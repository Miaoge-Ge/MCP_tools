"""Web search tool wrapper (Search1API / Serper)."""

from __future__ import annotations

import json
import os
import re
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


def _normalize_queries(q: str) -> list[str]:
    raw = str(q or "").strip()
    if not raw:
        return []
    variants: list[str] = [raw]
    no_suffix = re.sub(r"(?:的)?(?:趣事|八卦|梗|故事|名场面|集锦)\s*$", "", raw).strip()
    if no_suffix and no_suffix != raw:
        variants.append(no_suffix)
    compact = re.sub(r"\s+", " ", no_suffix).strip()
    if compact and compact != no_suffix:
        variants.append(compact)
    out: list[str] = []
    for v in variants:
        if v not in out:
            out.append(v)
    return out[:3]


def _try_serper_search(api_key: str, query: str, prefer_zh: bool) -> str:
    payload = {"q": query, "gl": "cn" if prefer_zh else "us", "hl": "zh-cn" if prefer_zh else "en", "num": 5}
    status, body = _http_post_json(
        "https://google.serper.dev/search",
        payload,
        {"Content-Type": "application/json", "X-API-KEY": api_key},
        timeout_s=20.0,
    )
    parsed: object | None
    try:
        parsed = json.loads(body.decode("utf-8"))
    except Exception:
        parsed = None
    if status < 200 or status >= 300:
        raise RuntimeError(f"Serper: HTTP {status} {json.dumps(parsed, ensure_ascii=False)}")
    organic = parsed.get("organic") if isinstance(parsed, dict) else None
    results = organic if isinstance(organic, list) else []
    if not results:
        return f"未找到与 '{query}' 相关的搜索结果。"
    lines: list[str] = []
    for r in results[:5]:
        if not isinstance(r, dict):
            continue
        link = str(r.get("link") or "").lower()
        if link and "tophub." in link:
            continue
        title = str(r.get("title") or "无标题")
        snippet = str(r.get("snippet") or "无摘要")
        if r.get("link"):
            lines.append(f"{title} - {snippet} ({r.get('link')})")
        else:
            lines.append(f"{title} - {snippet}")
    return "搜索结果：\n" + "\n".join(lines)


def _try_search1api(api_key: str, query: str, prefer_zh: bool) -> str:
    host = _env("SEARCH_API_HOST") or "api.search1api.com"
    url = f"https://{host}/search"
    payload: dict[str, object] = {
        "query": query,
        "search_service": "google",
        "max_results": 8,
        "crawl_results": 2,
        "image": False,
        "language": "zh" if prefer_zh else "en",
        "time_range": "month",
        "exclude_sites": ["wikipedia.org", "tophub.today", "tophub.link", "tophub.fun"],
    }
    if prefer_zh and re.search(r"(新闻|热搜|要闻|摘要|热点)", query):
        payload["include_sites"] = [
            "news.sina.com.cn",
            "news.qq.com",
            "cctv.com",
            "xinhuanet.com",
            "people.com.cn",
            "chinanews.com.cn",
            "thepaper.cn",
            "guancha.cn",
        ]

    status, body = _http_post_json(
        url,
        payload,
        {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        timeout_s=20.0,
    )
    parsed: object | None
    try:
        parsed = json.loads(body.decode("utf-8"))
    except Exception:
        parsed = None
    if status < 200 or status >= 300:
        raise RuntimeError(f"Search1API: HTTP {status} {json.dumps(parsed, ensure_ascii=False)}")

    results: list = []
    if isinstance(parsed, dict):
        for k in ("results", "organic_results", "data", "search_results"):
            v = parsed.get(k)
            if isinstance(v, list):
                results = v
                break
    if not results:
        return f"未找到与 '{query}' 相关的搜索结果。"
    lines: list[str] = []
    for r in results[:5]:
        if not isinstance(r, dict):
            continue
        title = str(r.get("title") or "无标题")
        snippet = str(r.get("snippet") or r.get("description") or "无摘要")
        link = r.get("link")
        lines.append(f"{title} - {snippet}{f' ({link})' if link else ''}")
    return "搜索结果：\n" + "\n".join(lines)


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="web_search", description="联网搜索（优先 Search1API，其次 Serper）")
    def web_search(query: str) -> str:
        q = str(query or "").strip()
        if not q:
            return "错误：搜索查询不能为空或无效。"
        errors: list[str] = []
        has_cjk = bool(re.search(r"[\u4e00-\u9fff]", q))
        has_latin = bool(re.search(r"[A-Za-z]", q))
        variants = _normalize_queries(q)
        langs = [True, False] if (has_cjk and has_latin) else [has_cjk]

        search1_key = _env("SEARCH_API_KEY")
        if search1_key:
            for qq in variants:
                for prefer_zh in langs:
                    try:
                        text = _try_search1api(search1_key, qq, prefer_zh)
                        if "未找到与" not in text:
                            return text
                    except Exception as e:
                        errors.append(str(e))

        serper_key = _env("SERPER_API_KEY")
        if serper_key:
            for qq in variants:
                for prefer_zh in langs:
                    try:
                        text = _try_serper_search(serper_key, qq, prefer_zh)
                        if "未找到与" not in text:
                            return text
                    except Exception as e:
                        errors.append(str(e))

        if not search1_key and not serper_key:
            return "缺少 SEARCH_API_KEY / SERPER_API_KEY，无法联网搜索"
        return "搜索失败：\n" + "\n".join(errors)
