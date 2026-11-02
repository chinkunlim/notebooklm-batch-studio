"""Configuration layer: the ONLY layer allowed to read environment variables.

Loads settings once at startup into an immutable `AppConfig` so every other layer
receives plain values instead of touching `os.environ`.

Data lives OUTSIDE the project folder: `DATA_DIR` holds
input/, output/, needs_review/, state/, db/ and logs/. The project folder only holds code,
docs and small test fixtures. A relative `DATA_DIR` is resolved from the project folder (never
from the current working directory), so the project and its data can be moved together.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = "../../projects-data/notebooklm-batch-studio"


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


def load_config() -> AppConfig:
    """Read and validate configuration from `.env` and environment variables.

    Returns:
        A populated `AppConfig`.

    Raises:
        ValueError: When a numeric setting is not an integer.
    """
    load_dotenv_file(PROJECT_ROOT / ".env")
    data_dir = resolve_data_dir(os.environ.get("DATA_DIR", DEFAULT_DATA_DIR))
    notebooklm_home = Path(
        os.environ.get("NOTEBOOKLM_HOME", "~/.config/notebooklm-batch-studio")
    ).expanduser()
    os.environ["NOTEBOOKLM_HOME"] = str(notebooklm_home)
    return AppConfig(
        app_env=os.environ.get("APP_ENV", "development").strip(),
        log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper(),
        log_to_file=_flag(os.environ.get("LOG_TO_FILE", "true")),
        timeout_seconds=int(os.environ.get("API_TIMEOUT_SECONDS", "15")),
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "gemma4:latest").strip(),
        data_dir=data_dir,
        database_url=os.environ.get("DATABASE_URL", "").strip() or f"sqlite:///{data_dir / 'db' / 'app.db'}",
        notebooklm_home=notebooklm_home,
        http_host=os.environ.get("HTTP_HOST", "127.0.0.1").strip(),
        http_port=int(os.environ.get("HTTP_PORT", "8768")),
        http_allowed_hosts=_csv(os.environ.get("HTTP_ALLOWED_HOSTS", "127.0.0.1, localhost")),
        http_allowed_origins=_csv(
            os.environ.get("HTTP_ALLOWED_ORIGINS", "http://127.0.0.1:8768, http://127.0.0.1:8080")
        ),
        auto_start_queue=_flag(os.environ.get("AUTO_START_QUEUE", "true")),
    )
