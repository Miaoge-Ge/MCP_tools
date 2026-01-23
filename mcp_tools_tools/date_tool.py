"""Date-related tools."""

from __future__ import annotations

import json
from typing import Any

from mcp_tools_core.tooling import ToolRegistry, register_decorated, tool
from mcp_tools_tools.datetime_common import build_datetime_payload, resolve_now_ms, resolve_timezone


@tool(
    name="get_date",
    title="获取日期详情",
    description="获取当前日期的详细信息",
    input_schema={
        "type": "object",
        "properties": {"tz": {"type": "string"}, "at_ms": {"type": "integer"}, "date_format": {"type": "string"}},
        "required": [],
        "additionalProperties": False,
    },
)
def get_date(_: dict[str, Any]) -> str:
    """Return today's date and derived fields."""
    args: dict[str, Any] = _ if isinstance(_, dict) else {}
    tz = resolve_timezone(str(args.get("tz") or "").strip() or None)
    now_ms = resolve_now_ms(args.get("at_ms") if isinstance(args.get("at_ms"), int) else None)
    date_format = str(args.get("date_format") or "").strip() or "%Y-%m-%d"
    full = build_datetime_payload(now_ms=now_ms, tz=tz, date_format=date_format)
    payload = {k: full[k] for k in ("date", "year", "month", "day", "weekday", "weekday_cn", "day_of_year")}
    return json.dumps(payload, ensure_ascii=False, indent=2)


def register(registry: ToolRegistry) -> None:
    """Register tools in this module."""
    register_decorated(registry, globals())
