"""Reminder tools and background scheduler."""

from __future__ import annotations

import datetime as dt
import os
import threading
import time
from typing import Any

from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP
from .napcat_http import NapCatHttpSender
from .parser import (
    is_self_reminder_request,
    parse_reminder_requests,
    pick_mention_user_id_for_request,
)
from .scheduler import ReminderScheduler
from .store import ReminderStore
from tools.limits import enforce_daily_limits


_LOCK = threading.Lock()
_STORE: ReminderStore | None = None
_SENDER: NapCatHttpSender | None = None
_SCHEDULER: ReminderScheduler | None = None


_ENV_BOOTSTRAPPED = False


def _load_dotenv_file(file_path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for raw in f.read().splitlines():
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                key = k.strip()
                if not key:
                    continue
                val = v.strip()
                if len(val) >= 2 and ((val[0] == val[-1] and val[0] in ("'", '"')) or (val[0] == "`" and val[-1] == "`")):
                    val = val[1:-1].strip()
                out[key] = val
    except Exception:
        return {}
    return out


def _bootstrap_env() -> None:
    global _ENV_BOOTSTRAPPED
    if _ENV_BOOTSTRAPPED:
        return
    _ENV_BOOTSTRAPPED = True
    explicit = str(os.environ.get("MCP_TOOLS_ENV_FILE") or "").strip()
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env_file = explicit or os.path.join(root, ".env")
    if not os.path.exists(env_file):
        return
    parsed = _load_dotenv_file(env_file)
    for k, v in parsed.items():
        if k not in os.environ:
            os.environ[k] = v


def _env(name: str) -> str | None:
    _bootstrap_env()
    v = os.environ.get(name)
    if not v:
        return None
    s = str(v).strip()
    return s or None


def _ensure_runtime() -> tuple[ReminderStore, NapCatHttpSender]:
    global _STORE, _SENDER, _SCHEDULER
    with _LOCK:
        if _STORE is None:
            _STORE = ReminderStore()
        if _SENDER is None:
            _SENDER = NapCatHttpSender()
        if _SCHEDULER is None:
            _SCHEDULER = ReminderScheduler(_STORE, _SENDER)
            _SCHEDULER.start()
        return _STORE, _SENDER


def _tz() -> dt.tzinfo:
    name = str(_env("REMINDER_TIMEZONE") or _env("TIMEZONE") or "").strip() or "Asia/Shanghai"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def _fmt_time(ms: int) -> str:
    d = dt.datetime.fromtimestamp(ms / 1000, tz=_tz())
    return d.strftime("%Y/%m/%d %H:%M:%S")


def _fmt_hm(ms: int) -> str:
    d = dt.datetime.fromtimestamp(ms / 1000, tz=_tz())
    return d.strftime("%H:%M")


def _format_at(user_id: str) -> str:
    i = str(user_id or "").strip()
    return f"[CQ:at,qq={i}]" if i else ""

def register(mcp: FastMCP) -> None:
    _ensure_runtime()

    @mcp.tool(name="reminder_create", description="创建一个定时提醒（支持 request 或者 due_at_ms+text）")
    def reminder_create(
        chat_type: str,
        user_id: str,
        group_id: str | None = None,
        message_id: str | None = None,
        request: str | None = None,
        mention_user_id: str | None = None,
        now_ms: int | None = None,
        due_at_ms: int | None = None,
        text: str | None = None,
    ) -> str:
        try:
            enforce_daily_limits(tool_name="reminder_create", chat_type=chat_type, user_id=user_id, group_id=group_id)
        except Exception as e:
            return f"错误：{e}"
        store, _ = _ensure_runtime()
        chat_type0 = str(chat_type or "").strip()
        user_id0 = str(user_id or "").strip()
        group_id0 = str(group_id or "").strip() if group_id is not None else None
        message_id0 = str(message_id or "").strip() if message_id is not None else None
        request0 = str(request or "").strip()
        now0 = int(now_ms or int(time.time() * 1000))
        if not chat_type0 or not user_id0:
            return "参数错误：chat_type / user_id 为必填"

        parsed: list[tuple[int, str]] | None = None
        text0 = str(text or "").strip()
        if isinstance(due_at_ms, int) and text0:
            parsed = [(int(due_at_ms), text0)]
        else:
            if not request0:
                return "参数错误：request 为必填（或提供 due_at_ms + text）"
            parsed = parse_reminder_requests(request0, now0)
            if not parsed:
                return "我没看懂提醒时间。你可以这样说：1分钟后提醒我 喝水 / 在20:30提醒我 下楼拿快递"

        wants_self = is_self_reminder_request(request0) if request0 else True
        mention_from_text = pick_mention_user_id_for_request(request0) if request0 else None
        mention_user_id0 = (
            str(mention_user_id or (user_id0 if wants_self else (mention_from_text or (user_id0 if chat_type0 == "group" else ""))))
            .strip()
            or None
        )

        target = {"chatType": "private", "userId": user_id0} if chat_type0 == "private" else {"chatType": "group", "groupId": group_id0 or "unknown"}

        created: list[dict] = []
        for due, msg in parsed:
            created.append(
                store.create(
                    {
                        "sourceMessageId": message_id0,
                        "dueAtMs": int(due),
                        "creatorUserId": user_id0,
                        "creatorChatType": "group" if chat_type0 == "group" else "private",
                        "creatorGroupId": group_id0,
                        "target": target,
                        "mentionUserId": mention_user_id0 if chat_type0 == "group" else None,
                        "text": msg,
                    }
                )
            )

        if len(created) >= 2:
            times = "、".join([_fmt_hm(int(r.get("dueAtMs") or 0)) for r in created])
            prefix = f"{_format_at(user_id0)} " if chat_type0 == "group" else ""
            who = f"，目标QQ：{mention_user_id0}" if (chat_type0 == "group" and mention_user_id0 and mention_user_id0 != user_id0) else ""
            return f"{prefix}已设置 {len(created)} 个提醒：{times}{who}，内容：{str(created[0].get('text') or '').strip()}".strip()

        rem = created[0]
        prefix = f"{_format_at(user_id0)} " if chat_type0 == "group" else ""
        who = f"，目标QQ：{mention_user_id0}" if (chat_type0 == "group" and mention_user_id0 and mention_user_id0 != user_id0) else ""
        return f"{prefix}已设置提醒：{_fmt_time(int(rem.get('dueAtMs') or 0))}{who}，内容：{str(rem.get('text') or '').strip()}".strip()

    @mcp.tool(name="reminder_list", description="列出我创建的待执行提醒")
    def reminder_list(chat_type: str, user_id: str, group_id: str | None = None, limit: int = 10) -> str:
        try:
            enforce_daily_limits(tool_name="reminder_list", chat_type=chat_type, user_id=user_id, group_id=group_id)
        except Exception as e:
            return f"错误：{e}"
        store, _ = _ensure_runtime()
        chat_type0 = str(chat_type or "").strip()
        user_id0 = str(user_id or "").strip()
        group_id0 = str(group_id or "").strip() if group_id is not None else None
        limit0 = max(1, min(20, int(limit or 10)))
        if not chat_type0 or not user_id0:
            return "参数错误：chat_type / user_id 为必填"
        lst = store.list_pending_by_creator(user_id0, "group" if chat_type0 == "group" else "private", group_id0)
        if not lst:
            return "暂无待提醒事项"
        lines: list[str] = []
        for i, r in enumerate(lst[:limit0]):
            rid = str(r.get("id") or "")
            lines.append(f"{i + 1}. {_fmt_time(int(r.get('dueAtMs') or 0))}：{str(r.get('text') or '').strip()}（{rid[:8]}）")
        return "待提醒：\n" + "\n".join(lines)

    @mcp.tool(name="reminder_cancel", description="取消我创建的提醒（通过提醒ID前缀）")
    def reminder_cancel(user_id: str, reminder_id: str) -> str:
        try:
            enforce_daily_limits(tool_name="reminder_cancel", chat_type=None, user_id=user_id, group_id=None)
        except Exception as e:
            return f"错误：{e}"
        store, _ = _ensure_runtime()
        user_id0 = str(user_id or "").strip()
        reminder_id0 = str(reminder_id or "").strip()
        if not user_id0 or not reminder_id0:
            return "参数错误：user_id / reminder_id 为必填"
        rem = store.cancel(user_id0, reminder_id0)
        if not rem:
            return "未找到要取消的提醒（请提供提醒ID）"
        return "已取消提醒" if str(rem.get("status") or "") == "canceled" else "该提醒已不是待执行状态"
