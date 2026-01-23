"""Vision tools via OpenAI-compatible chat/completions endpoint."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.error
import urllib.request

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


def _http_post_json(url: str, payload: dict, headers: dict[str, str], timeout_s: float = 15.0) -> tuple[int, bytes]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as res:
            return int(res.status), res.read()
    except urllib.error.HTTPError as e:
        return int(e.code), e.read()


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


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="vision_describe", description="图像理解（OpenAI 兼容接口，支持 image_url data URL）")
    def vision_describe(images: list[str], prompt: str | None = None) -> str:
        imgs = [str(x).strip() for x in (images or []) if str(x or "").strip()]
        imgs = imgs[:3]
        prompt0 = str(prompt or "").strip()
        if not imgs:
            return "错误：images 不能为空"

        base_url = _normalize_base_url(_env("VISION_BASE_URL"))
        api_key = _env("VISION_API_KEY")
        model = _env("VISION_MODEL") or "gpt-4o-mini"
        if not base_url or not api_key:
            return "缺少识图配置：请在 .env 设置 VISION_BASE_URL / VISION_API_KEY / VISION_MODEL"

        endpoint = _join_url(base_url, "chat/completions")
        content: list[dict] = []
        if prompt0:
            content.append({"type": "text", "text": prompt0})
        else:
            content.append({"type": "text", "text": "请描述图片内容，并指出关键细节。"})
        for d in imgs:
            content.append({"type": "image_url", "image_url": {"url": d}})

        payload = {
            "model": model,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": content}],
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        status, body = _http_post_json(endpoint, payload, headers, timeout_s=40.0)
        parsed: object | None
        try:
            parsed = json.loads(body.decode("utf-8"))
        except Exception:
            parsed = None
        if status < 200 or status >= 300:
            return f"识图失败：HTTP {status} {json.dumps(parsed, ensure_ascii=False)}"
        text = _extract_text_from_chat_response(parsed)
        return text or "识图失败：无可用输出"
