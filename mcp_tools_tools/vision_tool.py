"""Vision tools via OpenAI-compatible chat/completions endpoint."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from mcp_tools_core.env import env
from mcp_tools_core.http import http_post_json
from mcp_tools_core.tooling import ToolRegistry, register_decorated, tool


def _normalize_base_url(raw: str | None) -> str | None:
    s = str(raw or "").strip()
    if not s:
        return None
    s = s.strip().strip('"').strip("'").strip("`").strip()
    return s.rstrip("/")


def _join_url(base: str, path: str) -> str:
    if not base.endswith("/"):
        base = base + "/"
    return urllib.parse.urljoin(base, path.lstrip("/"))


def _extract_text_from_chat_response(parsed: object) -> str:
    if not isinstance(parsed, dict):
        return ""
    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    msg = first.get("message")
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if not isinstance(p, dict):
                continue
            if p.get("type") == "text" and isinstance(p.get("text"), str):
                parts.append(p["text"])
        return "\n".join([x.strip() for x in parts if str(x).strip()]).strip()
    return ""


@tool(
    name="vision_describe",
    title="图像理解",
    description="图像理解（OpenAI 兼容接口，支持 image_url data URL）",
    input_schema={
        "type": "object",
        "properties": {"images": {"type": "array", "items": {"type": "string"}}, "prompt": {"type": "string"}},
        "required": ["images"],
        "additionalProperties": False,
    },
)
def vision_describe(args: dict[str, Any]) -> str:
    images = args.get("images")
    if not isinstance(images, list):
        images = []
    images = [str(x).strip() for x in images if str(x or "").strip()]
    images = images[:3]
    prompt = str(args.get("prompt") or "").strip()
    if not images:
        return "错误：images 不能为空"

    base_url = _normalize_base_url(env("VISION_BASE_URL"))
    api_key = env("VISION_API_KEY")
    model = env("VISION_MODEL") or "gpt-4o-mini"
    if not base_url or not api_key:
        return "缺少识图配置：请在 mcp_tools/.env 设置 VISION_BASE_URL / VISION_API_KEY / VISION_MODEL"

    endpoint = _join_url(base_url, "chat/completions")
    content: list[dict] = []
    if prompt:
        content.append({"type": "text", "text": prompt})
    else:
        content.append({"type": "text", "text": "请描述图片内容，并指出关键细节。"})
    for d in images:
        content.append({"type": "image_url", "image_url": {"url": d}})

    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": content}],
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    status, body = http_post_json(endpoint, payload, headers, timeout_s=40.0)
    parsed: object | None
    try:
        parsed = json.loads(body.decode("utf-8"))
    except Exception:
        parsed = None
    if status < 200 or status >= 300:
        return f"识图失败：HTTP {status} {json.dumps(parsed, ensure_ascii=False)}"
    text = _extract_text_from_chat_response(parsed)
    return text or "识图失败：无可用输出"


def register(registry: ToolRegistry) -> None:
    """Register tools in this module."""
    register_decorated(registry, globals())
