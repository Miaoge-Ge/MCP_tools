import json
import os
import time
import uuid

from mcp_tools_core.env import env, project_abs


def _ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def _atomic_write_json(file_path: str, data: object) -> None:
    _ensure_dir(os.path.dirname(file_path))
    tmp = f"{file_path}.{os.getpid()}.{int(time.time() * 1000)}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, file_path)


def _read_json_file(file_path: str, fallback: object) -> object:
    if not os.path.exists(file_path):
        return fallback
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback


class ReminderStore:
    def __init__(self) -> None:
        data_dir = project_abs(env("DATA_DIR") or "data")
        self._file_path = os.path.join(data_dir, "reminders.json")
        self._lock_dir = os.path.join(data_dir, "reminders.locks")
        self._reminders: list[dict] = []
        self._refresh()

    def _refresh(self) -> None:
        raw = _read_json_file(self._file_path, [])
        self._reminders = raw if isinstance(raw, list) else []

    def _flush(self) -> None:
        _atomic_write_json(self._file_path, self._reminders)

    def _lock_path(self, reminder_id: str) -> str:
        return os.path.join(self._lock_dir, f"{reminder_id}.lock")

    def try_acquire_send_lock(self, reminder_id: str, now_ms: int) -> bool:
        _ensure_dir(self._lock_dir)
        p = self._lock_path(reminder_id)
        stale_ms = 2 * 60_000
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(f"{os.getpid()}\n{now_ms}\n")
            return True
        except FileExistsError:
            try:
                st = os.stat(p)
                if now_ms - int(st.st_mtime * 1000) > stale_ms:
                    try:
                        os.unlink(p)
                    except Exception:
                        return False
                    return self.try_acquire_send_lock(reminder_id, now_ms)
            except Exception:
                return False
            return False

    def release_send_lock(self, reminder_id: str) -> None:
        p = self._lock_path(reminder_id)
        try:
            os.unlink(p)
        except Exception:
            return

    def list_pending_by_creator(self, user_id: str, chat_type: str, group_id: str | None) -> list[dict]:
        self._refresh()
        out: list[dict] = []
        for r in self._reminders:
            if not isinstance(r, dict):
                continue
            if r.get("status") not in ("pending", "sending"):
                continue
            if str(r.get("creatorUserId") or "") != user_id:
                continue
            if chat_type == "private":
                if r.get("creatorChatType") != "private":
                    continue
            else:
                if str(r.get("creatorGroupId") or "") != str(group_id or ""):
                    continue
            out.append(r)
        out.sort(key=lambda x: int(x.get("dueAtMs") or 0))
        return [dict(x) for x in out]

    def claim_due(self, now_ms: int, limit: int) -> list[dict]:
        self._refresh()
        stale_ms = 2 * 60_000
        changed = False
        for r in self._reminders:
            if not isinstance(r, dict):
                continue
            if r.get("status") != "sending":
                continue
            claimed_at = int(r.get("claimedAtMs") or 0)
            if claimed_at and now_ms - claimed_at > stale_ms:
                r["status"] = "pending"
                r.pop("claimedAtMs", None)
                changed = True

        due: list[dict] = []
        for r in self._reminders:
            if not isinstance(r, dict):
                continue
            if r.get("status") != "pending":
                continue
            due_at = int(r.get("dueAtMs") or 0)
            if due_at > now_ms:
                continue
            next_at = r.get("nextAttemptAtMs")
            if next_at is not None and int(next_at or 0) > now_ms:
                continue
            due.append(r)

        due.sort(key=lambda x: int(x.get("dueAtMs") or 0))
        due = due[: max(0, int(limit))]
        for r in due:
            r["status"] = "sending"
            r["claimedAtMs"] = now_ms
            changed = True
        if changed:
            self._flush()
        return [dict(x) for x in due]

    def create(self, opts: dict) -> dict:
        self._refresh()
        source_message_id = str(opts.get("sourceMessageId") or "").strip() if opts.get("sourceMessageId") else None
        if source_message_id:
            for r in self._reminders:
                if not isinstance(r, dict):
                    continue
                if str(r.get("sourceMessageId") or "") != source_message_id:
                    continue
                if str(r.get("creatorUserId") or "") != str(opts.get("creatorUserId") or ""):
                    continue
                if str(r.get("creatorChatType") or "") != str(opts.get("creatorChatType") or ""):
                    continue
                if int(r.get("dueAtMs") or 0) != int(opts.get("dueAtMs") or 0):
                    continue
                if str(r.get("text") or "").strip() != str(opts.get("text") or "").strip():
                    continue
                if str(opts.get("creatorChatType") or "") == "group":
                    if str(r.get("creatorGroupId") or "") != str(opts.get("creatorGroupId") or ""):
                        continue
                return dict(r)

        rem = {
            "id": str(uuid.uuid4()),
            "createdAtMs": int(time.time() * 1000),
            "status": "pending",
            "attempts": 0,
            **opts,
            "text": str(opts.get("text") or "").strip(),
        }
        self._reminders.append(rem)
        self._flush()
        return dict(rem)

    def cancel(self, user_id: str, reminder_id: str) -> dict | None:
        self._refresh()
        key = str(reminder_id or "").strip()
        if not key:
            return None
        exact = None
        for r in self._reminders:
            if not isinstance(r, dict):
                continue
            if str(r.get("id") or "") == key and str(r.get("creatorUserId") or "") == user_id:
                exact = r
                break
        rem = exact
        if rem is None and len(key) < 36:
            for r in self._reminders:
                if not isinstance(r, dict):
                    continue
                if str(r.get("creatorUserId") or "") != user_id:
                    continue
                rid = str(r.get("id") or "")
                if rid.startswith(key):
                    rem = r
                    break
        if rem is None:
            return None
        if rem.get("status") not in ("pending", "sending"):
            return dict(rem)
        rem["status"] = "canceled"
        rem["canceledAtMs"] = int(time.time() * 1000)
        rem.pop("nextAttemptAtMs", None)
        rem.pop("claimedAtMs", None)
        self.release_send_lock(str(rem.get("id") or ""))
        self._flush()
        return dict(rem)

    def mark_sent(self, reminder_id: str) -> None:
        self._refresh()
        for r in self._reminders:
            if not isinstance(r, dict):
                continue
            if str(r.get("id") or "") != reminder_id:
                continue
            r["status"] = "sent"
            r["sentAtMs"] = int(time.time() * 1000)
            r.pop("lastError", None)
            r.pop("nextAttemptAtMs", None)
            r.pop("claimedAtMs", None)
            self.release_send_lock(reminder_id)
            self._flush()
            return

    def mark_failed(self, reminder_id: str, error: str) -> None:
        self._refresh()
        for r in self._reminders:
            if not isinstance(r, dict):
                continue
            if str(r.get("id") or "") != reminder_id:
                continue
            r["status"] = "pending"
            r["attempts"] = int(r.get("attempts") or 0) + 1
            r["lastError"] = str(error or "send_failed")
            r["nextAttemptAtMs"] = int(time.time() * 1000) + 10_000
            r.pop("claimedAtMs", None)
            self.release_send_lock(reminder_id)
            self._flush()
            return

