"""macOS notifications for things the user should look at in study/ (SPEC-029).

New course folders, whole textbooks waiting to be split, and missing/changed lecture PDFs are each announced
once. Announced keys are kept in `DATA_DIR/state/notified.json`, so restarts do not repeat them; a changed
PDF's key includes its new hash, so a second change is announced again.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TITLE = "Gemini Notebook 學習工作室"
Alert = tuple[str, str, str]


def _issue_alert(issue: dict[str, Any]) -> Alert:
    """Turn one lecture file issue into an alert.

    Args:
        issue: Row from `LectureFileChecker.issues`.

    Returns:
        `(key, title, message)`.
    """
    where = f"{issue['course_name']} 第 {issue['lecture_no']} 講（{issue['filename']}）"
    if issue["issue"] == "missing":
        return (f"missing|{issue['course_code']}|{issue['lecture_no']}", TITLE, f"講義遺失：{where}")
    key = f"changed|{issue['course_code']}|{issue['lecture_no']}|{issue['sha256']}"
    return (key, TITLE, f"講義已更新：{where}，筆記本裡還是舊版")


def collect_alerts(
    folders: list[dict[str, Any]], books: list[dict[str, Any]], issues: list[dict[str, Any]]
) -> list[Alert]:
    """Build alerts from the current findings.

    Args:
        folders: New course folders (`find_new_course_folders`).
        books: Whole textbooks waiting to be split (`pending_textbooks`).
        issues: Missing/changed lecture PDFs.

    Returns:
        `(key, title, message)` tuples.
    """
    alerts: list[Alert] = [
        (
            f"folder|{f['path']}",
            TITLE,
            f"偵測到新課程資料夾：{f['folder']}（{f['term']}），到「批次排程」加入課程",
        )
        for f in folders
    ]
    alerts += [
        (
            f"book|{b['course_code']}|{b['relative_path']}",
            TITLE,
            f"偵測到課本：{Path(b['relative_path']).name}（{b['course_name']}），到「批次排程」預覽並切割",
        )
        for b in books
    ]
    return alerts + [_issue_alert(i) for i in issues]


class AlertNotifier:
    """Send each alert key once, remembering sent keys in a JSON file."""

    def __init__(self, state_path: Path, send: Callable[[str, str], object]) -> None:
        """Bind the memory file and the notification sender.

        Args:
            state_path: `DATA_DIR/state/notified.json`.
            send: `(title, message)` sender injected by the entrypoint (adapter layer).
        """
        self.state_path = state_path
        self.send = send

    def _seen(self) -> set[str]:
        """Read the keys already announced.

        Returns:
            Keys (empty when the file is missing or unreadable).
        """
        try:
            return set(json.loads(self.state_path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return set()

    def notify_new(self, alerts: list[Alert]) -> list[str]:
        """Send alerts whose key has not been announced, then remember them.

        Args:
            alerts: Current alerts.

        Returns:
            Keys announced in this call.
        """
        seen = self._seen()
        fresh = [a for a in alerts if a[0] not in seen]
        for _key, title, message in fresh:
            self.send(title, message)
        if fresh:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_name(self.state_path.name + ".tmp")
            tmp.write_text(
                json.dumps(sorted(seen | {a[0] for a in fresh}), ensure_ascii=False), encoding="utf-8"
            )
            os.replace(tmp, self.state_path)
            logger.info("Sent %d study alerts", len(fresh))
        return [a[0] for a in fresh]
