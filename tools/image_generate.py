from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from openai import OpenAI

from tools.limits import enforce_daily_limits

_ENV_BOOTSTRAPPED = False
MAX_IMAGES = 4


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


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_output_dir() -> Path:
    return Path(_project_root()) / "data" / "files" / "images" / "generated"


def _resolve_output_dir(subdir: str | None) -> Path:
    base0 = str(_env("IMAGE_GENERATE_SAVE_DIR") or "").strip()
    if base0:
        p = Path(base0).expanduser()
        base = (p if p.is_absolute() else (Path(_project_root()) / p)).resolve()
    else:
        base = _default_output_dir()
    if not subdir:
        return base
    sd = str(subdir).strip().replace("\\", "/").strip("/")
    if not sd or sd in (".", "..") or ".." in sd.split("/"):
        return base
    out = (base / sd).resolve()
    try:
        if out == base or base in out.parents:
            return out
    except Exception:
        return base
    return base


def download_image(url: str, save_dir: Path, session: requests.Session, index: int = 0) -> Path:
    save_dir.mkdir(parents=True, exist_ok=True)

    parsed_path = urlparse(url).path
    filename = Path(unquote(parsed_path)).name
    if not filename or filename == "/":
        filename = f"image_{index}.png"

    filepath = save_dir / filename

    if filepath.exists():
        stem = filepath.stem
        suffix = filepath.suffix
        filepath = save_dir / f"{stem}_{index}{suffix}"

    resp = session.get(url, timeout=30)
    resp.raise_for_status()

    filepath.write_bytes(resp.content)
    return filepath


def generate_images(
    *,
    api_key: str,
    prompt: str,
    base_url: str,
    save_dir: Path,
    model: str,
    size: str,
    n: int,
    watermark: bool,
) -> list[Path]:
    client = OpenAI(base_url=base_url, api_key=api_key)
    try:
        response = client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            response_format="url",
            n=n,
            extra_body={"watermark": bool(watermark)},
        )
    except Exception as e:
        raise RuntimeError(f"Image generation failed: {e}") from e

    saved_files: list[Path] = []
    with requests.Session() as session:
        for i, item in enumerate(getattr(response, "data", []) or []):
            u = str(getattr(item, "url", "") or "").strip()
            if not u:
                continue
            path = download_image(u, save_dir, session, index=i)
            saved_files.append(path)
    if not saved_files:
        raise RuntimeError("Image generation failed: empty output")
    return saved_files


def register(mcp) -> None:
    @mcp.tool(name="image_generate", description="文生图：根据 prompt 生成图片并保存到本地（Ark/OpenAI 兼容 images.generate）")
    def image_generate(
        prompt: str,
        n: int | None = None,
        size: str | None = None,
        subdir: str | None = None,
        chat_type: str | None = None,
        user_id: str | None = None,
        group_id: str | None = None,
    ) -> str:
        try:
            enforce_daily_limits(tool_name="image_generate", chat_type=chat_type, user_id=user_id, group_id=group_id)

            api_key = str(_env("IMAGE_GENERATE_API_KEY") or "").strip()
            base_url = (
                str(_env("IMAGE_GENERATE_BASE_URL") or "")
                .strip()
                .strip("`")
                .strip()
                .strip('"')
                .strip("'")
            )
            model = str(_env("IMAGE_GENERATE_MODEL") or "doubao-seedream-4-5-251128").strip()
            size0 = str(size or "").strip() or str(_env("IMAGE_GENERATE_SIZE") or "2K").strip()
            n_raw = _env("IMAGE_GENERATE_N") or "1"
            n0 = int(n) if isinstance(n, int) else int(str(n_raw).strip() or "1")
            n0 = max(1, min(MAX_IMAGES, int(n0)))
            w_raw = _env("IMAGE_GENERATE_WATERMARK")
            watermark = str(w_raw or "").strip().lower() in ("1", "true", "yes", "y", "on")

            if not api_key or not base_url:
                return "错误：缺少文生图配置：请在 .env 设置 IMAGE_GENERATE_BASE_URL / IMAGE_GENERATE_API_KEY / IMAGE_GENERATE_MODEL"

            out_dir = _resolve_output_dir(subdir)
            files = generate_images(
                api_key=api_key,
                prompt=str(prompt or "").strip(),
                base_url=base_url,
                save_dir=out_dir,
                model=model,
                size=size0,
                n=n0,
                watermark=watermark if w_raw is not None else True,
            )
            return json.dumps(
                {
                    "base_url": base_url,
                    "model": model,
                    "size": size0,
                    "count": len(files),
                    "saved_dir": str(out_dir),
                    "files": [{"path": str(p)} for p in files],
                },
                ensure_ascii=False,
                indent=2,
            )
        except Exception as e:
            return f"错误：{e}"
