import datetime as _dt
import re


def _clamp_int(n: int, min_v: int, max_v: int) -> int:
    return max(min_v, min(max_v, int(n)))


def _parse_cn_number(text: str) -> int | None:
    s = str(text or "").strip()
    if not s:
        return None
    if re.fullmatch(r"\d+", s):
        return int(s)
    mapping = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    total = 0
    cur = 0
    for ch in s:
        if ch == "十":
            cur = 1 if cur == 0 else cur
            total += cur * 10
            cur = 0
            continue
        if ch not in mapping:
            return None
        cur += int(mapping[ch])
    total += cur
    return int(total) if total >= 0 else None


def _strip_mentions(text: str) -> str:
    t = str(text or "")
    t = re.sub(r"@\d+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _rewrite_duration_phrases(text: str) -> str:
    s = str(text or "")
    if not s:
        return s
    s = re.sub(r"(?:半\s*个\s*|半\s*)(?:小时|钟头)", "30分钟", s)
    s = re.sub(r"(?:一\s*刻\s*钟)", "15分钟", s)
    s = re.sub(r"(?:两\s*刻\s*钟)", "30分钟", s)
    s = re.sub(r"(?:三\s*刻\s*钟)", "45分钟", s)

    def repl_one_and_half(m: re.Match) -> str:
        raw = str(m.group("n") or "").strip()
        n = _parse_cn_number(raw)
        if n is None:
            return m.group(0)
        mins = int(n) * 60 + 30
        return f"{mins}分钟"

    s = re.sub(r"(?P<n>\d+|[零〇一二两三四五六七八九十]+)\s*(?:个)?\s*半\s*(?:小时|钟头)", repl_one_and_half, s)
    s = re.sub(r"(?P<n>\d+|[零〇一二两三四五六七八九十]+)\s*(?:小时|钟头)\s*半", repl_one_and_half, s)
    return s


def _extract_mention_ids(text: str) -> list[str]:
    out: list[str] = []
    for m in re.finditer(r"@(\d+)", str(text or "")):
        i = str(m.group(1) or "").strip()
        if i:
            out.append(i)
    return out


def is_self_reminder_request(text: str) -> bool:
    t = str(text or "")
    if not t:
        return False
    if re.search(r"(?:提醒|叫|通知|发|发送)\s*(?:一下|下)?\s*(?:我|自己)\b", t):
        return True
    if re.search(r"提醒我(?!们)", t):
        return True
    return False


def pick_mention_user_id_for_request(text: str) -> str | None:
    raw = str(text or "")
    i = raw.find("提醒")
    if i >= 0:
        after = raw[i:]
        ids = _extract_mention_ids(after)
        if ids:
            return ids[0]
    ids = _extract_mention_ids(raw)
    return ids[0] if ids else None


def _parse_hm(text: str) -> tuple[int, int] | None:
    m = re.match(r"^(\d{1,2})(?:[:：点](\d{1,2}))?$", str(text or "").strip())
    if not m:
        return None
    hour = _clamp_int(int(m.group(1)), 0, 23)
    minute = _clamp_int(int(m.group(2)) if m.group(2) else 0, 0, 59)
    return hour, minute


def _parse_time_token(text: str) -> tuple[int, int] | None:
    t = str(text or "").strip()
    if not t:
        return None
    m1 = re.match(r"^(\d{1,2})\s*(?:[:：]\s*(\d{1,2}))$", t)
    if m1:
        return _clamp_int(int(m1.group(1)), 0, 23), _clamp_int(int(m1.group(2)), 0, 59)
    m2 = re.match(r"^(\d{1,2})\s*点\s*半$", t)
    if m2:
        return _clamp_int(int(m2.group(1)), 0, 23), 30
    m3 = re.match(r"^(\d{1,2})\s*点\s*(\d{1,2})$", t)
    if m3:
        return _clamp_int(int(m3.group(1)), 0, 23), _clamp_int(int(m3.group(2)), 0, 59)
    m4 = re.match(r"^(\d{1,2})\s*点$", t)
    if m4:
        return _clamp_int(int(m4.group(1)), 0, 23), 0
    return _parse_hm(t)


def _compute_next_time(day_hint: str | None, hour: int, minute: int, now_ms: int) -> int:
    now = _dt.datetime.fromtimestamp(now_ms / 1000)
    base = now.replace(second=0, microsecond=0, hour=int(hour), minute=int(minute))
    if day_hint == "tomorrow":
        base = base + _dt.timedelta(days=1)
    elif day_hint == "day_after_tomorrow":
        base = base + _dt.timedelta(days=2)
    if day_hint is None and int(base.timestamp() * 1000) <= now_ms:
        base = base + _dt.timedelta(days=1)
    return int(base.timestamp() * 1000)


def _parse_delay_reminder(text: str, now_ms: int) -> tuple[int, str] | None:
    t = _rewrite_duration_phrases(_strip_mentions(text))
    r1 = re.match(
        r"^(?:(?:提醒|叫|通知|发|发送)(?:我|你)?\s*)?(?:(\d+|[零〇一二两三四五六七八九十]+)\s*(?:天|d))?\s*(?:(\d+|[零〇一二两三四五六七八九十]+)\s*(?:小时|h))?\s*(?:(\d+|[零〇一二两三四五六七八九十]+)\s*(?:分钟|分|min|m))?\s*(?:后|以后|之后)\s*(?:(?:提醒|叫|通知|发|发送)(?:我|你)?\s*)?(.+)$",
        t,
        flags=re.IGNORECASE,
    )
    r2 = re.match(
        r"^(?:(\d+|[零〇一二两三四五六七八九十]+)\s*(?:天|d))?\s*(?:(\d+|[零〇一二两三四五六七八九十]+)\s*(?:小时|h))?\s*(?:(\d+|[零〇一二两三四五六七八九十]+)\s*(?:分钟|分|min|m))?\s*(?:后|以后|之后)\s*(?:提醒|叫|通知|发|发送)(?:我|你)?\s*(.+)$",
        t,
        flags=re.IGNORECASE,
    )
    m = r1 or r2
    if not m:
        return None
    days_raw = str(m.group(1) or "").strip()
    hours_raw = str(m.group(2) or "").strip()
    mins_raw = str(m.group(3) or "").strip()
    days = _clamp_int(_parse_cn_number(days_raw) or 0, 0, 365) if days_raw else 0
    hours = _clamp_int(_parse_cn_number(hours_raw) or 0, 0, 168) if hours_raw else 0
    mins = _clamp_int(_parse_cn_number(mins_raw) or 0, 0, 10080) if mins_raw else 0
    if not days and not hours and not mins:
        return None
    delay_ms = (days * 24 * 60 + hours * 60 + mins) * 60_000
    msg = _strip_mentions(m.group(4) or "")
    if not msg:
        return None
    return now_ms + int(delay_ms), msg


def _parse_absolute_reminder(text: str, now_ms: int) -> tuple[int, str] | None:
    t = _strip_mentions(text)
    m_dt = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2})(?:[:：](\d{1,2}))\s*(?:提醒|叫|通知|发|发送)(?:我)?\s*(.+)$", t)
    if m_dt:
        year = int(m_dt.group(1))
        month = _clamp_int(int(m_dt.group(2)), 1, 12)
        day = _clamp_int(int(m_dt.group(3)), 1, 31)
        hour = _clamp_int(int(m_dt.group(4)), 0, 23)
        minute = _clamp_int(int(m_dt.group(5)), 0, 59)
        msg = _strip_mentions(m_dt.group(6) or "")
        if not msg:
            return None
        try:
            due = int(_dt.datetime(year, month, day, hour, minute).timestamp() * 1000)
        except Exception:
            return None
        if due <= now_ms:
            return None
        return due, msg

    m_hm = re.match(r"^(?:在\s*)?(今天|明天|后天|今晚)?\s*(\d{1,2}(?:[:：点]\d{1,2})?)\s*(?:提醒|叫|通知|发|发送)(?:我)?\s*(.+)$", t)
    if not m_hm:
        return None
    hint_raw = str(m_hm.group(1) or "").strip()
    hm = _parse_hm(str(m_hm.group(2) or "").strip())
    msg = _strip_mentions(m_hm.group(3) or "")
    if not hm or not msg:
        return None
    day_hint = None
    if hint_raw == "明天":
        day_hint = "tomorrow"
    elif hint_raw == "后天":
        day_hint = "day_after_tomorrow"
    elif hint_raw == "今天":
        day_hint = "today"
    elif hint_raw:
        day_hint = "today"
    due = _compute_next_time(day_hint if day_hint != "today" else "today", hm[0], hm[1], now_ms)
    if due <= now_ms:
        return None
    return due, msg


def _parse_multi_absolute_reminder(text: str, now_ms: int) -> list[tuple[int, str]] | None:
    t = _strip_mentions(text)
    m = re.match(r"^(?:在\s*)?(今天|明天|后天|今晚)?\s*([\s\S]+?)\s*(?:提醒|叫|通知|发|发送)(?:我|你|ta|他|她)?\s*(.+)$", t)
    if not m:
        return None
    hint_raw = str(m.group(1) or "").strip()
    times_raw = str(m.group(2) or "").strip()
    msg = _strip_mentions(m.group(3) or "")
    if not times_raw or not msg:
        return None
    day_hint = None
    if hint_raw == "明天":
        day_hint = "tomorrow"
    elif hint_raw == "后天":
        day_hint = "day_after_tomorrow"
    elif hint_raw == "今天":
        day_hint = "today"
    elif hint_raw:
        day_hint = "today"
    candidates = re.sub(r"[，、]", ",", times_raw)
    candidates = re.sub(r"\s+", " ", candidates)
    parts = [p.strip() for p in re.split(r"[,\s]+", candidates) if p.strip()]
    if len(parts) < 2:
        return None
    out: list[tuple[int, str]] = []
    for c in parts:
        hm = _parse_time_token(c)
        if not hm:
            continue
        due = _compute_next_time(day_hint if day_hint != "today" else "today", hm[0], hm[1], now_ms)
        if due <= now_ms:
            continue
        out.append((due, msg))
    uniq: dict[int, tuple[int, str]] = {}
    for due, mmsg in out:
        uniq[due] = (due, mmsg)
    lst = sorted(uniq.values(), key=lambda x: x[0])
    return lst if len(lst) >= 2 else None


def parse_reminder_requests(text: str, now_ms: int) -> list[tuple[int, str]] | None:
    multi = _parse_multi_absolute_reminder(text, now_ms)
    if multi:
        return multi
    one = _parse_delay_reminder(text, now_ms) or _parse_absolute_reminder(text, now_ms)
    return [one] if one else None
