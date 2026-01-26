"""Time-related tools."""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP

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


def _resolve_timezone(tz: str | None) -> dt.tzinfo:
    name = str(tz or "").strip() or str(_env("TIMEZONE") or "").strip() or "Asia/Shanghai"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def _resolve_now_ms(at_ms: int | None) -> int:
    return int(at_ms) if isinstance(at_ms, int) else int(time.time() * 1000)


def _weekday_cn_for(d: dt.datetime) -> str:
    return ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"][int(d.strftime("%w"))]


def _day_of_year_for(d: dt.datetime) -> int:
    start = dt.datetime(d.year, 1, 1, tzinfo=d.tzinfo)
    return int((d - start).total_seconds() // 86400) + 1


def _build_datetime_payload(
    *,
    now_ms: int,
    tz: dt.tzinfo,
    locale_format: str = "%Y/%m/%d %H:%M:%S",
    date_format: str = "%Y-%m-%d",
    include_weekday: bool = True,
    include_weekday_cn: bool = True,
    include_day_of_year: bool = True,
) -> dict:
    local = dt.datetime.fromtimestamp(now_ms / 1000, tz=tz)
    utc = local.astimezone(dt.timezone.utc)
    payload: dict = {
        "tz": str(getattr(tz, "key", None) or tz),
        "epoch_ms": int(now_ms),
        "iso_utc": utc.isoformat().replace("+00:00", "Z"),
        "local": local.strftime(locale_format),
        "date": local.strftime(date_format),
        "year": int(local.year),
        "month": int(local.month),
        "day": int(local.day),
    }
    if include_weekday:
        payload["weekday"] = local.strftime("%A")
    if include_weekday_cn:
        payload["weekday_cn"] = _weekday_cn_for(local)
    if include_day_of_year:
        payload["day_of_year"] = _day_of_year_for(local)
    return payload


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="datetime_now", description="获取当前日期与时间（支持时区），返回结构化字段")
    def datetime_now(
        tz: str | None = None,
        at_ms: int | None = None,
        locale_format: str = "%Y/%m/%d %H:%M:%S",
        date_format: str = "%Y-%m-%d",
        include_weekday: bool = True,
        include_weekday_cn: bool = True,
        include_day_of_year: bool = True,
        chat_type: str | None = None,
        user_id: str | None = None,
        group_id: str | None = None,
    ) -> str:
        try:
            enforce_daily_limits(tool_name="datetime_now", chat_type=chat_type, user_id=user_id, group_id=group_id)
        except Exception as e:
            return f"错误：{e}"
        tz0 = _resolve_timezone(tz)
        now_ms = _resolve_now_ms(at_ms)
        payload = _build_datetime_payload(
            now_ms=now_ms,
            tz=tz0,
            locale_format=locale_format,
            date_format=date_format,
            include_weekday=include_weekday,
            include_weekday_cn=include_weekday_cn,
            include_day_of_year=include_day_of_year,
        )
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @mcp.tool(name="now", description="获取当前时间（UTC ISO 与本地时间字符串，可选时区）")
    def now(
        tz: str | None = None,
        at_ms: int | None = None,
        locale_format: str = "%Y/%m/%d %H:%M:%S",
        chat_type: str | None = None,
        user_id: str | None = None,
        group_id: str | None = None,
    ) -> str:
        try:
            enforce_daily_limits(tool_name="now", chat_type=chat_type, user_id=user_id, group_id=group_id)
        except Exception as e:
            return f"错误：{e}"
        tz0 = _resolve_timezone(tz)
        now_ms = _resolve_now_ms(at_ms)
        payload = _build_datetime_payload(
            now_ms=now_ms,
            tz=tz0,
            locale_format=locale_format,
            include_weekday=False,
            include_weekday_cn=False,
            include_day_of_year=False,
        )
        out = {"iso": payload["iso_utc"], "locale": payload["local"], "tz": payload["tz"], "epoch_ms": payload["epoch_ms"]}
        return json.dumps(out, ensure_ascii=False, indent=2)
