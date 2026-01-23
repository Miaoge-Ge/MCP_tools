"""Date-related tools."""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP

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


def _build_datetime_payload(*, now_ms: int, tz: dt.tzinfo, date_format: str = "%Y-%m-%d") -> dict:
    local = dt.datetime.fromtimestamp(now_ms / 1000, tz=tz)
    payload: dict = {
        "date": local.strftime(date_format),
        "year": int(local.year),
        "month": int(local.month),
        "day": int(local.day),
        "weekday": local.strftime("%A"),
        "weekday_cn": _weekday_cn_for(local),
        "day_of_year": _day_of_year_for(local),
    }
    return payload


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="get_date", description="获取当前日期的详细信息")
    def get_date(tz: str | None = None, at_ms: int | None = None, date_format: str = "%Y-%m-%d") -> str:
        tz0 = _resolve_timezone(tz)
        now_ms = _resolve_now_ms(at_ms)
        payload = _build_datetime_payload(now_ms=now_ms, tz=tz0, date_format=date_format)
        return json.dumps(payload, ensure_ascii=False, indent=2)
