"""Date-related tools."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from mcp_tools_core.tooling import ToolRegistry, register_decorated, tool


@tool(
    name="get_date",
    title="获取日期详情",
    description="获取当前日期的详细信息",
    input_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
)
def get_date(_: dict[str, Any]) -> str:
    """Return today's date and derived fields."""
    now = dt.datetime.now()
    weekday_cn = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"][int(now.strftime("%w"))]
    start = dt.datetime(now.year, 1, 1)
    day_of_year = int((now - start).total_seconds() // 86400) + 1
    payload = {
        "date": now.strftime("%Y-%m-%d"),
        "year": now.year,
        "month": now.month,
        "day": now.day,
        "weekday": now.strftime("%A"),
        "weekday_cn": weekday_cn,
        "day_of_year": day_of_year,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def register(registry: ToolRegistry) -> None:
    """Register tools in this module."""
    register_decorated(registry, globals())
