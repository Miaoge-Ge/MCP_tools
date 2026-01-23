"""Time-related tools."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from mcp_tools_core.tooling import ToolRegistry, register_decorated, tool


@tool(
    name="now",
    title="获取当前时间",
    description="获取当前时间（UTC ISO 与本地格式）",
    input_schema={"type": "object", "properties": {"tz": {"type": "string"}}, "required": [], "additionalProperties": False},
)
def now(_: dict[str, Any]) -> str:
    """Return current time in ISO (UTC) and locale string formats."""
    d = dt.datetime.now()
    payload = {
        "iso": d.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "locale": d.strftime("%Y/%m/%d %H:%M:%S"),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def register(registry: ToolRegistry) -> None:
    """Register tools in this module."""
    register_decorated(registry, globals())
