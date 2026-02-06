from __future__ import annotations

import os
import threading
import time

from tools.gold_price import get_gold_snapshot
from tools.reminders.napcat_http import NapCatHttpSender

_LOCK = threading.Lock()
_STARTED = False


def _env(name: str) -> str | None:
    v = os.environ.get(name)
    if not v:
        return None
    s = str(v).strip()
    return s or None


def _env_bool(name: str, default: bool) -> bool:
    v = _env(name)
    if v is None:
        return default
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default


def _env_int(name: str, default: int) -> int:
    v = _env(name)
    if v is None:
        return default
    try:
        n = int(str(v).strip())
        return n if n > 0 else default
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    v = _env(name)
    if v is None:
        return default
    try:
        x = float(str(v).strip())
        return x if x > 0 else default
    except Exception:
        return default


def _format_alert_message(*, baseline: float, current: float, delta: float, usdcny: float, usd_oz: float | None, ts: str) -> str:
    direction = "上涨" if delta > 0 else "下跌"
    abs_delta = abs(delta)
    lines = [
        f"金价提醒：{direction}{abs_delta:.2f} 元/克",
        f"基准: {baseline:.2f} 元/克",
        f"当前: {current:.2f} 元/克",
        f"汇率: {usdcny:.4f}",
    ]
    if isinstance(usd_oz, (int, float)) and usd_oz > 0:
        lines.append(f"美元计价: {float(usd_oz):.2f} 美元/盎司")
    if ts:
        lines.append(f"时间: {ts}")
    return "\n".join(lines).strip()


def _loop() -> None:
    sender = NapCatHttpSender()
    group_id = str(_env("GOLD_ALERT_GROUP_ID") or "831369251").strip() or "831369251"
    threshold = _env_float("GOLD_ALERT_THRESHOLD_CNY", 10.0)
    interval_s = _env_int("GOLD_ALERT_INTERVAL_S", 60)

    baseline: float | None = None
    while True:
        try:
            snap = get_gold_snapshot()
            lbma = snap.get("lbma") if isinstance(snap.get("lbma"), dict) else {}
            sge = snap.get("sge") if isinstance(snap.get("sge"), dict) else {}
            sge_cny_g = sge.get("cny_g")
            current = lbma.get("cny_g")
            usdcny = float(snap.get("usdcny") or 0.0)
            usd_oz = lbma.get("usd_oz")
            ts = str(snap.get("timestamp") or "").strip()

            picked = None
            if isinstance(sge_cny_g, (int, float)) and float(sge_cny_g) > 0:
                picked = ("SGE", float(sge_cny_g))
            elif isinstance(current, (int, float)) and float(current) > 0:
                picked = ("LBMA", float(current))

            if not picked:
                time.sleep(interval_s)
                continue

            source, current_f = picked
            if baseline is None:
                baseline = current_f
                time.sleep(interval_s)
                continue

            delta = current_f - baseline
            if abs(delta) >= threshold:
                msg = _format_alert_message(
                    baseline=baseline,
                    current=current_f,
                    delta=delta,
                    usdcny=usdcny,
                    usd_oz=float(usd_oz) if isinstance(usd_oz, (int, float)) else None,
                    ts=ts,
                )
                msg = f"{source} {msg}".strip()
                sender.send({"chatType": "group", "groupId": group_id}, msg)
                baseline = current_f
        except Exception:
            pass
        time.sleep(interval_s)


def start_gold_alert_monitor() -> None:
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        if not _env_bool("GOLD_ALERT_ENABLED", False):
            _STARTED = True
            return
        t = threading.Thread(target=_loop, daemon=True)
        t.start()
        _STARTED = True
