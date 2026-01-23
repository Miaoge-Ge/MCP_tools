from __future__ import annotations

import datetime as dt
import time
from zoneinfo import ZoneInfo

from mcp_tools_core.env import env


def resolve_timezone(tz: str | None) -> dt.tzinfo:
    name = str(tz or "").strip()
    if not name:
        name = str(env("TIMEZONE") or "").strip()
    if not name:
        name = "Asia/Shanghai"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def resolve_now_ms(at_ms: int | None) -> int:
    if isinstance(at_ms, int):
        return int(at_ms)
    return int(time.time() * 1000)


def weekday_cn_for(d: dt.datetime) -> str:
    return ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"][int(d.strftime("%w"))]


def day_of_year_for(d: dt.datetime) -> int:
    start = dt.datetime(d.year, 1, 1, tzinfo=d.tzinfo)
    return int((d - start).total_seconds() // 86400) + 1


def build_datetime_payload(
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
        payload["weekday_cn"] = weekday_cn_for(local)
    if include_day_of_year:
        payload["day_of_year"] = day_of_year_for(local)
    return payload

