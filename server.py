from mcp.server.fastmcp import FastMCP

import os

from tools.bot_power import register as register_bot_power
from tools.clock import register as register_clock
from tools.date import register as register_date
from tools.file_save import register as register_file_save
from tools.gold_alert import start_gold_alert_monitor
from tools.gold_price import register as register_gold_price
from tools.image_generate import register as register_image_generate
from tools.image_understand import register as register_image_understand
from tools.model import register as register_model
from tools.reminders.tool import register as register_reminders
from tools.web_search import register as register_web_search
from tools.weather_query import register as register_weather_query


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
    start_gold_alert_monitor()
    mcp = FastMCP(name="tools", json_response=False)
    register_clock(mcp)
    register_model(mcp)
    register_date(mcp)
    register_weather_query(mcp)
    register_image_understand(mcp)
    register_web_search(mcp)
    register_reminders(mcp)
    register_file_save(mcp)
    register_bot_power(mcp)
    register_image_generate(mcp)
    register_gold_price(mcp)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
