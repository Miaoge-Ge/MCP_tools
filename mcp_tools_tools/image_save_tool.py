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
from typing import Any

from mcp_tools_core.env import env
from mcp_tools_core.tooling import ToolRegistry, register_decorated, tool


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
    base = str(env("IMAGE_SAVE_DIR") or "").strip() or _default_save_dir()
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


@tool(
    name="image_save",
    title="保存图片",
    description="把图片（data URL）保存到本地目录（支持子目录）",
    input_schema={
        "type": "object",
        "properties": {
            "images": {"type": "array", "items": {"type": "string"}},
            "subdir": {"type": "string"},
            "filename_prefix": {"type": "string"},
        },
        "required": ["images"],
        "additionalProperties": False,
    },
)
def image_save(args: dict[str, Any]) -> str:
    images = args.get("images")
    if not isinstance(images, list):
        images = []
    images = [str(x).strip() for x in images if str(x or "").strip()]
    images = images[:10]
    if not images:
        return "错误：images 不能为空"

    subdir = _sanitize_subdir(args.get("subdir")) if isinstance(args.get("subdir"), str) else None
    prefix = str(args.get("filename_prefix") or "img").strip() or "img"
    prefix = re.sub(r"[^A-Za-z0-9._-]+", "_", prefix)[:32] or "img"

    save_dir = _resolve_save_dir(subdir)
    os.makedirs(save_dir, exist_ok=True)

    saved: list[dict[str, Any]] = []
    ts = time.strftime("%Y%m%d_%H%M%S")
    for idx, u in enumerate(images):
        mime, blob = _parse_data_url(u)
        sha = hashlib.sha256(blob).hexdigest()
        ext = _pick_ext(mime)
        name = f"{prefix}_{ts}_{idx + 1}_{sha[:10]}.{ext}"
        path = os.path.join(save_dir, name)
        with open(path, "wb") as f:
            f.write(blob)
        saved.append({"path": path, "mime": mime, "bytes": len(blob), "sha256": sha})

    return json.dumps({"saved_dir": save_dir, "count": len(saved), "files": saved}, ensure_ascii=False, indent=2)


def register(registry: ToolRegistry) -> None:
    """Register tools in this module."""
    register_decorated(registry, globals())

