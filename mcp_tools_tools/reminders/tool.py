"""Reminder tools and background scheduler."""

from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any

from zoneinfo import ZoneInfo

from mcp_tools_core.env import env
from mcp_tools_core.tooling import ToolRegistry, register_decorated, tool
from mcp_tools_tools.reminders.napcat_http import NapCatHttpSender
from mcp_tools_tools.reminders.parser import (
    is_self_reminder_request,
    parse_reminder_requests,
    pick_mention_user_id_for_request,
)
from mcp_tools_tools.reminders.scheduler import ReminderScheduler
from mcp_tools_tools.reminders.store import ReminderStore


_LOCK = threading.Lock()
_STORE: ReminderStore | None = None
_SENDER: NapCatHttpSender | None = None
_SCHEDULER: ReminderScheduler | None = None


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
    name = str(env("REMINDER_TIMEZONE") or env("TIMEZONE") or "").strip() or "Asia/Shanghai"
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


@tool(
    name="reminder_create",
    title="创建提醒",
    description="创建一个定时提醒（支持 request 或者 due_at_ms+text）",
    input_schema={
        "type": "object",
        "properties": {
            "chat_type": {"type": "string"},
            "user_id": {"type": "string"},
            "group_id": {"type": "string"},
            "message_id": {"type": "string"},
            "request": {"type": "string"},
            "mention_user_id": {"type": "string"},
            "now_ms": {"type": "integer"},
            "due_at_ms": {"type": "integer"},
            "text": {"type": "string"},
        },
        "required": ["chat_type", "user_id"],
        "additionalProperties": False,
    },
)
def reminder_create(args: dict[str, Any]) -> str:
    store, _ = _ensure_runtime()
    chat_type = str(args.get("chat_type") or "")
    user_id = str(args.get("user_id") or "")
    group_id = str(args.get("group_id") or "").strip() if args.get("group_id") is not None else None
    message_id = str(args.get("message_id") or "").strip() if args.get("message_id") is not None else None
    request = str(args.get("request") or "").strip()
    now_ms = int(args.get("now_ms") or int(time.time() * 1000))
    if not chat_type or not user_id:
        return "参数错误：chat_type / user_id 为必填"

    due_at_ms = args.get("due_at_ms")
    text = str(args.get("text") or "").strip()
    parsed = None
    if isinstance(due_at_ms, int) and text:
        parsed = [(int(due_at_ms), text)]
    else:
        if not request:
            return "参数错误：request 为必填（或提供 due_at_ms + text）"
        parsed = parse_reminder_requests(request, now_ms)
        if not parsed:
            return "我没看懂提醒时间。你可以这样说：1分钟后提醒我 喝水 / 在20:30提醒我 下楼拿快递"

    wants_self = is_self_reminder_request(request) if request else True
    mention_from_text = pick_mention_user_id_for_request(request) if request else None
    mention_user_id = str(args.get("mention_user_id") or (user_id if wants_self else (mention_from_text or (user_id if chat_type == "group" else "")))).strip() or None

    target = {"chatType": "private", "userId": user_id} if chat_type == "private" else {"chatType": "group", "groupId": group_id or "unknown"}

    created: list[dict] = []
    for due, msg in parsed:
        created.append(
            store.create(
                {
                    "sourceMessageId": message_id,
                    "dueAtMs": int(due),
                    "creatorUserId": user_id,
                    "creatorChatType": "group" if chat_type == "group" else "private",
                    "creatorGroupId": group_id,
                    "target": target,
                    "mentionUserId": mention_user_id if chat_type == "group" else None,
                    "text": msg,
                }
            )
        )

    if len(created) >= 2:
        times = "、".join([_fmt_hm(int(r.get("dueAtMs") or 0)) for r in created])
        prefix = f"{_format_at(user_id)} " if chat_type == "group" else ""
        who = f"，目标QQ：{mention_user_id}" if (chat_type == "group" and mention_user_id and mention_user_id != user_id) else ""
        return f"{prefix}已设置 {len(created)} 个提醒：{times}{who}，内容：{str(created[0].get('text') or '').strip()}".strip()

    rem = created[0]
    prefix = f"{_format_at(user_id)} " if chat_type == "group" else ""
    who = f"，目标QQ：{mention_user_id}" if (chat_type == "group" and mention_user_id and mention_user_id != user_id) else ""
    return f"{prefix}已设置提醒：{_fmt_time(int(rem.get('dueAtMs') or 0))}{who}，内容：{str(rem.get('text') or '').strip()}".strip()


@tool(
    name="reminder_list",
    title="查看提醒",
    description="列出我创建的待执行提醒",
    input_schema={
        "type": "object",
        "properties": {"chat_type": {"type": "string"}, "user_id": {"type": "string"}, "group_id": {"type": "string"}, "limit": {"type": "integer"}},
        "required": ["chat_type", "user_id"],
        "additionalProperties": False,
    },
)
def reminder_list(args: dict[str, Any]) -> str:
    store, _ = _ensure_runtime()
    chat_type = str(args.get("chat_type") or "")
    user_id = str(args.get("user_id") or "")
    group_id = str(args.get("group_id") or "").strip() if args.get("group_id") is not None else None
    try:
        limit = int(args.get("limit") or 10)
    except Exception:
        limit = 10
    limit = max(1, min(20, limit))
    if not chat_type or not user_id:
        return "参数错误：chat_type / user_id 为必填"
    lst = store.list_pending_by_creator(user_id, "group" if chat_type == "group" else "private", group_id)
    if not lst:
        return "暂无待提醒事项"
    lines: list[str] = []
    for i, r in enumerate(lst[:limit]):
        rid = str(r.get("id") or "")
        lines.append(f"{i + 1}. {_fmt_time(int(r.get('dueAtMs') or 0))}：{str(r.get('text') or '').strip()}（{rid[:8]}）")
    return "待提醒：\n" + "\n".join(lines)


@tool(
    name="reminder_cancel",
    title="取消提醒",
    description="取消我创建的提醒（通过提醒ID前缀）",
    input_schema={
        "type": "object",
        "properties": {"user_id": {"type": "string"}, "reminder_id": {"type": "string"}},
        "required": ["user_id", "reminder_id"],
        "additionalProperties": False,
    },
)
def reminder_cancel(args: dict[str, Any]) -> str:
    store, _ = _ensure_runtime()
    user_id = str(args.get("user_id") or "")
    reminder_id = str(args.get("reminder_id") or "").strip()
    if not user_id or not reminder_id:
        return "参数错误：user_id / reminder_id 为必填"
    rem = store.cancel(user_id, reminder_id)
    if not rem:
        return "未找到要取消的提醒（请提供提醒ID）"
    return "已取消提醒" if str(rem.get("status") or "") == "canceled" else "该提醒已不是待执行状态"


def register(registry: ToolRegistry) -> None:
    """Register tools in this module and ensure the scheduler is running."""
    _ensure_runtime()
    register_decorated(registry, globals())
