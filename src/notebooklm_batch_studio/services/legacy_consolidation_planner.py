"""Discovery and step-planning helpers for legacy data consolidation (Refs: SPEC-014 Task 15)."""

from __future__ import annotations

import logging
from pathlib import Path

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.config.study_layout import CategoryRole
from notebooklm_batch_studio.domain.course_identity import (
    TERM_PATTERN,
    make_course_code,
    parse_course_folder,
)
from notebooklm_batch_studio.domain.models import Course
from notebooklm_batch_studio.domain.path_safety import is_within
from notebooklm_batch_studio.domain.study_hierarchy import (
    parse_term_subject,
    resolve_category_dir,
    resolve_note_studio_dir,
)
from notebooklm_batch_studio.services.legacy_consolidation_ops import (
    ActionType,
    ConsolidationRequest,
    ConsolidationStep,
    inventory_directory_summary,
    singular_aliases_for,
)
from notebooklm_batch_studio.services.notes.note_sync import list_legacy_markdown_files

logger = logging.getLogger(__name__)


def resolve_under(base: Path, raw: str) -> Path:
    """Resolve `raw` safely inside `base` while preserving `base`'s path prefix style.

    Args:
        base: Root containment directory.
        raw: Relative or absolute path string.

    Returns:
        Normalized `Path` inside `base`.

    Raises:
        ValueError: When `raw` escapes `base`.
    """
    candidate = Path(raw) if Path(raw).is_absolute() else (base / raw)
    resolved, base_resolved = candidate.resolve(), base.resolve()
    if not is_within(resolved, base_resolved):
        raise ValueError(f"路徑超出允許目錄 {base}：{raw}")
    return base if resolved == base_resolved else (base / resolved.relative_to(base_resolved))


def _resolve_folder_pair(study_root: Path, old_raw: str, new_raw: str) -> tuple[Path, Path]:
    """Resolve source and target paths for a `--folder OLD=NEW_FOLDER` mapping.

    Args:
        study_root: Configured `study/` root directory.
        old_raw: Old folder path relative to `study_root` or inside it.
        new_raw: New folder basename under the same term, or `<term>/<name>`.

    Returns:
        `(old_dir, new_dir)` pair.
    """
    old_dir = resolve_under(study_root, old_raw)
    target_rel = new_raw if ("/" in new_raw or "\\" in new_raw) else f"{old_dir.parent.name}/{new_raw}"
    return old_dir, resolve_under(study_root, target_rel)


def build_course_dir_index(
    config: AppConfig, request: ConsolidationRequest, courses: list[Course]
) -> tuple[dict[str, Path], dict[str, Path], list[tuple[str, str]]]:
    """Build post-rename `code -> study_dir`, `old_dir -> new_dir` map, and unique rename pairs.

    Args:
        config: Application configuration.
        request: Requested code and folder mappings.
        courses: Registered courses loaded from DB.

    Returns:
        `(code_to_dir, old_to_new_dir, folder_pairs)` tuple.
    """
    old_to_new: dict[str, Path] = {}
    pairs: list[tuple[str, str]] = []
    code_to_dir: dict[str, Path] = {}
    for old_raw, new_raw in request.folder_maps.items():
        old_d, new_d = _resolve_folder_pair(config.study_root_dir, old_raw, new_raw)
        if old_d != new_d:
            old_to_new[str(old_d)] = new_d
            old_to_new[str(old_d.resolve())] = new_d
            pairs.append((str(old_d), str(new_d)))
        parsed = parse_course_folder(new_d.name)
        if parsed and parsed.course_no and TERM_PATTERN.match(new_d.parent.name):
            inferred = make_course_code(new_d.parent.name, parsed.course_no)
            code_to_dir[inferred] = new_d
            code_to_dir[request.code_maps.get(inferred, inferred)] = new_d
    for c in courses:
        if not c.study_dir:
            continue
        base_dir = Path(c.study_dir)
        resolved_dir = old_to_new.get(str(base_dir)) or old_to_new.get(str(base_dir.resolve()), base_dir)
        code_to_dir[c.code] = resolved_dir
        code_to_dir[request.code_maps.get(c.code, c.code)] = resolved_dir
    return code_to_dir, old_to_new, pairs


def _match_input_folder(folder: Path, code_to_dir: dict[str, Path], code_maps: dict[str, str]) -> Path | None:
    """Resolve an `input/courses/<dir>` folder to a known course study directory if matched.

    Args:
        folder: Legacy input subfolder path.
        code_to_dir: Post-rename course code -> `study_dir` map.
        code_maps: Course code overrides.

    Returns:
        Target course `study_dir` Path, or None when unmapped.
    """
    parsed = parse_course_folder(folder.name)
    if parsed and parsed.course_no:
        guessed = code_maps.get(parsed.course_no, parsed.course_no)
        for code, cdir in code_to_dir.items():
            if cdir.name == folder.name or code.endswith(f"_{guessed}"):
                return cdir
    _, subj = parse_term_subject(folder.name)
    for d in code_to_dir.values():
        if d.name == folder.name or folder.name in d.name or (subj and subj in d.name):
            return d
    return None


def _is_under_assigned(path: Path, assigned_paths: set[Path]) -> bool:
    """Return True when `path` equals or sits inside any `--assign` source path.

    Args:
        path: Candidate path to check.
        assigned_paths: Resolved paths explicitly handled by `--assign`.

    Returns:
        True if already covered by an assignment.
    """
    resolved = path.resolve()
    return any(resolved == ap or is_within(resolved, ap) for ap in assigned_paths)


def _input_subfolder_inventories(
    folder: Path, notes_name: str, assigned_paths: set[Path]
) -> list[ConsolidationStep]:
    """Emit inventory steps for un-assigned non-PDF subfolders inside `input/courses/<course>/`.

    Args:
        folder: Input course directory.
        notes_name: Canonical Notes category folder name (e.g. `03 Notes`).
        assigned_paths: Explicitly assigned source paths to skip.

    Returns:
        List of `inventory` steps for non-empty non-PDF subdirectories (such as `study-notes`).
    """
    steps: list[ConsolidationStep] = []
    for sub in sorted(folder.iterdir()):
        if not sub.is_dir() or sub.name.startswith(".") or _is_under_assigned(sub, assigned_paths):
            continue
        has_non_pdf = any(
            p.is_file() and not p.name.startswith(".") and p.suffix.lower() != ".pdf" for p in sub.rglob("*")
        )
        if not has_non_pdf:
            continue
        target_hint = f"(input/courses 子資料夾，建議 --assign 至 {notes_name}/{sub.name}/)"
        steps.append(ConsolidationStep("inventory", str(sub), target_hint, inventory_directory_summary(sub)))
    return steps


def _steps_for_input_folder(
    config: AppConfig, folder: Path, code_to_dir: dict[str, Path], assigned_paths: set[Path]
) -> list[ConsolidationStep]:
    """Build `move` and `inventory` steps for PDFs and subfolders under `input/courses/`.

    Args:
        config: Application configuration.
        folder: Candidate input course folder.
        code_to_dir: Course code -> `study_dir` lookup.
        assigned_paths: Explicitly assigned paths already moved separately.

    Returns:
        List of consolidation steps discovered inside `folder`.
    """
    handouts_name = config.study_layout.names[CategoryRole.HANDOUTS]
    notes_name = config.study_layout.names[CategoryRole.NOTES]
    steps = _input_subfolder_inventories(folder, notes_name, assigned_paths)
    pdfs = [
        p
        for p in sorted(folder.rglob("*.pdf"))
        if p.is_file() and not p.name.startswith(".") and not _is_under_assigned(p, assigned_paths)
    ]
    if not pdfs:
        return steps
    target_dir = _match_input_folder(folder, code_to_dir, {})
    if target_dir is None:
        note = f"input/courses 含 {len(pdfs)} 份 PDF，待透過 --map / --folder 確認目標"
        steps.append(ConsolidationStep("inventory", str(folder), "(未對照到已註冊課程)", note))
        return steps
    steps.extend(
        ConsolidationStep(
            "move",
            str(pdf),
            str(target_dir / handouts_name / pdf.name),
            f"搬移舊 input PDF 至 {handouts_name}",
        )
        for pdf in pdfs
    )
    return steps


def plan_input_moves(
    config: AppConfig,
    request: ConsolidationRequest,
    code_to_dir: dict[str, Path],
    assigned_paths: set[Path] | None = None,
) -> list[ConsolidationStep]:
    """Plan PDF moves and non-PDF subfolder inventories from legacy `input/courses/` folders.

    Args:
        config: Application configuration.
        request: Consolidation request carrying `code_maps`.
        code_to_dir: Post-rename course code -> `study_dir` lookup.
        assigned_paths: Resolved paths explicitly handled via `--assign`.

    Returns:
        Planned `move` and `inventory` steps.
    """
    if not config.courses_input_dir.is_dir():
        return []
    assigned = assigned_paths or set()
    _ = request
    steps: list[ConsolidationStep] = []
    for folder in sorted(config.courses_input_dir.iterdir()):
        if folder.is_dir() and not folder.name.startswith("."):
            steps.extend(_steps_for_input_folder(config, folder, code_to_dir, assigned))
    return steps


def _singular_steps_for_course(config: AppConfig, disk_dir: Path, final_dir: Path) -> list[ConsolidationStep]:
    """Collect singular-to-plural merge steps inside one course folder.

    Args:
        config: Application configuration.
        disk_dir: Existing folder path on disk.
        final_dir: Post-rename course directory path.

    Returns:
        List of `merge` steps for non-empty singular category folders.
    """
    steps: list[ConsolidationStep] = []
    for role in CategoryRole:
        primary_name = config.study_layout.names[role]
        steps.extend(_singular_role_steps(config, disk_dir, final_dir, (role, primary_name)))
    return steps


def _dir_has_visible_files(folder: Path) -> bool:
    """Return True when `folder` contains at least one non-hidden file recursively.

    Args:
        folder: Candidate directory path.

    Returns:
        True when visible files exist under `folder`.
    """
    if not folder.is_dir():
        return False
    return any(p.is_file() and not p.name.startswith(".") for p in folder.rglob("*"))


def _singular_role_steps(
    config: AppConfig, disk_dir: Path, final_dir: Path, role_info: tuple[CategoryRole, str]
) -> list[ConsolidationStep]:
    """Check singular aliases for one category role inside a course folder.

    Args:
        config: Application configuration.
        disk_dir: Existing course directory on disk.
        final_dir: Post-rename destination directory.
        role_info: Tuple of `(CategoryRole, primary_plural_name)`.

    Returns:
        Matching `merge` steps.
    """
    role, primary_name = role_info
    steps: list[ConsolidationStep] = []
    for alias in singular_aliases_for(config.study_layout, role):
        if not _dir_has_visible_files(disk_dir / alias):
            continue
        note = f"單數分類 {alias} 內容併入 {primary_name}（同名加後綴，空夾保留）"
        steps.append(ConsolidationStep("merge", str(final_dir / alias), str(final_dir / primary_name), note))
    return steps


def plan_singular_merges(config: AppConfig, old_to_new: dict[str, Path]) -> list[ConsolidationStep]:
    """Scan `study/<term>/<course>` folders for singular categories and plan plural merges.

    Args:
        config: Application configuration.
        old_to_new: Post-rename course directory mappings.

    Returns:
        Planned `merge` steps.
    """
    if not config.study_root_dir.is_dir():
        return []
    steps: list[ConsolidationStep] = []
    for term_dir in sorted(config.study_root_dir.iterdir()):
        if not term_dir.is_dir() or term_dir.name.startswith("."):
            continue
        steps.extend(_singular_steps_in_term(config, term_dir, old_to_new))
    return steps


def _singular_steps_in_term(
    config: AppConfig, term_dir: Path, old_to_new: dict[str, Path]
) -> list[ConsolidationStep]:
    """Scan one semester directory inside `study/` for singular category merges.

    Args:
        config: Application configuration.
        term_dir: Semester folder path.
        old_to_new: Post-rename folder map.

    Returns:
        List of `merge` steps for all courses inside `term_dir`.
    """
    steps: list[ConsolidationStep] = []
    for cdir in sorted(term_dir.iterdir()):
        if not cdir.is_dir() or cdir.name.startswith("."):
            continue
        final_dir = old_to_new.get(str(cdir)) or old_to_new.get(str(cdir.resolve()), cdir)
        steps.extend(_singular_steps_for_course(config, cdir, final_dir))
    return steps


def _target_for_spec(
    config: AppConfig,
    request: ConsolidationRequest,
    code_to_dir: dict[str, Path],
    target_spec: tuple[str, CategoryRole, str],
) -> tuple[str, Path, str]:
    """Resolve destination path and descriptive category string for an assign/restore target.

    Args:
        config: Application configuration.
        request: Consolidation request carrying `code_maps`.
        code_to_dir: Resolved course code -> `study_dir` lookup.
        target_spec: Tuple of `(course_code, CategoryRole, subfolder)`.

    Returns:
        `(mapped_code, dest_dir, label_suffix)` tuple.

    Raises:
        ValueError: When target course code lacks a resolved `study_dir`.
    """
    raw_code, role, subfolder = target_spec
    mapped = request.code_maps.get(raw_code, raw_code)
    course_dir = code_to_dir.get(mapped) or code_to_dir.get(raw_code)
    if course_dir is None:
        raise ValueError(f"找不到課程 {raw_code} 的 study 資料夾")
    cat_name = config.study_layout.names[role]
    dest_dir = resolve_category_dir(course_dir, cat_name, subfolder, config.study_layout)
    return mapped, dest_dir, f"{cat_name}/{subfolder}".rstrip("/")


def plan_assignments(
    config: AppConfig, request: ConsolidationRequest, code_to_dir: dict[str, Path]
) -> tuple[list[ConsolidationStep], set[Path]]:
    """Plan explicit `--assign PATH=CODE:ROLE[/SUB]` moves (or copies when inside `deleted/`).

    Args:
        config: Application configuration.
        request: Consolidation request payload.
        code_to_dir: Post-rename course code -> `study_dir` lookup.

    Returns:
        Tuple of `(steps, assigned_resolved_paths)`.
    """
    steps: list[ConsolidationStep] = []
    assigned: set[Path] = set()
    deleted_root = config.deleted_dir.resolve()
    for src_raw, raw_code, role, subfolder in request.assignments:
        src_path = resolve_under(config.data_dir, src_raw)
        assigned.add(src_path.resolve())
        mapped, dest_dir, label = _target_for_spec(config, request, code_to_dir, (raw_code, role, subfolder))
        target_path = (dest_dir / src_path.name) if src_path.is_file() else dest_dir
        is_deleted = is_within(src_path.resolve(), deleted_root)
        action: ActionType = "copy" if is_deleted else "move"
        note = (
            f"從 deleted 複製還原至 {mapped} {label}（保留原檔）"
            if is_deleted
            else f"指派至 {mapped} {label}"
        )
        steps.append(ConsolidationStep(action, str(src_path), str(target_path), note))
    return steps, assigned


def plan_restores(
    config: AppConfig, request: ConsolidationRequest, code_to_dir: dict[str, Path]
) -> list[ConsolidationStep]:
    """Plan explicit `--restore PATH=CODE:ROLE[/SUB]` non-destructive copy steps from `deleted/`.

    Args:
        config: Application configuration.
        request: Consolidation request payload carrying `restores`.
        code_to_dir: Post-rename course code -> `study_dir` lookup.

    Returns:
        List of `copy` `ConsolidationStep` entries.
    """
    steps: list[ConsolidationStep] = []
    for src_raw, raw_code, role, subfolder in request.restores:
        src_path = resolve_under(config.data_dir, src_raw)
        mapped, dest_dir, label = _target_for_spec(config, request, code_to_dir, (raw_code, role, subfolder))
        target_path = (dest_dir / src_path.name) if src_path.is_file() else dest_dir
        note = f"從 deleted 複製還原至 {mapped} {label}（保留原檔）"
        steps.append(ConsolidationStep("copy", str(src_path), str(target_path), note))
    return steps


def _match_notes_course(
    folder_name: str, request: ConsolidationRequest, code_to_dir: dict[str, Path], courses: list[Course]
) -> Path | None:
    """Resolve a legacy NoteStudio subfolder name to a target course `study_dir`.

    Args:
        folder_name: Legacy NoteStudio folder name.
        request: Consolidation request.
        code_to_dir: Resolved course code -> `study_dir` map.
        courses: Registered courses.

    Returns:
        Matched course `study_dir`, or None when unmapped.
    """
    explicit = request.note_course_maps.get(folder_name)
    if explicit:
        mapped = request.code_maps.get(explicit, explicit)
        if mapped in code_to_dir:
            return code_to_dir[mapped]
    for c in courses:
        target_dir = code_to_dir.get(c.code)
        if target_dir and (folder_name == c.name or folder_name in target_dir.name or c.name in folder_name):
            return target_dir
    return None


def plan_legacy_notes(
    config: AppConfig, request: ConsolidationRequest, code_to_dir: dict[str, Path], courses: list[Course]
) -> list[ConsolidationStep]:
    """Plan imports of legacy standalone `note-studio` `.md` folders into `03 Notes/NoteStudio/`.

    Args:
        config: Application configuration.
        request: Consolidation request.
        code_to_dir: Resolved course code -> `study_dir` map.
        courses: Registered courses.

    Returns:
        List of `import_notes` or `inventory` steps.
    """
    ns_root = config.legacy_note_studio_dir
    if not ns_root or not ns_root.is_dir():
        return []
    steps: list[ConsolidationStep] = []
    for folder in sorted(ns_root.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        mds = list_legacy_markdown_files(folder)
        if not mds:
            continue
        target_course = _match_notes_course(folder.name, request, code_to_dir, courses)
        if target_course is None:
            note = f"note-studio 含 {len(mds)} 份 .md 筆記，請以對照表指定目標課程"
            steps.append(ConsolidationStep("inventory", str(folder), "(未對照到課程)", note))
            continue
        steps.append(
            ConsolidationStep(
                "import_notes",
                str(folder),
                str(resolve_note_studio_dir(target_course)),
                f"匯入 {len(mds)} 份舊 NoteStudio .md 至 03 Notes/NoteStudio",
            )
        )
    return steps
