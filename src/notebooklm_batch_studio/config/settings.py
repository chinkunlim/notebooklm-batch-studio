"""Configuration layer: the ONLY layer allowed to read environment variables.

Loads settings once at startup into an immutable `AppConfig` so every other layer
receives plain values instead of touching `os.environ`.

Data lives OUTSIDE the project folder: `DATA_DIR` holds
input/, output/, needs_review/, state/, db/ and logs/. The project folder only holds code,
docs and small test fixtures. A relative `DATA_DIR` is resolved from the project folder (never
from the current working directory), so the project and its data can be moved together.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.config.study_layout import (
    DEFAULT_LAYOUT,
    StudyLayout,
    layout_from_names,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = "../../projects-data/notebooklm-batch-studio"
SCRATCH_KINDS: tuple[str, ...] = ("literature", "notes", "outputs", "uploads", "unarchived")


def resolve_data_dir(raw: str) -> Path:
    """Turn a `DATA_DIR` value into an absolute path.

    Args:
        raw: Value from `.env`; relative paths are relative to the project folder, `~` is expanded.

    Returns:
        The absolute data folder.
    """
    path = Path(raw.strip()).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


# Keys whose project `.env` value beats an inherited environment variable. `DATA_DIR` is a common
# name (e.g. Open WebUI's `export DATA_DIR=...` in ~/.zshrc) and must never point a project elsewhere.
PROJECT_FILE_WINS = ("DATA_DIR",)


def load_dotenv_file(path: Path) -> None:
    """Load `KEY=value` lines from a `.env` file.

    Variables that are already set win (so `LOG_LEVEL=DEBUG uv run ...` works), except the keys in
    `PROJECT_FILE_WINS`, where the project's own `.env` always wins.

    Args:
        path: The `.env` file (missing files are ignored).
    """
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("\"'")
            if key in PROJECT_FILE_WINS and value:
                os.environ[key] = value
            else:
                os.environ.setdefault(key, value)


@dataclass(frozen=True)
class AppConfig:
    """Immutable application settings.

    Attributes:
        app_env: Deployment environment name, e.g. `development` or `production`.
        log_level: Logging level name, e.g. `INFO` or `DEBUG`.
        log_to_file: Also write `<data_dir>/logs/app.log` and `errors.log` (default on; tests turn it off).
        timeout_seconds: Timeout for outgoing API calls.
        ollama_base_url: Local Ollama endpoint (always 127.0.0.1, never localhost / 0.0.0.0).
        ollama_model: Ollama model tag used for prompt refinement (`OLLAMA_MODEL`).
        data_dir: Root folder for all data, outside the project folder.
        database_url: SQLAlchemy URL; SQLite file `<data_dir>/db/app.db` by default.
        notebooklm_home: Folder holding Gemini Notebook credentials and session states.
        auto_start_queue: Start the job queue when the web service starts (`AUTO_START_QUEUE`,
            default true in `.env`; off for configs built directly, e.g. in tests).
        study_root_dir_override: Optional custom root for `<term>/<subject>/<category>` study folders.
        legacy_note_studio_dir: Optional whitelisted folder for standalone `note-studio` legacy
            imports (`LEGACY_NOTE_STUDIO_DIR`). Refs: ADR-013, ISSUE-045
        library_email: University e-mail for OpenAthens sign-in (`LIBRARY_EMAIL`; legacy `USER_EMAIL`).
        library_password: Library (OpenAthens) password, never a Google password (`LIBRARY_PASSWORD`;
            legacy `USER_PASSWORD`); hidden from repr. Refs: ADR-013
        openathens_domain: OpenAthens organisation domain; empty uses plain DOI links.
        ebsco_profile: Library EBSCO Discovery profile id; empty skips EBSCO.
        chrome_path: Google Chrome executable path (`CHROME_PATH`). Refs: ISSUE-053
        study_categories: Optional comma-separated 5 study category names (`STUDY_CATEGORIES`).
    """

    app_env: str = "development"
    log_level: str = "INFO"
    log_to_file: bool = True
    timeout_seconds: int = 15
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma4:latest"
    data_dir: Path = resolve_data_dir(DEFAULT_DATA_DIR)
    database_url: str = "sqlite://"
    notebooklm_home: Path = Path("~/.config/notebooklm-batch-studio").expanduser()
    http_host: str = "127.0.0.1"
    http_port: int = 8768
    http_allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost")
    http_allowed_origins: tuple[str, ...] = ("http://127.0.0.1:8768", "http://127.0.0.1:8080")
    auto_start_queue: bool = False
    study_root_dir_override: Path | None = None
    legacy_note_studio_dir: Path | None = None
    library_email: str = ""
    library_password: str = field(default="", repr=False)
    openathens_domain: str = ""
    ebsco_profile: str = ""
    chrome_path: str = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    playwright_startup_timeout_seconds: int = 60
    gemini_outline_timeout_seconds: int = 900
    study_categories: str = ""

    @property
    def input_dir(self) -> Path:
        """Folder with files waiting to be processed.

        Returns:
            `<data_dir>/input`.
        """
        return self.data_dir / "input"

    @property
    def output_dir(self) -> Path:
        """Folder for produced results.

        Returns:
            `<data_dir>/output`.
        """
        return self.data_dir / "output"

    @property
    def needs_review_dir(self) -> Path:
        """Quarantine for failed or low-confidence items (batches never stop for them).

        Returns:
            `<data_dir>/needs_review`.
        """
        return self.data_dir / "needs_review"

    @property
    def state_dir(self) -> Path:
        """Folder for progress / resume state.

        Returns:
            `<data_dir>/state`.
        """
        return self.data_dir / "state"

    @property
    def fonts_dir(self) -> Path:
        """Folder for Google Fonts the user downloaded (ADR-009).

        Returns:
            `<data_dir>/fonts`.
        """
        return self.data_dir / "fonts"

    @property
    def logs_dir(self) -> Path:
        """Folder for log files.

        Returns:
            `<data_dir>/logs`.
        """
        return self.data_dir / "logs"

    @property
    def db_dir(self) -> Path:
        """Folder for SQLite database files.

        Returns:
            `<data_dir>/db`.
        """
        return self.data_dir / "db"

    @property
    def courses_input_dir(self) -> Path:
        """Folder for incoming course materials.

        Returns:
            `<data_dir>/input/courses`.
        """
        return self.input_dir / "courses"

    @property
    def courses_output_dir(self) -> Path:
        """Folder for generated course output packages.

        Returns:
            `<data_dir>/output/courses`.
        """
        return self.output_dir / "courses"

    @property
    def study_root_dir(self) -> Path:
        """Root folder for unified `<term>/<subject>/<category>` study directories.

        Returns:
            `STUDY_ROOT_DIR` when configured, otherwise `<data_dir>/study`.
        """
        return self.study_root_dir_override or (self.data_dir / "study")

    @property
    def scratch_dir(self) -> Path:
        """Folder for unprocessed user files (`<data_dir>/scratch`).

        Returns:
            `<data_dir>/scratch`.
        """
        return self.data_dir / "scratch"

    @property
    def literature_dir(self) -> Path:
        """Staging folder for unarchived literature PDFs (`<data_dir>/scratch/literature`).

        Returns:
            `<data_dir>/scratch/literature`.
        """
        return self.scratch_dir / "literature"

    @property
    def literature_browser_profile_dir(self) -> Path:
        """Persistent Chrome profile used for OpenAthens / publisher access.

        Returns:
            `<data_dir>/state/literature_browser_profile`.
        """
        return self.state_dir / "literature_browser_profile"

    @property
    def literature_job_lock_path(self) -> Path:
        """Cross-process OS lock path guarding active background literature jobs.

        Returns:
            `<data_dir>/state/literature_job.lock`.
        """
        return self.state_dir / "literature_job.lock"

    @property
    def gemini_profile_dir(self) -> Path:
        """Persistent Chrome user-data directory for Gemini Web automation.

        Returns:
            `<data_dir>/state/gemini_profile`.
        """
        return self.state_dir / "gemini_profile"

    @property
    def diagnostics_dir(self) -> Path:
        """Directory where adapter diagnostic HTML/screenshots are stored.

        Returns:
            `<data_dir>/logs`.
        """
        return self.logs_dir

    @property
    def deleted_dir(self) -> Path:
        """Recoverable trash folder for deleted course legacy artifacts.

        Returns:
            `<data_dir>/deleted`.
        """
        return self.data_dir / "deleted"

    @property
    def prompt_override_dir(self) -> Path:
        """User override folder for NoteStudio modular `.md` prompt templates.

        Returns:
            `<data_dir>/prompts/modular_specs`.
        """
        return self.data_dir / "prompts" / "modular_specs"

    @property
    def notes_state_dir(self) -> Path:
        """State directory for NoteStudio per-course checkpoints and pause flags.

        Returns:
            `<data_dir>/state/notes`.
        """
        return self.state_dir / "notes"

    @property
    def study_layout(self) -> StudyLayout:
        """Configured study category layout (defaults to `DEFAULT_LAYOUT`).

        Returns:
            `StudyLayout` parsed from `study_categories`, or `DEFAULT_LAYOUT`.
        """
        if self.study_categories.strip():
            return layout_from_names(self.study_categories)
        return DEFAULT_LAYOUT

    def scratch_kind_dir(self, kind: str) -> Path:
        """Return `<scratch_dir>/<kind>` for one of the five fixed scratch categories.

        Args:
            kind: Scratch category (`literature`, `notes`, `outputs`, `uploads`, `unarchived`).

        Returns:
            Path inside `<data_dir>/scratch`.

        Raises:
            ValueError: When `kind` is not one of the allowed `SCRATCH_KINDS`.
        """
        if kind not in SCRATCH_KINDS:
            raise ValueError(f"Unsupported scratch kind {kind!r}; expected one of {SCRATCH_KINDS}")
        return self.scratch_dir / kind

    def ensure_data_dirs(self) -> list[Path]:
        """Create required `study/` and `scratch/<kind>/` data directories idempotently.

        Returns:
            List of created or verified directory paths.
        """
        targets = [
            self.db_dir,
            self.logs_dir,
            self.state_dir,
            self.needs_review_dir,
            self.study_root_dir,
            self.scratch_dir,
            *(self.scratch_kind_dir(kind) for kind in SCRATCH_KINDS),
        ]
        for folder in targets:
            folder.mkdir(parents=True, exist_ok=True)
        return targets


def _csv(value: str) -> tuple[str, ...]:
    """Split a comma-separated setting.

    Args:
        value: Raw text such as `a, b`.

    Returns:
        The non-empty, stripped items.
    """
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _flag(value: str) -> bool:
    """Interpret an environment flag.

    Args:
        value: Raw text such as `1`, `true`, `yes`.

    Returns:
        True for 1 / true / yes / on (case-insensitive).
    """
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env(name: str, default: str = "") -> str:
    """Read one stripped environment variable.

    Args:
        name: Variable name.
        default: Value when the variable is unset.

    Returns:
        The stripped value.
    """
    return os.environ.get(name, default).strip()


def _http_settings() -> dict[str, Any]:
    """Collect HTTP server settings from the environment.

    Returns:
        Keyword arguments for the HTTP fields of `AppConfig`.

    Raises:
        ValueError: When `HTTP_PORT` is not an integer.
    """
    return {
        "http_host": _env("HTTP_HOST", "127.0.0.1"),
        "http_port": int(_env("HTTP_PORT", "8768")),
        "http_allowed_hosts": _csv(_env("HTTP_ALLOWED_HOSTS", "127.0.0.1, localhost")),
        "http_allowed_origins": _csv(
            _env("HTTP_ALLOWED_ORIGINS", "http://127.0.0.1:8768, http://127.0.0.1:8080")
        ),
    }


def _literature_settings() -> dict[str, Any]:
    """Collect library / browser settings, preferring `LIBRARY_*` over the legacy `USER_*` names.

    Returns:
        Keyword arguments for the literature and browser fields of `AppConfig`.

    Raises:
        ValueError: When a timeout setting is not an integer.
    """
    return {
        "library_email": _env("LIBRARY_EMAIL") or _env("USER_EMAIL"),
        "library_password": _env("LIBRARY_PASSWORD") or _env("USER_PASSWORD"),
        "openathens_domain": _env("OPENATHENS_DOMAIN"),
        "ebsco_profile": _env("EBSCO_PROFILE"),
        "chrome_path": _env("CHROME_PATH", AppConfig.chrome_path),
        "playwright_startup_timeout_seconds": int(_env("PLAYWRIGHT_STARTUP_TIMEOUT_SECONDS", "60")),
        "gemini_outline_timeout_seconds": int(_env("GEMINI_OUTLINE_TIMEOUT_SECONDS", "900")),
    }


def _core_settings(data_dir: Path) -> dict[str, Any]:
    """Collect runtime, logging, Ollama, and database settings.

    Args:
        data_dir: Resolved data folder (used for the default SQLite path).

    Returns:
        Keyword arguments for the core fields of `AppConfig`.

    Raises:
        ValueError: When `API_TIMEOUT_SECONDS` is not an integer.
    """
    return {
        "app_env": _env("APP_ENV", "development"),
        "log_level": _env("LOG_LEVEL", "INFO").upper(),
        "log_to_file": _flag(_env("LOG_TO_FILE", "true")),
        "timeout_seconds": int(_env("API_TIMEOUT_SECONDS", "15")),
        "ollama_base_url": _env("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
        "ollama_model": _env("OLLAMA_MODEL", "gemma4:latest"),
        "database_url": _env("DATABASE_URL") or f"sqlite:///{data_dir / 'db' / 'app.db'}",
        "auto_start_queue": _flag(_env("AUTO_START_QUEUE", "true")),
    }


def load_config() -> AppConfig:
    """Read and validate configuration from `.env` and environment variables.

    Returns:
        A populated `AppConfig`.

    Raises:
        ValueError: When a numeric setting is not an integer.
    """
    load_dotenv_file(PROJECT_ROOT / ".env")
    data_dir = resolve_data_dir(os.environ.get("DATA_DIR", DEFAULT_DATA_DIR))
    notebooklm_home = Path(_env("NOTEBOOKLM_HOME", "~/.config/notebooklm-batch-studio")).expanduser()
    os.environ["NOTEBOOKLM_HOME"] = str(notebooklm_home)
    study_root_raw = _env("STUDY_ROOT_DIR")
    legacy_notes_raw = _env("LEGACY_NOTE_STUDIO_DIR")
    return AppConfig(
        data_dir=data_dir,
        notebooklm_home=notebooklm_home,
        study_root_dir_override=resolve_data_dir(study_root_raw) if study_root_raw else None,
        legacy_note_studio_dir=resolve_data_dir(legacy_notes_raw) if legacy_notes_raw else None,
        study_categories=_env("STUDY_CATEGORIES"),
        **_core_settings(data_dir),
        **_http_settings(),
        **_literature_settings(),
    )
