"""Image saving tool.

This tool stores incoming images (data URLs) to a local directory, intended for
“save/favorite this image” type commands from the chat layer.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time

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


_MIME_TO_EXT: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_save_dir() -> str:
    return os.path.join(_project_root(), "data", "images")


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


def _resolve_save_dir(subdir: str | None) -> str:
    base = str(_env("IMAGE_SAVE_DIR") or "").strip() or _default_save_dir()
    base = os.path.abspath(os.path.expanduser(base))
    sd = _sanitize_subdir(subdir)
    if not sd:
        return base
    out = os.path.abspath(os.path.join(base, sd))
    if os.path.commonpath([base, out]) != base:
        return base
    return out


def _parse_data_url(url: str) -> tuple[str, bytes]:
    s = str(url or "").strip()
    m = re.match(r"^data:(?P<mime>[^;]+);base64,(?P<data>[A-Za-z0-9+/=\s]+)$", s)
    if not m:
        raise ValueError("仅支持 data URL（data:<mime>;base64,...）")
    mime = str(m.group("mime") or "").strip().lower()
    data_b64 = re.sub(r"\s+", "", str(m.group("data") or ""))
    try:
        blob = base64.b64decode(data_b64, validate=True)
    except Exception as e:
        raise ValueError(f"base64 解码失败：{e}") from e
    if not blob:
        raise ValueError("图片内容为空")
    return mime or "application/octet-stream", blob


def _pick_ext(mime: str) -> str:
    return _MIME_TO_EXT.get(str(mime or "").lower(), "bin")


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="image_save", description="把图片（data URL）保存到本地目录（支持子目录）")
    def image_save(images: list[str], subdir: str | None = None, filename_prefix: str | None = None) -> str:
        imgs = [str(x).strip() for x in (images or []) if str(x or "").strip()]
        imgs = imgs[:10]
        if not imgs:
            return "错误：images 不能为空"

        subdir0 = _sanitize_subdir(subdir) if isinstance(subdir, str) else None
        prefix = str(filename_prefix or "img").strip() or "img"
        prefix = re.sub(r"[^A-Za-z0-9._-]+", "_", prefix)[:32] or "img"

        save_dir = _resolve_save_dir(subdir0)
        os.makedirs(save_dir, exist_ok=True)

        saved: list[dict[str, object]] = []
        ts = time.strftime("%Y%m%d_%H%M%S")
        for idx, u in enumerate(imgs):
            mime, blob = _parse_data_url(u)
            sha = hashlib.sha256(blob).hexdigest()
            ext = _pick_ext(mime)
            name = f"{prefix}_{ts}_{idx + 1}_{sha[:10]}.{ext}"
            path = os.path.join(save_dir, name)
            with open(path, "wb") as f:
                f.write(blob)
            saved.append({"path": path, "mime": mime, "bytes": len(blob), "sha256": sha})

        return json.dumps({"saved_dir": save_dir, "count": len(saved), "files": saved}, ensure_ascii=False, indent=2)
