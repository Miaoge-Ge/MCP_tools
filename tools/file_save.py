"""File saving tool (data URL or http/https URL -> local file)."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import math
import mimetypes
import os
import re
import socket
import time
import urllib.parse
import urllib.request

from tools.limits import enforce_daily_limits

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


_MIME_TO_EXT: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
    "video/x-matroska": "mkv",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "application/pdf": "pdf",
    "application/zip": "zip",
    "application/json": "json",
    "text/plain": "txt",
}

MAX_SINGLE_FILE_BYTES = 30 * 1024 * 1024
MAX_FILES = 10


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_save_dir() -> str:
    return os.path.join(_project_root(), "data", "files")


def _resolve_path_from_root(p: str) -> str:
    raw = str(p or "").strip()
    expanded = os.path.expanduser(raw)
    if os.path.isabs(expanded):
        return os.path.abspath(expanded)
    return os.path.abspath(os.path.join(_project_root(), expanded))


def _sanitize_subdir(raw: str | None) -> str | None:
    s = str(raw or "").strip()
    if not s:
        return None
    s = s.replace("\\", "/")
    s = re.sub(r"/+", "/", s).strip("/")
    if not s or s in (".", ".."):
        return None
    if ".." in s.split("/"):
        return None
    return s


def _category_dirname(mime: str) -> str:
    top = str(mime or "").split("/", 1)[0].strip().lower()
    if top == "image":
        return "images"
    if top == "video":
        return "videos"
    if top == "audio":
        return "audio"
    if top == "text":
        return "text"
    if top == "application":
        return "files"
    return "others"


def _resolve_save_dir(mime: str, subdir: str | None) -> str:
    base = str(_env("FILE_SAVE_DIR") or "").strip() or _default_save_dir()
    base = _resolve_path_from_root(base)
    category = _category_dirname(mime)
    base2 = os.path.abspath(os.path.join(base, category))
    sd = _sanitize_subdir(subdir)
    if not sd:
        return base2
    out = os.path.abspath(os.path.join(base2, sd))
    if os.path.commonpath([base2, out]) != base2:
        return base2
    return out


def _parse_data_url(url: str, *, max_bytes: int = MAX_SINGLE_FILE_BYTES) -> tuple[str, bytes]:
    s = str(url or "").strip()
    m = re.match(r"^data:(?P<mime>[^;]+);base64,(?P<data>[A-Za-z0-9+/=\s]+)$", s)
    if not m:
        raise ValueError("仅支持 data URL（data:<mime>;base64,...）")
    mime = str(m.group("mime") or "").strip().lower()
    data_b64 = re.sub(r"\s+", "", str(m.group("data") or ""))
    if max_bytes > 0:
        max_b64_len = int(math.ceil(max_bytes / 3) * 4)
        if len(data_b64) > max_b64_len + 16:
            raise ValueError("单个文件不能超过 30MB")
    try:
        blob = base64.b64decode(data_b64, validate=True)
    except Exception as e:
        raise ValueError(f"base64 解码失败：{e}") from e
    if not blob:
        raise ValueError("文件内容为空")
    if max_bytes > 0 and len(blob) > max_bytes:
        raise ValueError("单个文件不能超过 30MB")
    return mime or "application/octet-stream", blob


def _check_public_host(host: str) -> None:
    h = str(host or "").strip()
    if not h:
        raise ValueError("URL 缺少 host")
    try:
        infos = socket.getaddrinfo(h, None)
    except Exception as e:
        raise ValueError(f"无法解析 URL host：{e}") from e
    ips = []
    for info in infos:
        addr = info[4][0]
        if addr:
            ips.append(addr)
    if not ips:
        raise ValueError("无法解析 URL host")
    for addr in ips[:16]:
        try:
            ip = ipaddress.ip_address(addr)
        except Exception:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise ValueError("不允许访问内网/本机地址")


def _fetch_http_url(url: str, *, max_bytes: int = MAX_SINGLE_FILE_BYTES, timeout_s: int = 15) -> tuple[str, bytes]:
    u = str(url or "").strip()
    parsed = urllib.parse.urlparse(u)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("仅支持 http/https URL")
    _check_public_host(parsed.hostname or "")

    req = urllib.request.Request(u, method="GET", headers={"User-Agent": "mcp-tools/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            ct = str(resp.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
            cl = resp.headers.get("content-length")
            try:
                if cl is not None and int(cl) > max_bytes:
                    raise ValueError("单个文件不能超过 30MB")
            except ValueError:
                raise
            except Exception:
                pass

            chunks: list[bytes] = []
            total = 0
            while True:
                b = resp.read(64 * 1024)
                if not b:
                    break
                total += len(b)
                if total > max_bytes:
                    raise ValueError("单个文件不能超过 30MB")
                chunks.append(b)
            blob = b"".join(chunks)
            if not blob:
                raise ValueError("文件内容为空")
            if not ct:
                guess = mimetypes.guess_type(u, strict=False)[0]
                ct = str(guess or "application/octet-stream").lower()
            return ct, blob
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"下载失败：{e}") from e


def _pick_ext(mime: str) -> str:
    m = str(mime or "").lower()
    known = _MIME_TO_EXT.get(m)
    if known:
        return known
    subtype = m.split("/", 1)[1] if "/" in m else ""
    subtype = re.sub(r"[^a-z0-9]+", "_", subtype.lower()).strip("_")
    if not subtype:
        return "bin"
    return subtype[:12] or "bin"


def save_files(
    inputs: list[str],
    *,
    subdir: str | None = None,
    filename_prefix: str | None = None,
    max_single_bytes: int = MAX_SINGLE_FILE_BYTES,
    max_files: int = MAX_FILES,
) -> dict[str, object]:
    items = [str(x).strip() for x in (inputs or []) if str(x or "").strip()]
    items = items[: max(0, int(max_files))]
    if not items:
        raise ValueError("files 不能为空")

    subdir0 = _sanitize_subdir(subdir) if isinstance(subdir, str) else None
    prefix = str(filename_prefix or "file").strip() or "file"
    prefix = re.sub(r"[^A-Za-z0-9._-]+", "_", prefix)[:32] or "file"

    saved: list[dict[str, object]] = []
    ts = time.strftime("%Y%m%d_%H%M%S")
    for idx, item in enumerate(items):
        if re.match(r"^data:", item, flags=re.I):
            mime, blob = _parse_data_url(item, max_bytes=max_single_bytes)
        elif re.match(r"^https?://", item, flags=re.I):
            mime, blob = _fetch_http_url(item, max_bytes=max_single_bytes)
        else:
            raise ValueError("仅支持 data URL 或 http/https URL")
        sha = hashlib.sha256(blob).hexdigest()
        ext = _pick_ext(mime)
        save_dir = _resolve_save_dir(mime, subdir0)
        os.makedirs(save_dir, exist_ok=True)
        name = f"{prefix}_{ts}_{idx + 1}_{sha[:10]}.{ext}"
        path = os.path.join(save_dir, name)
        with open(path, "wb") as f:
            f.write(blob)
        saved.append({"path": path, "mime": mime, "kind": _category_dirname(mime), "bytes": len(blob), "sha256": sha})

    base = str(_env("FILE_SAVE_DIR") or "").strip() or _default_save_dir()
    base = _resolve_path_from_root(base)
    return {"base_dir": base, "count": len(saved), "max_single_bytes": max_single_bytes, "files": saved}


def register(mcp) -> None:
    @mcp.tool(name="file_save", description="把文件（data URL 或 http/https URL）保存到本地目录（按类型分目录，支持子目录；单个文件<=30MB）")
    def file_save(
        files: list[str],
        subdir: str | None = None,
        filename_prefix: str | None = None,
        chat_type: str | None = None,
        user_id: str | None = None,
        group_id: str | None = None,
    ) -> str:
        try:
            enforce_daily_limits(tool_name="file_save", chat_type=chat_type, user_id=user_id, group_id=group_id)
            res = save_files(files, subdir=subdir, filename_prefix=filename_prefix, max_single_bytes=MAX_SINGLE_FILE_BYTES, max_files=MAX_FILES)
            return json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"错误：{e}"
