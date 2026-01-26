from __future__ import annotations

import json
import os
import time
from typing import Any

from tools.limits import enforce_daily_limits

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
                if len(val) >= 2 and (
                    (val[0] == val[-1] and val[0] in ("'", '"')) or (val[0] == "`" and val[-1] == "`")
                ):
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
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_state_path() -> str:
    return os.path.join(_project_root(), "data", "power_state.json")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _parse_admin_ids() -> set[str]:
    raw = str(_env("BOT_ADMIN_QQ_IDS") or "").strip()
    if not raw:
        return set()
    parts = [p.strip() for p in raw.replace("，", ",").split(",")]
    return {p for p in parts if p}


def _parse_allowed_groups() -> set[str] | None:
    raw = str(_env("BOT_POWER_GROUP_IDS") or "").strip()
    if not raw:
        return None
    parts = [p.strip() for p in raw.replace("，", ",").split(",")]
    out = {p for p in parts if p}
    return out or None


def _state_path() -> str:
    p = str(_env("BOT_POWER_STATE_FILE") or "").strip()
    if not p:
        return _default_state_path()
    expanded = os.path.expanduser(p)
    if os.path.isabs(expanded):
        return os.path.abspath(expanded)
    return os.path.abspath(os.path.join(_project_root(), expanded))


def _read_state() -> dict[str, Any]:
    path = _state_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            v = json.load(f)
            if isinstance(v, dict):
                return v
    except Exception:
        return {"groups": {}}
    return {"groups": {}}


def _atomic_write_json(path: str, obj: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _write_state(state: dict[str, Any]) -> None:
    path = _state_path()
    _atomic_write_json(path, state)


def _require_group(chat_type: str, group_id: str | None) -> str:
    ct = str(chat_type or "").strip().lower()
    if ct != "group":
        raise ValueError("仅支持群聊")
    gid = str(group_id or "").strip()
    if not gid:
        raise ValueError("缺少 group_id")
    allowed = _parse_allowed_groups()
    if allowed is not None and gid not in allowed:
        raise ValueError("该群未启用此功能")
    return gid


def _require_admin(user_id: str | None) -> str:
    uid = str(user_id or "").strip()
    if not uid:
        raise ValueError("缺少 user_id")
    admins = _parse_admin_ids()
    if not admins:
        raise ValueError("未配置管理员账号")
    if uid not in admins:
        raise ValueError("无权限")
    return uid


def _cleanup_expired(groups: dict[str, Any], now_ms: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for gid, v in (groups or {}).items():
        try:
            until_ms = int((v or {}).get("until_ms"))
        except Exception:
            continue
        if until_ms > now_ms:
            out[str(gid)] = v
    return out


def _get_group_status(group_id: str) -> dict[str, Any]:
    now = _now_ms()
    st = _read_state()
    groups = st.get("groups") if isinstance(st.get("groups"), dict) else {}
    groups2 = _cleanup_expired(groups, now)
    if groups2 != groups:
        st["groups"] = groups2
        _write_state(st)
    item = groups2.get(group_id)
    until_ms = int(item.get("until_ms")) if isinstance(item, dict) and "until_ms" in item else 0
    muted = until_ms > now
    return {"group_id": group_id, "muted": bool(muted), "until_ms": until_ms if muted else 0, "remaining_ms": int(max(0, until_ms - now)) if muted else 0}


def power_off_group(*, chat_type: str, group_id: str, user_id: str, hours: float) -> dict[str, Any]:
    gid = _require_group(chat_type, group_id)
    uid = _require_admin(user_id)
    h = float(hours) if hours is not None else 0.0
    if not (h > 0):
        raise ValueError("hours 必须大于 0")
    if h > 720:
        raise ValueError("hours 不能超过 720")
    now = _now_ms()
    until = now + int(h * 3600_000)
    st = _read_state()
    groups = st.get("groups") if isinstance(st.get("groups"), dict) else {}
    groups2 = _cleanup_expired(groups, now)
    groups2[gid] = {"until_ms": int(until), "by": uid, "at_ms": int(now)}
    st["groups"] = groups2
    _write_state(st)
    return _get_group_status(gid)


def power_on_group(*, chat_type: str, group_id: str, user_id: str) -> dict[str, Any]:
    gid = _require_group(chat_type, group_id)
    _require_admin(user_id)
    now = _now_ms()
    st = _read_state()
    groups = st.get("groups") if isinstance(st.get("groups"), dict) else {}
    groups2 = _cleanup_expired(groups, now)
    if gid in groups2:
        groups2.pop(gid, None)
        st["groups"] = groups2
        _write_state(st)
    return _get_group_status(gid)


def register(mcp) -> None:
    @mcp.tool(name="bot_power_off", description="群聊关机：在指定群内一段时间不再回复任何人（仅管理员）")
    def bot_power_off(chat_type: str, group_id: str, user_id: str, hours: float) -> str:
        try:
            enforce_daily_limits(tool_name="bot_power_off", chat_type=chat_type, user_id=user_id, group_id=group_id)
            res = power_off_group(chat_type=chat_type, group_id=group_id, user_id=user_id, hours=hours)
            return json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"错误：{e}"

    @mcp.tool(name="bot_power_on", description="群聊开机：解除指定群的关机状态（仅管理员）")
    def bot_power_on(chat_type: str, group_id: str, user_id: str) -> str:
        try:
            enforce_daily_limits(tool_name="bot_power_on", chat_type=chat_type, user_id=user_id, group_id=group_id)
            res = power_on_group(chat_type=chat_type, group_id=group_id, user_id=user_id)
            return json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"错误：{e}"

    @mcp.tool(name="bot_power_status", description="查询指定群是否处于关机状态")
    def bot_power_status(chat_type: str, group_id: str, user_id: str | None = None) -> str:
        try:
            enforce_daily_limits(tool_name="bot_power_status", chat_type=chat_type, user_id=user_id, group_id=group_id)
            gid = _require_group(chat_type, group_id)
            res = _get_group_status(gid)
            return json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"错误：{e}"
