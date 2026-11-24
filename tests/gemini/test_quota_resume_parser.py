"""Tests for Gemini quota reset time parsing and fallback (note-studio SPEC-019, note-studio ISSUE-065)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from notebooklm_batch_studio.domain.quota_parser import parse_quota_resume_time


class QuotaResumeParserTest(unittest.TestCase):
    """驗證 Quota 額度用完時間解析、1 小時保底與請求阻擋機制。"""

    def setUp(self) -> None:
        self.base_time = datetime(2026, 11, 12, 11, 50, 0, tzinfo=timezone.utc)

    def test_parse_chinese_pm_time(self) -> None:
        """解析繁中「額度已用完。請於下午 2:15 後再試。」為當日 14:15。"""
        text = "額度已用完。請於下午 2:15 後再試。"
        res = parse_quota_resume_time(text, now=self.base_time, local_tz=timezone.utc)
        self.assertEqual(res, datetime(2026, 11, 12, 14, 15, 0, tzinfo=timezone.utc))

    def test_parse_chinese_am_time(self) -> None:
        """解析「請於上午 10:00 後再試」為當日 10:00（若時間在過去則為次日）。"""
        # base_time is 08:00
        now = datetime(2026, 11, 12, 8, 0, 0, tzinfo=timezone.utc)
        text = "請於上午 10:00 後再試"
        res = parse_quota_resume_time(text, now=now, local_tz=timezone.utc)
        self.assertEqual(res, datetime(2026, 11, 12, 10, 0, 0, tzinfo=timezone.utc))

    def test_parse_english_pm_am_time(self) -> None:
        """解析英文「Try again at 2:15 PM」與「10:00 AM」。"""
        text_pm = "You have reached your limit. Try again at 2:15 PM."
        res_pm = parse_quota_resume_time(text_pm, now=self.base_time, local_tz=timezone.utc)
        self.assertEqual(res_pm, datetime(2026, 11, 12, 14, 15, 0, tzinfo=timezone.utc))

        now_early = datetime(2026, 11, 12, 9, 0, 0, tzinfo=timezone.utc)
        text_am = "Try again at 10:00 AM"
        res_am = parse_quota_resume_time(text_am, now=now_early, local_tz=timezone.utc)
        self.assertEqual(res_am, datetime(2026, 11, 12, 10, 0, 0, tzinfo=timezone.utc))

    def test_parse_tomorrow_time(self) -> None:
        """解析「明天」與「tomorrow」時間為次日。"""
        text = "Try again tomorrow at 9:00 AM"
        res = parse_quota_resume_time(text, now=self.base_time, local_tz=timezone.utc)
        self.assertEqual(res, datetime(2026, 11, 13, 9, 0, 0, tzinfo=timezone.utc))

        text_zh = "請於明天下午 2:15 後再試"
        res_zh = parse_quota_resume_time(text_zh, now=self.base_time, local_tz=timezone.utc)
        self.assertEqual(res_zh, datetime(2026, 11, 13, 14, 15, 0, tzinfo=timezone.utc))

    def test_parse_24hour_time(self) -> None:
        """解析 24 小時制時間「請於 14:15 後再試」。"""
        text = "請於 14:15 後再試"
        res = parse_quota_resume_time(text, now=self.base_time, local_tz=timezone.utc)
        self.assertEqual(res, datetime(2026, 11, 12, 14, 15, 0, tzinfo=timezone.utc))

    def test_parse_relative_minutes(self) -> None:
        """解析相對時間「45 分鐘後」或「in 30 minutes」。"""
        text = "Try again in 30 minutes"
        res = parse_quota_resume_time(text, now=self.base_time, local_tz=timezone.utc)
        self.assertEqual(res, self.base_time + timedelta(minutes=30))

        text_zh = "請於 45 分鐘後再試"
        res_zh = parse_quota_resume_time(text_zh, now=self.base_time, local_tz=timezone.utc)
        self.assertEqual(res_zh, self.base_time + timedelta(minutes=45))

    def test_parse_unparseable_defaults_to_one_hour(self) -> None:
        """無法解析時間文字時，預設保底為 1 小時（3600 秒），不可為 60 秒。"""
        text = "Limit reached. Please try again later."
        res = parse_quota_resume_time(text, now=self.base_time, local_tz=timezone.utc)
        self.assertEqual(res, self.base_time + timedelta(hours=1))

        empty_res = parse_quota_resume_time("", now=self.base_time, local_tz=timezone.utc)
        self.assertEqual(empty_res, self.base_time + timedelta(hours=1))

    def test_past_time_rolls_to_tomorrow(self) -> None:
        """當解析出的時間小於當前時間時，自動順延至次日。"""
        # base_time is 11:50, text says 10:00 (past)
        text = "請於上午 10:00 後再試"
        res = parse_quota_resume_time(text, now=self.base_time, local_tz=timezone.utc)
        self.assertEqual(res, datetime(2026, 11, 13, 10, 0, 0, tzinfo=timezone.utc))

    def test_web_driver_assert_quota_available_extracts_and_parses_time(self) -> None:
        """驗證 WebDriver.assert_quota_available 能從橫幅解析出恢復時間並附於異常中。"""
        from notebooklm_batch_studio.adapters.gemini.web_driver import (
            GeminiQuotaExceededError,
            GeminiWebDriver,
        )

        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.first.is_visible.return_value = True
        mock_locator.first.inner_text.return_value = "額度已用完。請於下午 2:15 後再試。"
        mock_page.locator.return_value = mock_locator

        driver = GeminiWebDriver(
            page=mock_page,
            selectors={"quota_warning_banner": ".limit-reached"},
        )

        with self.assertRaises(GeminiQuotaExceededError) as ctx:
            driver.assert_quota_available()

        err = ctx.exception
        self.assertIn("額度已用完", str(err))
        self.assertIsNotNone(err.resume_after)
        # 「下午 2:15」是本機當地時間（note-studio ISSUE-065 時區修正）；轉回本機時區比對
        local = err.resume_after.astimezone()
        self.assertEqual((local.hour, local.minute), (14, 15))


class QuotaLocalTimezoneTest(unittest.TestCase):
    """Gemini 顯示的是使用者當地時間；時鐘時間必須依當地時區換算（台灣 UTC+8）。"""

    def test_clock_time_is_read_as_local_time(self) -> None:
        """台灣 14:00 時看到「下午 2:15」，恢復時間是台灣 14:15（UTC 06:15），不是 UTC 14:15。"""
        taipei = timezone(timedelta(hours=8))
        now = datetime(2026, 11, 12, 6, 0, 0, tzinfo=timezone.utc)  # 台灣 14:00
        res = parse_quota_resume_time("你的額度將於下午 2:15 重設", now=now, local_tz=taipei)
        self.assertEqual(res, datetime(2026, 11, 12, 6, 15, 0, tzinfo=timezone.utc))

    def test_local_time_already_passed_rolls_to_next_local_day(self) -> None:
        """台灣 15:00 時看到「2:15 PM」，表示明天台灣 14:15（UTC 06:15 次日）。"""
        taipei = timezone(timedelta(hours=8))
        now = datetime(2026, 11, 12, 7, 0, 0, tzinfo=timezone.utc)  # 台灣 15:00
        res = parse_quota_resume_time("You can try again at 2:15 PM", now=now, local_tz=taipei)
        self.assertEqual(res, datetime(2026, 11, 13, 6, 15, 0, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
