"""List and prune `DATA_DIR/backups/db-*` database backups; pruning moves, never deletes (SPEC-017)."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.config.settings import AppConfig

logger = logging.getLogger(__name__)

BACKUP_PREFIX = "db-"


def _backups_root(config: AppConfig) -> Path:
    """Return `DATA_DIR/backups`.

    Args:
        config: Application configuration.

    Returns:
        Backups directory path.
    """
    return config.backups_dir


def _dir_size(path: Path) -> int:
    """Sum file sizes under a backup folder (symlinks ignored).

    Args:
        path: Backup directory.

    Returns:
        Total size in bytes.
    """
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink())


def list_backups(config: AppConfig) -> list[dict[str, Any]]:
    """List database backup folders, newest first.

    Args:
        config: Application configuration.

    Returns:
        `[{name, path, size_bytes, modified_at}]` sorted by name descending (names embed the timestamp).
    """
    root = _backups_root(config)
    if not root.is_dir():
        return []
    dirs = [
        p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and p.name.startswith(BACKUP_PREFIX)
    ]
    return [
        {
            "name": p.name,
            "path": str(p),
            "size_bytes": _dir_size(p),
            "modified_at": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
        }
        for p in sorted(dirs, key=lambda p: p.name, reverse=True)
    ]


def _unique_target(target: Path) -> Path:
    """Return `target`, or `target-2`, `target-3`… when the name is taken.

    Args:
        target: Desired destination path.

    Returns:
        A path that does not exist yet.
    """
    candidate, n = target, 2
    while candidate.exists():
        candidate = target.with_name(f"{target.name}-{n}")
        n += 1
    return candidate


def prune_backups(config: AppConfig, keep: int = 5, dry_run: bool = True) -> dict[str, Any]:
    """Keep the newest `keep` backups and move the rest to `DATA_DIR/deleted/backups/`.

    Args:
        config: Application configuration.
        keep: Number of newest backups to keep (at least 1).
        dry_run: Only report what would move when True.

    Returns:
        `{dry_run, keep, kept, to_move, moved, destination}`.

    Raises:
        ValueError: When `keep` is less than 1.
    """
    if keep < 1:
        raise ValueError("至少要保留 1 份備份")
    backups = [b["name"] for b in list_backups(config)]
    kept, to_move = backups[:keep], backups[keep:]
    dest_root = config.deleted_dir / "backups"
    moved: list[str] = []
    if not dry_run and to_move:
        dest_root.mkdir(parents=True, exist_ok=True)
        for name in to_move:
            shutil.move(str(_backups_root(config) / name), str(_unique_target(dest_root / name)))
            moved.append(name)
        logger.info("Moved %d old backups to %s", len(moved), dest_root)
    return {
        "dry_run": dry_run,
        "keep": keep,
        "kept": kept,
        "to_move": to_move,
        "moved": moved,
        "destination": str(dest_root),
    }
