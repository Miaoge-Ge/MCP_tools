"""Weather tools powered by Seniverse (心知天气)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error

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


def _http_get(url: str, timeout_s: float = 15.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as res:
            return int(res.status), res.read()
    except urllib.error.HTTPError as e:
        return int(e.code), e.read()


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


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="weather_query", description="获取指定城市当前天气（需要配置 SENIVERSE_PUBLIC_KEY / SENIVERSE_PRIVATE_KEY）")
    def weather_query(location: str) -> str:
        loc = str(location or "").strip()
        if not loc:
            return "错误：城市名称不能为空或无效"

        public_key = _env("SENIVERSE_PUBLIC_KEY")
        private_key = _env("SENIVERSE_PRIVATE_KEY")
        if not public_key or not private_key:
            return "缺少心知天气配置：请设置环境变量 SENIVERSE_PUBLIC_KEY 和 SENIVERSE_PRIVATE_KEY"

        host = _normalize_seniverse_host(_env("SENIVERSE_API_HOST"))
        base_url = f"https://{host}/v3/weather/now.json"
        signature = _seniverse_signature(public_key, private_key)
        params = urllib.parse.urlencode({"location": loc, "language": "zh-Hans", "unit": "c"})
        full_url = f"{base_url}?{params}&{signature}"

        status, body = _http_get(full_url, timeout_s=20.0)
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
