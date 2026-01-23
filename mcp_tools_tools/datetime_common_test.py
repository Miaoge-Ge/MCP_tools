import datetime as dt
import os
import unittest


class DateTimeCommonTest(unittest.TestCase):
    def test_timezone_changes_local_date(self):
        from mcp_tools_tools.datetime_common import build_datetime_payload, resolve_timezone

        at = int(dt.datetime(2026, 1, 1, 23, 30, tzinfo=dt.timezone.utc).timestamp() * 1000)

        os.environ["TIMEZONE"] = "UTC"
        p_utc = build_datetime_payload(now_ms=at, tz=resolve_timezone(None))
        self.assertEqual(p_utc["date"], "2026-01-01")

        os.environ["TIMEZONE"] = "Asia/Shanghai"
        p_cn = build_datetime_payload(now_ms=at, tz=resolve_timezone(None))
        self.assertEqual(p_cn["date"], "2026-01-02")


if __name__ == "__main__":
    unittest.main()

