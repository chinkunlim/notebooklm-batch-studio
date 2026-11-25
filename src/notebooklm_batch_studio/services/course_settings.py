"""Per-course settings and versioned regeneration, kept apart from the orchestrator.

Generation options change how future Gemini Notebook generations look (infographic orientation,
audio format, ...). Regeneration enqueues a new version of one artifact slot and never deletes
or overwrites the older version (ADR-005).
"""

from __future__ import annotations

import dataclasses
import json
import logging
import shutil
import uuid
from datetime import date, datetime
from typing import Any

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    CourseStatus,
    JobStatus,
    ProfileName,
    effective_options,
    merge_generation_options,
)
from notebooklm_batch_studio.domain.naming import label_for
from notebooklm_batch_studio.domain.repositories import CourseRepositoryProtocol, QueueRepositoryProtocol
from notebooklm_batch_studio.domain.study_hierarchy import resolve_course_output_root
from notebooklm_batch_studio.services.course_options import (
    apply_job_settings as apply_job_settings,
)
from notebooklm_batch_studio.services.course_options import (
    default_options as default_options,
)
from notebooklm_batch_studio.services.course_options import (
    fields_for_type as fields_for_type,
)
from notebooklm_batch_studio.services.course_options import (
    job_overrides as job_overrides,
)
from notebooklm_batch_studio.services.course_options import (
    option_choices as option_choices,
)
from notebooklm_batch_studio.services.job_planner import blueprint_or_none, generate_jobs_for_course
from notebooklm_batch_studio.services.prompt_generator import PromptGenerator

CHAPTER_TYPES = [t.value for t in ArtifactType if not t.value.startswith("course_")]
COURSE_TYPES = [t.value for t in ArtifactType if t.value.startswith("course_")]
UNSTARTED = [JobStatus.PENDING, JobStatus.QUOTA_WAIT, JobStatus.FAILED]
LANGUAGES = ("zh-TW", "en", "bilingual")
MOCK_EXAM_RANGE = (10, 100)


logger = logging.getLogger(__name__)


class CourseSettingsService:
    """Read and change generation options; enqueue new versions of artifacts."""

    def __init__(
        self,
        course_repo: CourseRepositoryProtocol,
        queue_repo: QueueRepositoryProtocol,
        config: AppConfig,
    ) -> None:
        """Bind the service to its repositories.

        Args:
            course_repo: Course persistence.
            queue_repo: Job queue persistence.
            config: Application configuration (folders used when deleting a course).
        """
        self.course_repo = course_repo
        self.queue_repo = queue_repo
        self.config = config

    def _course(self, code: str) -> Course:
        """Load a course or raise.

        Args:
            code: Course code.

        Returns:
            The course.

        Raises:
            CourseNotFoundError: When the course does not exist.
        """
        course = self.course_repo.get_course(code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {code}")
        return course

    def get_options(self, code: str) -> dict[str, Any]:
        """Return a course's generation options and the allowed values.

        Args:
            code: Course code.

        Returns:
            Dictionary with `options` (current values) and `choices` (allowed values; None = boolean).
        """
        course = self._course(code)
        options = dataclasses.asdict(course.generation_options)
        options.update(
            language=course.language,
            mock_exam_questions=course.mock_exam_questions,
            exam_date=course.exam_date or "",
        )
        choices = option_choices()
        choices.update(
            language=list(LANGUAGES),
            mock_exam_questions={"min": MOCK_EXAM_RANGE[0], "max": MOCK_EXAM_RANGE[1]},
            exam_date="date",
        )
        return {"options": options, "choices": choices, "defaults": default_options()}

    def set_options(self, code: str, changes: dict[str, Any]) -> dict[str, Any]:
        """Validate and store option changes; they apply to generations started afterwards.

        Args:
            code: Course code.
            changes: Option name to new value.

        Returns:
            The updated options in the same shape as `get_options`.

        Raises:
            ValueError: On an unknown option or a disallowed value.
        """
        course = self._course(code)
        changes = dict(changes)
        language = changes.pop("language", course.language)
        mock = changes.pop("mock_exam_questions", course.mock_exam_questions)
        exam_date = str(changes.pop("exam_date", course.exam_date or "") or "").strip() or None
        if exam_date is not None:
            try:
                date.fromisoformat(exam_date)
            except ValueError as err:
                raise ValueError("exam_date must look like 2026-12-20") from err
        if language not in LANGUAGES:
            raise ValueError(f"language must be one of {', '.join(LANGUAGES)}")
        if (
            not isinstance(mock, int)
            or isinstance(mock, bool)
            or not MOCK_EXAM_RANGE[0] <= mock <= MOCK_EXAM_RANGE[1]
        ):
            raise ValueError(
                "mock_exam_questions must be a whole number from "
                f"{MOCK_EXAM_RANGE[0]} to {MOCK_EXAM_RANGE[1]}"
            )
        updated = merge_generation_options(course.generation_options, changes)
        self.course_repo.update_generation_options(code, updated)
        if (language, mock, exam_date) != (course.language, course.mock_exam_questions, course.exam_date):
            self.course_repo.update_course_basics(code, language, mock, exam_date)
        logger.info("Updated generation options for %s: %s", code, sorted(changes))
        return self.get_options(code)

    def copy_options(self, code: str, targets: list[str]) -> dict[str, Any]:
        """Copy one course's options, language, and mock exam count to other courses.

        Each target course keeps its own exam date.

        Args:
            code: Source course code.
            targets: List of target course codes.

        Returns:
            Dictionary naming the source, updated targets, and copied values.

        Raises:
            CourseNotFoundError: If source or any target course does not exist.
            ValueError: If no valid target courses are specified.
        """
        source = self._course(code)
        clean_targets = list(dict.fromkeys(t.strip() for t in targets if t.strip() and t.strip() != code))
        if not clean_targets:
            raise ValueError("targets must contain at least one other course code")
        target_courses = [self._course(t) for t in clean_targets]
        for target in target_courses:
            self.course_repo.update_generation_options(target.code, source.generation_options)
            self.course_repo.update_course_basics(
                target.code, source.language, source.mock_exam_questions, target.exam_date
            )
        logger.info("Copied options from %s to %s", code, clean_targets)
        return {
            "source": code,
            "copied_to": clean_targets,
            "options": dataclasses.asdict(source.generation_options),
            "language": source.language,
            "mock_exam_questions": source.mock_exam_questions,
        }

    def _latest_slot_job(
        self, course_code: str, lecture_no: int | None, art_type: ArtifactType
    ) -> ArtifactJob | None:
        """Return the highest-version job recorded for one `(course, lecture, artifact_type)` slot.

        Args:
            course_code: Course code.
            lecture_no: Target lecture number or None for course-wide scope.
            art_type: Target ArtifactType enum value.

        Returns:
            Highest-version domain ArtifactJob in that slot, or None when absent.
        """
        slot = [
            j
            for j in self.queue_repo.list_jobs(course_code=course_code)
            if j.lecture_no == lecture_no and j.artifact_type == art_type
        ]
        return max(slot, key=lambda j: j.version) if slot else None

    def _build_regenerated_job(
        self, course: Course, lecture_no: int | None, art_type: ArtifactType
    ) -> ArtifactJob:
        """Construct the next versioned ArtifactJob inheriting slot style overrides.

        Args:
            course: Domain Course entity.
            lecture_no: Target lecture number or None for course-wide scope.
            art_type: Target ArtifactType enum value.

        Returns:
            Newly created pending ArtifactJob ready for enqueueing.
        """
        lecture = next((lec for lec in course.lectures if lec.no == lecture_no), None)
        if lecture_no is not None and lecture is None:
            raise ValueError(f"Lecture {lecture_no} not found in course {course.code}")
        version = self.queue_repo.max_version(course.code, lecture_no, art_type) + 1
        latest = self._latest_slot_job(course.code, lecture_no, art_type)
        # Always start from the current blueprint: an older version's stored prompt may predate
        # prompt fixes (e.g. the 10-question quizzes, ISSUE-017). Edit the queued job to customize.
        topic = lecture.topic if lecture else f"{course.code} 全範圍整合"
        prompt = blueprint_or_none(PromptGenerator(), art_type, topic, course)
        return ArtifactJob(
            id=str(uuid.uuid4()),
            course_code=course.code,
            lecture_no=lecture_no,
            artifact_type=art_type,
            custom_prompt=prompt,
            version=version,
            # The output's own settings carry over to the new version (SPEC-006).
            style_options=latest.style_options if latest else None,
        )

    def regenerate(self, code: str, lecture_no: int | None, artifact_type: str) -> dict[str, Any]:
        """Enqueue the next version of one artifact slot, reviving skipped v1 jobs when present.

        Args:
            code: Course code.
            lecture_no: Lecture number, or None for a course-wide artifact.
            artifact_type: Artifact type value (e.g. 'infographic').

        Returns:
            Summary of the new or revived job (id, version, label, lecture_no).

        Raises:
            ValueError: When the artifact type is unknown, scope mismatches, or lecture is missing.
        """
        course = self._course(code)
        if course.profile == ProfileName.RECORD_ONLY:  # Refs: ISSUE-068
            raise ValueError(
                "此課程為 record-only 模式且未連結 Gemini Notebook，"
                "請先變更產出模式並完成筆記本設定後再重新生成"
            )
        art_type = ArtifactType(artifact_type)
        if (lecture_no is None) != (art_type.value in COURSE_TYPES):
            raise ValueError(f"Scope mismatch for {artifact_type} with lecture_no={lecture_no}")
        if lecture_no is not None and not any(lec.no == lecture_no for lec in course.lectures):
            raise ValueError(f"Lecture {lecture_no} not found in course {course.code}")
        latest = self._latest_slot_job(code, lecture_no, art_type)
        if latest is not None and latest.status == JobStatus.SKIPPED:
            self.queue_repo.retry_job(latest.id)
            logger.info("Revived skipped %s v%d for %s L%s", art_type.value, latest.version, code, lecture_no)
            job = latest
        else:
            job = self._build_regenerated_job(course, lecture_no, art_type)
            self.queue_repo.enqueue_jobs([job])
            logger.info("Enqueued %s v%d for %s L%s", art_type.value, job.version, code, lecture_no)
        return {
            "job_id": job.id,
            "version": job.version,
            "label": label_for(art_type),
            "lecture_no": lecture_no,
        }

    def get_artifact_selection(self, code: str) -> dict[str, Any]:
        """Return which artifact types a course generates, with labels for every choice.

        Args:
            code: Course code.

        Returns:
            Dictionary with `chapter` and `course` (selected type values) and `choices`
            (type value and label for each scope).
        """
        course = self._course(code)
        types = {j.artifact_type.value for j in generate_jobs_for_course(course)}
        if course.selected_chapter_artifacts or course.selected_course_artifacts:
            types = set(course.selected_chapter_artifacts) | set(course.selected_course_artifacts)
        return {
            "chapter": [t for t in CHAPTER_TYPES if t in types],
            "course": [t for t in COURSE_TYPES if t in types],
            "choices": {
                "chapter": [{"value": t, "label": label_for(t)} for t in CHAPTER_TYPES],
                "course": [{"value": t, "label": label_for(t)} for t in COURSE_TYPES],
            },
        }

    def set_artifact_selection(self, code: str, chapter: list[str], whole: list[str]) -> dict[str, Any]:
        """Change which artifact types a course generates after it was added.

        Newly chosen types are queued (skipped jobs of that type are revived); unchosen types have
        their unstarted jobs skipped. Finished outputs are never deleted.

        Args:
            code: Course code.
            chapter: Per-lecture artifact type values to generate.
            whole: Course-wide artifact type values to generate.

        Returns:
            Counts of queued, revived and skipped jobs plus the new selection.

        Raises:
            ValueError: When a value is not a known type of the right scope.
        """
        bad = [t for t in chapter if t not in CHAPTER_TYPES] + [t for t in whole if t not in COURSE_TYPES]
        if bad:
            raise ValueError(f"Unknown or wrong-scope artifact types: {', '.join(bad)}")
        before = self.get_artifact_selection(code)
        old = set(before["chapter"]) | set(before["course"])
        new = set(chapter) | set(whole)
        self.course_repo.update_artifact_selection(code, list(chapter), list(whole))
        removed, added = sorted(old - new), sorted(new - old)
        skipped = self.queue_repo.set_types_status(code, removed, UNSTARTED, JobStatus.SKIPPED)
        revived = self.queue_repo.set_types_status(code, added, [JobStatus.SKIPPED], JobStatus.PENDING)
        course = self._course(code)
        queued = self.queue_repo.enqueue_jobs(
            [j for j in generate_jobs_for_course(course) if j.artifact_type.value in added]
        )
        logger.info("Artifact selection for %s: +%s -%s", code, added, removed)
        return {"queued": queued, "revived": revived, "skipped": skipped, **self.get_artifact_selection(code)}

    def _job(self, job_id: str) -> ArtifactJob:
        """Load a job or raise.

        Args:
            job_id: Job id.

        Returns:
            The job.

        Raises:
            ValueError: When the job does not exist.
        """
        job = self.queue_repo.get_job(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")
        return job

    def get_job_options(self, job_id: str) -> dict[str, Any]:
        """Return one output's own settings, the settings it will actually use, and its fields.

        Args:
            job_id: Job id.

        Returns:
            Dictionary with `overrides`, `effective` (course + overrides), `fields` relevant to the
            type, `choices`, `status`, and `unsupported` notes for options the library lacks.
        """
        job = self._job(job_id)
        course = self._course(job.course_code)
        overrides = job_overrides(job)
        effective = effective_options(course.generation_options, overrides)
        is_quiz = job.artifact_type.value.removeprefix("course_").startswith(("quiz", "mock_exam"))
        return {
            "job_id": job.id,
            "artifact_type": job.artifact_type.value,
            "label": label_for(job.artifact_type),
            "status": job.status.value,
            "overrides": overrides,
            "effective": dataclasses.asdict(effective),
            "fields": fields_for_type(job.artifact_type.value),
            "choices": option_choices(),
            "defaults": default_options(),
            "unsupported": ["題型（選擇題／簡答題）：等 notebooklm-py 下一版支援後開放"] if is_quiz else [],
        }

    def set_job_options(self, job_id: str, overrides: dict[str, Any]) -> dict[str, Any]:
        """Replace one output's own settings; empty values fall back to the course settings.

        Args:
            job_id: Job id.
            overrides: Option name to value; "" or None removes that override.

        Returns:
            The same shape as `get_job_options`.

        Raises:
            ValueError: On an option the type does not use, or an invalid value.
        """
        job = self._job(job_id)
        allowed = set(fields_for_type(job.artifact_type.value))
        cleaned = {k: v for k, v in overrides.items() if v not in ("", None)}
        bad = sorted(set(cleaned) - allowed)
        if bad:
            raise ValueError(f"Options not used by {job.artifact_type.value}: {', '.join(bad)}")
        merge_generation_options(self._course(job.course_code).generation_options, cleaned)  # validates
        self.queue_repo.update_job_style_options(
            job_id, json.dumps(cleaned, ensure_ascii=False) if cleaned else None
        )
        logger.info("Updated own settings of job %s: %s", job_id, sorted(cleaned))
        return self.get_job_options(job_id)

    def set_paused(self, code: str, paused: bool) -> dict[str, Any]:
        """Pause a course (its jobs wait) or start it (its jobs join the running queue).

        Args:
            code: Course code.
            paused: True to pause, False to start.

        Returns:
            Course code and its new paused state.
        """
        self._course(code)
        self.course_repo.set_course_paused(code, paused)
        logger.info("Course %s %s", code, "paused" if paused else "started")
        return {"code": code, "paused": paused}

    def _move_legacy_delete_targets(self, code: str) -> str | None:
        """Move only legacy output/courses and needs_review folders into deleted/.

        Args:
            code: Course code being removed from the database.

        Returns:
            Target archive path when at least one legacy folder moved, else None.
        """
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.config.deleted_dir / f"{code}-{stamp}"
        moved: str | None = None
        legacy_output = resolve_course_output_root(self.config.courses_output_dir, code, "")
        sources = [legacy_output, *self.config.needs_review_dir.glob(f"{code}_*")]
        for folder in (f for f in sources if f.exists()):
            target.mkdir(parents=True, exist_ok=True)
            shutil.move(str(folder), str(target / folder.name))
            moved = str(target)
        return moved

    def delete_course(self, code: str) -> dict[str, Any]:
        """Remove an archived course from DB while keeping all study/ files intact.

        Only legacy `output/courses/<code>` and `needs_review/<code>_*` folders are moved
        to `DATA_DIR/deleted/<code>-<time>/` (Refs: ISSUE-065). Active courses are refused.

        Args:
            code: Course code (must already have `status == CourseStatus.ARCHIVED`).

        Returns:
            Removed job count, legacy move target, and counts of removed learning records.
        """
        course = self._course(code)
        if course.status != CourseStatus.ARCHIVED:
            raise ValueError("請先封存課程，封存後才能刪除")
        counts = self.course_repo.count_learning_records(code)
        moved = self._move_legacy_delete_targets(code)
        removed = self.course_repo.delete_course(code)
        logger.info("Deleted archived course %s (%d jobs); legacy moved to %s", code, removed, moved)
        return {
            "code": code,
            "removed_jobs": removed,
            "moved_to": moved,
            "learning_records_removed": counts,
        }
