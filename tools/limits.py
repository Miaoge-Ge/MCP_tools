from __future__ import annotations

import json
import os
import time
from typing import Any
from zoneinfo import ZoneInfo

_CACHED: dict[str, Any] | None = None
_CACHED_MTIME: float | None = None


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_limits_file() -> str:
    return os.path.join(_project_root(), "tool_limits.json")


def _default_usage_file() -> str:
    return os.path.join(_project_root(), "data", "tool_usage.json")

def _resolve_path_from_root(p: str) -> str:
    raw = str(p or "").strip()
    expanded = os.path.expanduser(raw)
    if os.path.isabs(expanded):
        return os.path.abspath(expanded)
    return os.path.abspath(os.path.join(_project_root(), expanded))


def _load_json_file(path: str) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else None
    except Exception:
        return None


def _atomic_write_json(path: str, obj: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _get_timezone(cfg: dict[str, Any]) -> ZoneInfo:
    tz = str(cfg.get("timezone") or "").strip() or str(os.environ.get("TIMEZONE") or "").strip() or "Asia/Shanghai"
    try:
        return ZoneInfo(tz)
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def load_limits_config() -> dict[str, Any] | None:
    global _CACHED, _CACHED_MTIME
    path0 = str(os.environ.get("MCP_LIMITS_FILE") or "").strip() or _default_limits_file()
    path = _resolve_path_from_root(path0)
    if not os.path.exists(path):
        _CACHED = None
        _CACHED_MTIME = None
        return None
    try:
        mtime = os.path.getmtime(path)
    except Exception:
        mtime = None
    if _CACHED is not None and _CACHED_MTIME is not None and mtime is not None and mtime == _CACHED_MTIME:
        return _CACHED
    cfg = _load_json_file(path)
    _CACHED = cfg
    _CACHED_MTIME = mtime if mtime is not None else None
    return cfg


def _today_key(tz: ZoneInfo) -> str:
    now = time.time()
    local = time.localtime(now)
    try:
        import datetime as dt

        local_dt = dt.datetime.fromtimestamp(now, tz=tz)
        return local_dt.strftime("%Y-%m-%d")
    except Exception:
        return time.strftime("%Y-%m-%d", local)


def _usage_path() -> str:
    path0 = str(os.environ.get("MCP_TOOL_USAGE_FILE") or "").strip() or _default_usage_file()
    return _resolve_path_from_root(path0)


def _load_usage() -> dict[str, Any]:
    path = _usage_path()
    v = _load_json_file(path)
    if not v:
        return {"days": {}}
    if "days" not in v or not isinstance(v.get("days"), dict):
        return {"days": {}}
    return v


def _save_usage(usage: dict[str, Any]) -> None:
    _atomic_write_json(_usage_path(), usage)


def enforce_daily_limits(*, tool_name: str, chat_type: str | None = None, user_id: str | None = None, group_id: str | None = None) -> None:
    cfg = load_limits_config()
    if not cfg:
        return
    limits = cfg.get("limits")
    if not isinstance(limits, dict) or not limits:
        return

    tn = str(tool_name or "").strip()
    if not tn:
        return
    rule = limits.get(tn)
    if not isinstance(rule, dict) or not rule:
        return

    per_day = rule.get("per_day")
    per_user_per_day = rule.get("per_user_per_day")
    try:
        per_day_n = int(per_day) if per_day is not None else None
    except Exception:
        per_day_n = None
    try:
        per_user_n = int(per_user_per_day) if per_user_per_day is not None else None
    except Exception:
        per_user_n = None

    if (per_day_n is None or per_day_n <= 0) and (per_user_n is None or per_user_n <= 0):
        return

    tz = _get_timezone(cfg)
    day = _today_key(tz)
    uid = str(user_id or "").strip() or "unknown"

    usage = _load_usage()
    days = usage.get("days")
    if not isinstance(days, dict):
        days = {}
        usage["days"] = days
    day_obj = days.get(day)
    if not isinstance(day_obj, dict):
        day_obj = {}
        days[day] = day_obj
    tool_obj = day_obj.get(tn)
    if not isinstance(tool_obj, dict):
        tool_obj = {"total": 0, "users": {}}
        day_obj[tn] = tool_obj
    total = int(tool_obj.get("total") or 0)
    users = tool_obj.get("users")
    if not isinstance(users, dict):
        users = {}
        tool_obj["users"] = users
    ucount = int(users.get(uid) or 0)

    if per_day_n is not None and per_day_n > 0 and total >= per_day_n:
        raise ValueError(f"今日 {tn} 已达使用上限（{per_day_n} 次）")
    if per_user_n is not None and per_user_n > 0 and ucount >= per_user_n:
        raise ValueError(f"你今日 {tn} 已达使用上限（{per_user_n} 次）")

    tool_obj["total"] = total + 1
    users[uid] = ucount + 1
    tool_obj["users"] = users
    day_obj[tn] = tool_obj
    days[day] = day_obj
    usage["days"] = days
    _save_usage(usage)
