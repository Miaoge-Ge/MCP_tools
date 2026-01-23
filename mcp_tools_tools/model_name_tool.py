"""Model metadata tools."""

from __future__ import annotations

from typing import Any

from mcp_tools_core.env import env
from mcp_tools_core.tooling import ToolRegistry, register_decorated, tool


@tool(
    name="get_model_name",
    title="获取模型名称",
    description="获取当前使用的语言模型名称",
    input_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
)
def get_model_name(_: dict[str, Any]) -> str:
    """Return current configured LLM model name."""
    model = (env("LLM_MODEL") or "deepseek-v3").strip()
    if not model:
        return "错误：模型名称未配置或无效"
    return model


def register(registry: ToolRegistry) -> None:
    """Register tools in this module."""
    register_decorated(registry, globals())
