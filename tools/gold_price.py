"""Real-time gold prices (SGE + LBMA spot reference) without paid API keys.

Data source: Eastmoney public endpoints (quote + suggest), no API key required.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from mcp.server.fastmcp import FastMCP

from tools.limits import enforce_daily_limits

_ENV_BOOTSTRAPPED = False

TROY_OUNCE_TO_GRAM = 31.1034768


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
                if len(val) >= 2 and (
                    (val[0] == val[-1] and val[0] in ("'", '"')) or (val[0] == "`" and val[-1] == "`")
                ):
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


def _env_float(name: str) -> float | None:
    v = _env(name)
    if v is None:
        return None
    try:
        x = float(str(v).strip())
        return x if x > 0 else None
    except Exception:
        return None


def _http_get(url: str, *, headers: dict[str, str] | None = None, timeout_s: float = 15.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="GET")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as res:
            return int(res.status), res.read()
    except urllib.error.HTTPError as e:
        return int(e.code), e.read()


def _http_get_json(url: str, *, headers: dict[str, str] | None = None, timeout_s: float = 15.0) -> Any:
    status, body = _http_get(url, headers=headers, timeout_s=timeout_s)
    parsed: Any
    try:
        parsed = json.loads(body.decode("utf-8"))
    except Exception:
        parsed = body.decode("utf-8", errors="replace")
    if status < 200 or status >= 300:
        raise RuntimeError(f"HTTP {status} {json.dumps(parsed, ensure_ascii=False) if not isinstance(parsed, str) else parsed}")
    return parsed


def _parse_number(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    s = s.replace(",", "")
    s = re.sub(r"[^\d.\-]+", "", s)
    if not s or s in ("-", ".", "-."):
        return None
    try:
        return float(s)
    except Exception:
        return None


def _format_change(change: float | None, pct: float | None, unit: str) -> str:
    if change is None and pct is None:
        return "—"
    if change is None:
        sign = "+" if pct is not None and pct > 0 else ""
        return f"{sign}{pct:.2f}%"
    sign = "+" if change > 0 else ""
    if pct is None:
        return f"{sign}{change:.2f} {unit}"
    signp = "+" if pct > 0 else ""
    return f"{sign}{change:.2f} {unit} ({signp}{pct:.2f}%)"


def _get_usdcny_rate() -> float:
    manual = _env_float("GOLD_USDCNY")
    if manual:
        return manual
    url = "https://open.er-api.com/v6/latest/USD"
    parsed = _http_get_json(url, timeout_s=12.0)
    if not isinstance(parsed, dict):
        raise RuntimeError("汇率服务返回异常")
    rates = parsed.get("rates")
    if not isinstance(rates, dict):
        raise RuntimeError("汇率服务返回异常")
    cny = rates.get("CNY")
    x = _parse_number(cny)
    if not x:
        raise RuntimeError("无法获取 USD/CNY 汇率")
    return float(x)


def _em_get_quote(secid: str) -> dict[str, Any]:
    fields = ",".join(
        [
            "f57",
            "f58",
            "f43",
            "f44",
            "f45",
            "f46",
            "f60",
            "f169",
            "f170",
            "f171",
            "f168",
            "f124",
        ]
    )
    url = (
        "https://push2.eastmoney.com/api/qt/stock/get?"
        + urllib.parse.urlencode(
            {
                "secid": secid,
                "fields": fields,
                "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            }
        )
    )
    parsed = _http_get_json(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}, timeout_s=15.0)
    if not isinstance(parsed, dict):
        raise RuntimeError("行情服务返回异常")
    data = parsed.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("行情服务返回异常")
    return data


def _em_scaled(v: Any) -> float | None:
    n = _parse_number(v)
    if n is None:
        return None
    if abs(n) >= 1000:
        return n / 100.0
    return n


def _em_scaled_pct(v: Any) -> float | None:
    n = _parse_number(v)
    if n is None:
        return None
    if abs(n) >= 1.0:
        return n / 100.0
    return n


def _em_quote_to_fields(data: dict[str, Any]) -> dict[str, Any]:
    price = _em_scaled(data.get("f43"))
    high = _em_scaled(data.get("f44"))
    low = _em_scaled(data.get("f45"))
    open_p = _em_scaled(data.get("f46"))
    prev = _em_scaled(data.get("f60"))
    ch = _em_scaled(data.get("f169"))
    chp = _em_scaled_pct(data.get("f170"))
    ts = str(data.get("f124") or "").strip()
    name = str(data.get("f58") or data.get("f57") or "").strip()
    code = str(data.get("f57") or "").strip()
    return {
        "name": name or code or "—",
        "code": code or "—",
        "price": price,
        "high": high,
        "low": low,
        "open": open_p,
        "prev_close": prev,
        "change": ch,
        "change_pct": chp,
        "ts": ts,
    }


def _format_usd_block(*, title: str, q: dict[str, Any]) -> list[str]:
    price = q.get("price")
    high = q.get("high")
    low = q.get("low")
    ch = q.get("change")
    chp = q.get("change_pct")
    lines: list[str] = []
    lines.append("💵 美元计价:")
    if isinstance(price, (int, float)) and price > 0:
        lines.append(f"    最新价: {price:.2f} 美元/盎司")
        lines.append(f"    涨跌: {_format_change(ch, chp, '美元/盎司')}")
        if isinstance(high, (int, float)) and isinstance(low, (int, float)) and high > 0 and low > 0:
            lines.append(f"    最高/最低: {high:.2f} / {low:.2f}")
    else:
        lines.append("    最新价: —")
    return lines


def _format_cny_block(*, title: str, usd_oz: float, usdcny: float) -> list[str]:
    cny_oz = usd_oz * usdcny
    cny_g = cny_oz / TROY_OUNCE_TO_GRAM
    return [
        f"💴 人民币计价 (汇率: {usdcny:.4f}):",
        f"    每盎司: {cny_oz:.2f} 元",
        f"    每克: {cny_g:.2f} 元",
    ]


def _format_sge_blocks(*, title: str, cny_g: float, q: dict[str, Any], usdcny: float) -> list[str]:
    cny_oz = cny_g * TROY_OUNCE_TO_GRAM
    usd_oz = cny_oz / usdcny
    usd_g = cny_g / usdcny
    high = q.get("high")
    low = q.get("low")
    ch = q.get("change")
    chp = q.get("change_pct")
    out: list[str] = []
    out.append("💴 人民币计价:")
    out.append(f"    最新价: {cny_g:.2f} 元/克")
    out.append(f"    涨跌: {_format_change(ch, chp, '元/克')}")
    if isinstance(high, (int, float)) and isinstance(low, (int, float)) and high > 0 and low > 0:
        out.append(f"    最高/最低: {high:.2f} / {low:.2f} 元/克")
    out.append(f"💵 美元计价 (汇率: {usdcny:.4f}):")
    out.append(f"    每盎司: {usd_oz:.2f} 美元/盎司")
    out.append(f"    每克: {usd_g:.2f} 美元/克")
    return out


def get_gold_snapshot() -> dict[str, Any]:
    usdcny = _get_usdcny_rate()

    lbma_secid = str(_env("GOLD_LONDON_EM_SECID") or "122.XAU").strip() or "122.XAU"
    sge_secid = str(_env("GOLD_SGE_EM_SECID") or "118.SHAU").strip() or "118.SHAU"

    lbma_raw = _em_get_quote(lbma_secid)
    sge_raw = _em_get_quote(sge_secid)

    lbma_q = _em_quote_to_fields(lbma_raw)
    sge_q = _em_quote_to_fields(sge_raw)

    lbma_usd_oz = float(lbma_q["price"]) if isinstance(lbma_q.get("price"), (int, float)) and lbma_q["price"] > 0 else None
    lbma_cny_g = (lbma_usd_oz * usdcny / TROY_OUNCE_TO_GRAM) if lbma_usd_oz else None

    sge_cny_g = float(sge_q["price"]) if isinstance(sge_q.get("price"), (int, float)) and sge_q["price"] > 0 else None
    sge_usd_oz = (sge_cny_g * TROY_OUNCE_TO_GRAM / usdcny) if sge_cny_g else None
    sge_usd_g = (sge_cny_g / usdcny) if sge_cny_g else None

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "usdcny": usdcny,
        "lbma": {
            "secid": lbma_secid,
            **lbma_q,
            "usd_oz": lbma_usd_oz,
            "cny_g": lbma_cny_g,
        },
        "sge": {
            "secid": sge_secid,
            **sge_q,
            "cny_g": sge_cny_g,
            "usd_oz": sge_usd_oz,
            "usd_g": sge_usd_g,
        },
    }


def format_gold_snapshot(snapshot: dict[str, Any]) -> str:
    usdcny = float(snapshot.get("usdcny") or 0.0)
    lbma_q = snapshot.get("lbma") if isinstance(snapshot.get("lbma"), dict) else {}
    sge_q = snapshot.get("sge") if isinstance(snapshot.get("sge"), dict) else {}
    ts = str(snapshot.get("timestamp") or "").strip() or time.strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []

    lines.append(f"LBMA（伦敦金/现货参考：{str(lbma_q.get('name') or '—')}）")
    lines.extend(_format_usd_block(title="", q=lbma_q))
    if isinstance(lbma_q.get("usd_oz"), (int, float)) and lbma_q["usd_oz"] > 0 and usdcny > 0:
        lines.extend(_format_cny_block(title="", usd_oz=float(lbma_q["usd_oz"]), usdcny=usdcny))
    lines.append("")

    lines.append(f"SGE（上海黄金交易所：{str(sge_q.get('name') or '—')}）")
    if isinstance(sge_q.get("cny_g"), (int, float)) and sge_q["cny_g"] > 0 and usdcny > 0:
        lines.extend(_format_sge_blocks(title="", cny_g=float(sge_q["cny_g"]), q=sge_q, usdcny=usdcny))
    else:
        lines.append("  当前未返回有效最新价（可能非交易时段或数据源暂不可用）")
    lines.append("")
    lines.append(f"生成时间: {ts}")
    return "\n".join([x.rstrip() for x in lines]).strip()


def get_realtime_gold_prices() -> str:
    return format_gold_snapshot(get_gold_snapshot())


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="gold_price_realtime", description="实时金价：SGE 上海金 + 伦敦金参考（LBMA 现货），输出美元/人民币计价、涨跌与最高/最低")
    def gold_price_realtime(
        chat_type: str | None = None,
        user_id: str | None = None,
        group_id: str | None = None,
    ) -> str:
        try:
            enforce_daily_limits(tool_name="gold_price_realtime", chat_type=chat_type, user_id=user_id, group_id=group_id)
            return get_realtime_gold_prices()
        except Exception as e:
            return f"错误：{e}"
