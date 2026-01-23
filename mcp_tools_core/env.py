import os


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def bootstrap_env() -> None:
    explicit = str(os.environ.get("MCP_TOOLS_ENV_FILE") or "").strip()
    env_file = explicit or os.path.join(ROOT_DIR, ".env")
    if not os.path.exists(env_file):
        return
    parsed = _load_dotenv_file(env_file)
    for k, v in parsed.items():
        if k not in os.environ:
            os.environ[k] = v


def env(name: str) -> str | None:
    v = os.environ.get(name)
    if not v:
        return None
    s = str(v).strip()
    return s or None


def project_abs(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(ROOT_DIR, path))
