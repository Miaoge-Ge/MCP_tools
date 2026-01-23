import os
import sys


def _ensure_import_path() -> None:
    base = os.path.dirname(os.path.abspath(__file__))
    if base not in sys.path:
        sys.path.insert(0, base)


_ensure_import_path()


from mcp_tools_core.env import bootstrap_env
from mcp_tools_core.server import serve
from mcp_tools_core.tooling import ToolRegistry
from mcp_tools_tools.date_tool import register as register_date
from mcp_tools_tools.model_name_tool import register as register_model
from mcp_tools_tools.now_tool import register as register_now
from mcp_tools_tools.reminders.tool import register as register_reminders
from mcp_tools_tools.vision_tool import register as register_vision
from mcp_tools_tools.web_search_tool import register as register_web_search
from mcp_tools_tools.weather_tool import register as register_weather


def main() -> int:
    bootstrap_env()
    reg = ToolRegistry(server_name="tools", server_version="0.1.0")
    register_now(reg)
    register_model(reg)
    register_date(reg)
    register_weather(reg)
    register_vision(reg)
    register_web_search(reg)
    register_reminders(reg)
    return serve(reg)


if __name__ == "__main__":
    raise SystemExit(main())
