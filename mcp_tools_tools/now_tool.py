"""Time-related tools."""

from __future__ import annotations

import json
from typing import Any

from mcp_tools_core.tooling import ToolRegistry, register_decorated, tool
from mcp_tools_tools.datetime_common import build_datetime_payload, resolve_now_ms, resolve_timezone


@tool(
    name="datetime_now",
    title="获取日期与时间",
    description="获取当前日期与时间（支持时区），返回结构化字段",
    input_schema={
        "type": "object",
        "properties": {
            "tz": {"type": "string"},
            "at_ms": {"type": "integer"},
            "locale_format": {"type": "string"},
            "date_format": {"type": "string"},
            "include_weekday": {"type": "boolean"},
            "include_weekday_cn": {"type": "boolean"},
            "include_day_of_year": {"type": "boolean"},
        },
        "required": [],
        "additionalProperties": False,
    },
)
def datetime_now(args: dict[str, Any]) -> str:
    tz = resolve_timezone(str(args.get("tz") or "").strip() or None)
    now_ms = resolve_now_ms(args.get("at_ms") if isinstance(args.get("at_ms"), int) else None)
    locale_format = str(args.get("locale_format") or "").strip() or "%Y/%m/%d %H:%M:%S"
    date_format = str(args.get("date_format") or "").strip() or "%Y-%m-%d"
    include_weekday = bool(args.get("include_weekday")) if "include_weekday" in args else True
    include_weekday_cn = bool(args.get("include_weekday_cn")) if "include_weekday_cn" in args else True
    include_day_of_year = bool(args.get("include_day_of_year")) if "include_day_of_year" in args else True
    payload = build_datetime_payload(
        now_ms=now_ms,
        tz=tz,
        locale_format=locale_format,
        date_format=date_format,
        include_weekday=include_weekday,
        include_weekday_cn=include_weekday_cn,
        include_day_of_year=include_day_of_year,
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool(
    name="now",
    title="获取当前时间",
    description="获取当前时间（UTC ISO 与本地时间字符串，可选时区）",
    input_schema={
        "type": "object",
        "properties": {"tz": {"type": "string"}, "at_ms": {"type": "integer"}, "locale_format": {"type": "string"}},
        "required": [],
        "additionalProperties": False,
    },
)
def now(args: dict[str, Any]) -> str:
    tz = resolve_timezone(str(args.get("tz") or "").strip() or None)
    now_ms = resolve_now_ms(args.get("at_ms") if isinstance(args.get("at_ms"), int) else None)
    locale_format = str(args.get("locale_format") or "").strip() or "%Y/%m/%d %H:%M:%S"
    payload = build_datetime_payload(
        now_ms=now_ms,
        tz=tz,
        locale_format=locale_format,
        include_weekday=False,
        include_weekday_cn=False,
        include_day_of_year=False,
    )
    return json.dumps({"iso": payload["iso_utc"], "locale": payload["local"], "tz": payload["tz"], "epoch_ms": payload["epoch_ms"]}, ensure_ascii=False, indent=2)


def register(registry: ToolRegistry) -> None:
    register_decorated(registry, globals())
