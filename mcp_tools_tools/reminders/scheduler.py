import threading
import time

from mcp_tools_tools.reminders.napcat_http import NapCatHttpSender
from mcp_tools_tools.reminders.store import ReminderStore


def _format_mention(mention_user_id: str | None) -> str | None:
    i = str(mention_user_id or "").strip()
    return f"[CQ:at,qq={i}]" if i else None


class ReminderScheduler(threading.Thread):
    def __init__(self, store: ReminderStore, sender: NapCatHttpSender) -> None:
        super().__init__(daemon=True)
        self._stop = threading.Event()
        self._store = store
        self._sender = sender

    def run(self) -> None:
        while not self._stop.is_set():
            self._tick()
            time.sleep(1.0)

    def stop(self) -> None:
        self._stop.set()

    def _tick(self) -> None:
        now = int(time.time() * 1000)
        due = self._store.claim_due(now, 10)
        if not due:
            return
        for rem in due:
            rid = str(rem.get("id") or "")
            if not rid:
                continue
            if not self._store.try_acquire_send_lock(rid, now):
                continue
            try:
                prefix = _format_mention(str(rem.get("mentionUserId") or "").strip() or None)
                text = f"{(prefix + ' ') if prefix else ''}提醒：{str(rem.get('text') or '').strip()}".strip()
                target = rem.get("target") if isinstance(rem.get("target"), dict) else {}
                self._sender.send(target, text)
                self._store.mark_sent(rid)
            except Exception as e:
                self._store.mark_failed(rid, str(e))
            finally:
                self._store.release_send_lock(rid)

