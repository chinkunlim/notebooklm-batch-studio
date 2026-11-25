"""Tests for SPEC-012: unified study hierarchy, legacy migration, and literature-fetch integration."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository
from notebooklm_batch_studio.adapters.db.models import CourseRecord
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.adapters.db.study_migration_repo import StudyMigrationRepository
from notebooklm_batch_studio.adapters.literature.factory import AdapterLiteratureRuntime
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.literature.literature import Reference, ReferenceKind, WorkMeta
from notebooklm_batch_studio.domain.literature.tracker import ItemStatus, TrackedItem
from notebooklm_batch_studio.domain.study_hierarchy import (
    ensure_course_study_tree,
    parse_term_subject,
    resolve_course_study_dir,
    resolve_literature_dir,
    resolve_notebooklm_notes_dir,
)
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.course_parser import scan_course_directory
from notebooklm_batch_studio.services.literature.manager import LiteratureManager
from notebooklm_batch_studio.services.study_migration import migrate_courses_to_study_hierarchy


class _FakeResolver:
    """Offline WorkResolver returning deterministic metadata for tests."""

    def by_doi(self, doi: str) -> WorkMeta | None:
        return WorkMeta(
            doi=doi,
            title="Test Cognitive Load Paper",
            year=2024,
            kind=ReferenceKind.ARTICLE,
            first_author="Sweller",
            authors=(("Sweller", "John"),),
            container="Educational Psychology Review",
            volume="36",
            issue="1",
            pages="1-18",
        )

    def search(self, query: str, rows: int = 5) -> list[WorkMeta]:
        return [self.by_doi("10.1000/test.2024")]  # type: ignore[list-item]


class StudyHierarchyAndMigrationTest(unittest.TestCase):
    """Verify `<term>/<subject>/<category>` parsing, recursive scanning, and legacy migration."""

    def test_parse_term_subject_and_paths(self) -> None:
        """Term/subject parsing extracts `115-1` and `心理學研究法` and builds standard paths."""
        term, subject = parse_term_subject("115-1 心理學研究法")
        self.assertEqual(term, "115-1")
        self.assertEqual(subject, "心理學研究法")

        root = Path("/tmp/study-root")
        course_dir = resolve_course_study_dir(root, term, subject, "PSYC101")
        self.assertEqual(course_dir, root / "115-1" / "心理學研究法")
        self.assertEqual(
            resolve_literature_dir(course_dir),
            course_dir / "01 Materials" / "Literature_Review",
        )
        self.assertEqual(
            resolve_notebooklm_notes_dir(course_dir),
            course_dir / "03 Notes" / "NotebookLM",
        )

    def test_recursive_course_scan_ignores_notes_and_assignments(self) -> None:
        """Scanning a study-layout course reads nested `02 Handouts` (or alias) only."""
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "115-1" / "心理學研究法"
            ensure_course_study_tree(course_dir)
            (course_dir / "01 Materials" / "Literature_Review").mkdir(parents=True, exist_ok=True)
            (course_dir / "02 Handouts" / "Week01").mkdir(parents=True, exist_ok=True)
            (course_dir / "01 Materials" / "Literature_Review" / "01_Paper.pdf").write_bytes(b"%PDF-1.4\na")
            (course_dir / "02 Handouts" / "Week01" / "02_Slides.pdf").write_bytes(b"%PDF-1.4\nb")
            (course_dir / "03 Notes" / "my_note.pdf").write_bytes(b"%PDF-1.4\nc")
            (course_dir / "05 Assignments" / "report.pdf").write_bytes(b"%PDF-1.4\nd")

            course = scan_course_directory(course_dir, custom_code="PSYC101")
            self.assertEqual(course.term, "115-1")
            self.assertEqual(course.subject, "心理學研究法")
            self.assertEqual(course.study_dir, str(course_dir.resolve()))
            filenames = [lec.filename for lec in course.lectures]
            self.assertEqual(filenames, ["02_Slides.pdf"])
            self.assertTrue(all(lec.relative_path.startswith("02 Handouts/") for lec in course.lectures))

    def test_legacy_migration_moves_files_and_updates_db(self) -> None:
        """Legacy flat `input/courses` + `output/courses` migrate cleanly into `study_root_dir`."""
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            cfg = AppConfig(
                data_dir=data_dir,
                database_url=f"sqlite:///{data_dir / 'db' / 'app.db'}",
                http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
            )
            cfg.db_dir.mkdir(parents=True, exist_ok=True)
            engine = create_db_engine(cfg.database_url)
            Base.metadata.create_all(engine)
            session_factory = make_session_factory(engine)

            legacy_in = cfg.courses_input_dir / "115-1 心理學研究法"
            legacy_out = cfg.courses_output_dir / "PSYC101"
            legacy_in.mkdir(parents=True, exist_ok=True)
            (legacy_out / "01_導論").mkdir(parents=True, exist_ok=True)
            (legacy_in / "01_導論.pdf").write_bytes(b"%PDF-1.4\nhello")
            (legacy_out / "01_導論" / "audio.m4a").write_bytes(b"audio")

            with session_factory() as session:
                session.add(
                    CourseRecord(
                        code="PSYC101",
                        name="115-1 心理學研究法",
                        source_dir=str(legacy_in),
                    )
                )
                session.commit()

                preview = migrate_courses_to_study_hierarchy(
                    StudyMigrationRepository(session), cfg, dry_run=True
                )
                self.assertEqual(preview["items"][0]["status"], "planned")
                self.assertTrue((legacy_in / "01_導論.pdf").is_file())

                result = migrate_courses_to_study_hierarchy(
                    StudyMigrationRepository(session), cfg, dry_run=False
                )
                self.assertEqual(result["items"][0]["status"], "migrated")

                target_dir = cfg.study_root_dir / "115-1" / "心理學研究法"
                self.assertTrue((target_dir / "02 Handouts" / "01_導論.pdf").is_file())
                self.assertTrue((target_dir / "03 Notes" / "NotebookLM" / "01_導論" / "audio.m4a").is_file())
                row = session.get(CourseRecord, "PSYC101")
                assert row is not None
                self.assertEqual(row.term, "115-1")
                self.assertEqual(row.subject, "心理學研究法")
                self.assertEqual(row.study_dir, str(target_dir))

    def test_migration_leaves_courses_already_in_study_root_alone(self) -> None:
        """A course already in a school-named study folder is not moved when `subject` differs (ISSUE-069)."""
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            cfg = AppConfig(
                data_dir=data_dir,
                database_url=f"sqlite:///{data_dir / 'db' / 'app.db'}",
                http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
            )
            cfg.db_dir.mkdir(parents=True, exist_ok=True)
            engine = create_db_engine(cfg.database_url)
            Base.metadata.create_all(engine)
            session_factory = make_session_factory(engine)

            school_dir = cfg.study_root_dir / "115-1" / "CP__30210-心理學研究法"
            ensure_course_study_tree(school_dir)
            (school_dir / "02 Handouts" / "Ch01.pdf").write_bytes(b"%PDF-1.4\nx")

            with session_factory() as session:
                session.add(
                    CourseRecord(
                        code="115-1_CP30210",
                        name="心理學研究法",
                        source_dir=str(school_dir),
                        term="115-1",
                        subject="心理學研究法",
                        study_dir=str(school_dir),
                    )
                )
                session.commit()

                for dry_run in (True, False):
                    result = migrate_courses_to_study_hierarchy(
                        StudyMigrationRepository(session), cfg, dry_run=dry_run
                    )
                    item = result["items"][0]
                    self.assertEqual(item["status"], "already_migrated")
                    self.assertEqual(item["new_study_dir"], str(school_dir))

                self.assertTrue((school_dir / "02 Handouts" / "Ch01.pdf").is_file())
                self.assertFalse((cfg.study_root_dir / "115-1" / "心理學研究法").exists())
                row = session.get(CourseRecord, "115-1_CP30210")
                assert row is not None
                self.assertEqual(row.study_dir, str(school_dir))


class LiteratureIntegrationTest(unittest.TestCase):
    """Verify LiteratureManager, HTTP routes, MCP tools, and Web UI exposure."""

    def test_manager_identify_import_and_export(self) -> None:
        """Manager identifies offline, exports APA 7 HTML, and imports PDF into course folder."""
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            cfg = AppConfig(
                data_dir=data_dir,
                database_url=f"sqlite:///{data_dir / 'db' / 'app.db'}",
                http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
            )
            cfg.db_dir.mkdir(parents=True, exist_ok=True)
            engine = create_db_engine(cfg.database_url)
            Base.metadata.create_all(engine)
            session_factory = make_session_factory(engine)

            study_course = cfg.study_root_dir / "115-1" / "教育心理學"
            ensure_course_study_tree(study_course)

            with session_factory() as session:
                session.add(
                    CourseRecord(
                        code="EDPS101",
                        name="教育心理學",
                        source_dir=str(study_course),
                        term="115-1",
                        subject="教育心理學",
                        study_dir=str(study_course),
                    )
                )
                session.commit()

                lit_repo = LiteratureRepository(session)
                course_repo = CourseRepository(session)
                mgr = LiteratureManager(cfg, lit_repo, course_repo, runtime=AdapterLiteratureRuntime(cfg))
                mgr._work_resolver = _FakeResolver()

                added = mgr.add_entries(
                    "10.1000/test.2024",
                    course_code="EDPS101",
                    category="01 Materials",
                    subfolder="Literature_Review",
                )
                self.assertEqual(len(added), 1)
                identified = mgr.identify_item(added[0])
                self.assertEqual(identified.status, ItemStatus.PENDING)
                self.assertIn("Sweller", identified.apa)

                target_dir = mgr.resolve_target_dir(identified)
                self.assertEqual(target_dir, study_course / "01 Materials" / "Literature_Review")
                pdf_file = target_dir / f"{identified.key}.pdf"
                pdf_file.write_bytes(b"%PDF-1.4\ntest")
                lit_repo.upsert_item(
                    TrackedItem(
                        key=identified.key,
                        input=identified.input,
                        reference=Reference(
                            key=identified.key, citation=identified.apa, doi="10.1000/test.2024"
                        ),
                        apa=identified.apa,
                        status=ItemStatus.DOWNLOADED,
                        file=pdf_file.name,
                        course_code="EDPS101",
                        target_category="01 Materials",
                        target_subfolder="Literature_Review",
                    )
                )

                imported = mgr.import_to_course(identified.key)
                self.assertTrue(imported.imported_to_course)
                apa_export = mgr.export_apa_list("EDPS101")
                self.assertEqual(apa_export["count"], 1)
                self.assertIn("<i>", apa_export["html"])

                # Unarchive moves back to staging folder; untracked PDF auto-sync registers new files
                unarchived = mgr.unarchive_item(identified.key)
                self.assertFalse(unarchived.imported_to_course)
                self.assertIsNone(unarchived.course_code)
                self.assertTrue((cfg.literature_dir / pdf_file.name).is_file())

                (cfg.literature_dir / "Manual_Added_2026.pdf").write_bytes(b"%PDF-1.4\nmanual")
                synced_keys = mgr.sync_untracked_pdfs()
                self.assertEqual(synced_keys, ["Manual_Added_2026"])
                self.assertIsNotNone(lit_repo.get_item("Manual_Added_2026"))

    def test_http_and_mcp_literature_endpoints(self) -> None:
        """HTTP API, Web UI HTML, and MCP tools expose literature and migration endpoints."""
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            cfg = AppConfig(
                data_dir=data_dir,
                database_url=f"sqlite:///{data_dir / 'db' / 'app.db'}",
                http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
            )
            cfg.db_dir.mkdir(parents=True, exist_ok=True)
            Base.metadata.create_all(create_db_engine(cfg.database_url))
            app = create_app(config=cfg)
            client = TestClient(app)

            html_resp = client.get("/")
            self.assertEqual(html_resp.status_code, 200)
            self.assertIn('data-view="literature"', html_resp.text)
            self.assertIn('id="view-literature"', html_resp.text)
            self.assertIn("studio-literature.js", html_resp.text)

            add_resp = client.post(
                "/api/literature/add",
                json={
                    "text": "10.1000/sample.2025",
                    "category": "01 Materials",
                    "subfolder": "Literature_Review",
                },
            )
            self.assertEqual(add_resp.status_code, 200)
            keys = add_resp.json()["keys"]
            self.assertEqual(len(keys), 1)

            list_resp = client.get("/api/literature")
            self.assertEqual(list_resp.status_code, 200)
            self.assertEqual(len(list_resp.json()["items"]), 1)

            del_resp = client.delete(f"/api/literature/{keys[0]}")
            self.assertEqual(del_resp.status_code, 200)

            mcp = build_mcp_server(
                service=app.state.service,
                study_service=app.state.study_service,
                config=cfg,
                literature_jobs=app.state.literature_jobs,
                preferences=app.state.preferences,
            )
            tools = {t.name: t for t in mcp._tool_manager.list_tools()}
            self.assertIn("list_literature", tools)
            self.assertIn("add_literature", tools)
            self.assertIn("process_literature", tools)
            self.assertIn("import_literature_to_course", tools)
            self.assertIn("delete_literature", tools)
            self.assertIn("migrate_study_layout", tools)
            self.assertIn("sync_literature_notebook", tools)
            self.assertIn("query_literature_notebook", tools)
            self.assertIn("generate_literature_review", tools)

            nb_resp = client.get("/api/literature/notebook")
            self.assertEqual(nb_resp.status_code, 200)
            self.assertIn("total_with_pdf", nb_resp.json())

            guard_res = json.loads(tools["delete_literature"].fn(key="x", confirm=False))
            self.assertFalse(guard_res["confirmed"])
            self.assertIn("confirm", guard_res["warning"].lower())


if __name__ == "__main__":
    unittest.main()
