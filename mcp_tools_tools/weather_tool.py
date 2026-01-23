"""Weather tools powered by Seniverse (心知天气)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.parse
from typing import Any

from mcp_tools_core.env import env
from mcp_tools_core.http import http_get
from mcp_tools_core.tooling import ToolRegistry, register_decorated, tool


def _seniverse_signature(public_key: str, private_key: str, ttl: int = 300) -> str:
    ts = int(time.time())
    params = f"ts={ts}&ttl={int(ttl)}&uid={public_key}"
    digest = hmac.new(private_key.encode("utf-8"), params.encode("utf-8"), hashlib.sha1).digest()
    sig = urllib.parse.quote(base64.b64encode(digest).decode("utf-8"), safe="")
    return f"{params}&sig={sig}"


def _normalize_seniverse_host(raw: str | None) -> str:
    h = str(raw or "").strip()
    if not h:
        return "api.seniverse.com"
    if h.startswith("http://") or h.startswith("https://"):
        u = urllib.parse.urlparse(h)
        return u.netloc or h.replace("https://", "").replace("http://", "")
    return h


@tool(
    name="weather_query",
    title="查询天气",
    description="获取指定城市当前天气（需要配置 SENIVERSE_PUBLIC_KEY / SENIVERSE_PRIVATE_KEY）",
    input_schema={"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"], "additionalProperties": False},
)
def weather_query(args: dict[str, Any]) -> str:
    """Return current weather for a location."""
    loc = str(args.get("location") or "").strip()
    if not loc:
        return "错误：城市名称不能为空或无效"

    public_key = env("SENIVERSE_PUBLIC_KEY")
    private_key = env("SENIVERSE_PRIVATE_KEY")
    if not public_key or not private_key:
        return "缺少心知天气配置：请设置环境变量 SENIVERSE_PUBLIC_KEY 和 SENIVERSE_PRIVATE_KEY"

    host = _normalize_seniverse_host(env("SENIVERSE_API_HOST"))
    base_url = f"https://{host}/v3/weather/now.json"
    signature = _seniverse_signature(public_key, private_key)
    params = urllib.parse.urlencode({"location": loc, "language": "zh-Hans", "unit": "c"})
    full_url = f"{base_url}?{params}&{signature}"

    status, body = http_get(full_url, timeout_s=20.0)
    parsed: object | None
    try:
        parsed = json.loads(body.decode("utf-8"))
    except Exception:
        parsed = None
    if status < 200 or status >= 300:
        return f"请求天气失败：HTTP {status} {json.dumps(parsed, ensure_ascii=False)}"

    results = parsed.get("results") if isinstance(parsed, dict) else None
    if not isinstance(results, list) or not results:
        return f"未获取到 {loc} 的天气信息"
    first = results[0] if isinstance(results[0], dict) else {}
    now = first.get("now") if isinstance(first, dict) else {}
    loc_obj = first.get("location") if isinstance(first, dict) else {}
    city = (loc_obj.get("name") if isinstance(loc_obj, dict) else None) or loc
    weather_text = (now.get("text") if isinstance(now, dict) else None) or "未知天气"
    temperature = (now.get("temperature") if isinstance(now, dict) else None) or "未知温度"
    return f"{city} 当前天气：{weather_text}，气温 {temperature}°C"


def register(registry: ToolRegistry) -> None:
    """Register tools in this module."""
    register_decorated(registry, globals())
