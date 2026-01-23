import os
import time
import unittest


class ReminderParserTimezoneTest(unittest.TestCase):
    def test_parse_today_hm_respects_timezone(self):
        os.environ["REMINDER_TIMEZONE"] = "Asia/Shanghai"
        from mcp_tools_tools.reminders import parser

        now_ms = int(time.time() * 1000)
        due, msg = parser.parse_reminder_requests("在20:30提醒我 喝水", now_ms)[0]
        self.assertIsInstance(due, int)
        self.assertGreater(due, now_ms)
        self.assertEqual(msg, "喝水")


if __name__ == "__main__":
    unittest.main()

