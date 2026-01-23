from mcp.server.fastmcp import FastMCP

import os

from tools.date_tool import register as register_date
from tools.image_save_tool import register as register_image_save
from tools.model_name_tool import register as register_model
from tools.now_tool import register as register_now
from tools.reminders.tool import register as register_reminders
from tools.vision_tool import register as register_vision
from tools.web_search_tool import register as register_web_search
from tools.weather_tool import register as register_weather


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
    env_file = explicit or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_file):
        return
    parsed = _load_dotenv_file(env_file)
    for k, v in parsed.items():
        if k not in os.environ:
            os.environ[k] = v


def main() -> None:
    bootstrap_env()
    mcp = FastMCP(name="tools", json_response=False)
    register_now(mcp)
    register_model(mcp)
    register_date(mcp)
    register_weather(mcp)
    register_vision(mcp)
    register_web_search(mcp)
    register_reminders(mcp)
    register_image_save(mcp)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
