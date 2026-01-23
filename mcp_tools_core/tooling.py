from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable


ToolHandler = Callable[[dict[str, Any]], str]


@dataclass(frozen=True)
class ToolDef:
    """A single MCP tool definition."""

    name: str
    title: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler


def tool(
    *,
    name: str,
    title: str,
    description: str,
    input_schema: dict[str, Any],
) -> Callable[[ToolHandler], ToolHandler]:
    """Decorator to declare a tool handler in a module.

    The decorated function will carry a ToolDef in attribute "__mcp_tool_def__",
    and can be registered via register_decorated().
    """

    def decorator(fn: ToolHandler) -> ToolHandler:
        if not callable(fn):
            raise TypeError("tool decorator can only be applied to callables")
        setattr(
            fn,
            "__mcp_tool_def__",
            ToolDef(name=str(name), title=str(title), description=str(description), input_schema=input_schema, handler=fn),
        )
        return fn

    return decorator


def register_decorated(registry: "ToolRegistry", namespace: dict[str, Any]) -> None:
    """Register all @tool-decorated handlers found in the given namespace."""
    items = list(namespace.values())
    for obj in items:
        if not callable(obj):
            continue
        tool_def = getattr(obj, "__mcp_tool_def__", None)
        if isinstance(tool_def, ToolDef):
            registry.register(tool_def)


class ToolRegistry:
    """In-memory tool registry for a single MCP server instance."""

    def __init__(self, server_name: str, server_version: str) -> None:
        self.server_name = str(server_name)
        self.server_version = str(server_version)
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool_def: ToolDef) -> None:
        self._tools[tool_def.name] = tool_def

    def list_tools(self) -> list[ToolDef]:
        return list(self._tools.values())

    def has_tool(self, name: str) -> bool:
        return str(name) in self._tools

    def call(self, name: str, args: dict[str, Any]) -> str:
        tool_def = self._tools.get(str(name))
        if not tool_def:
            raise KeyError(name)
        out = tool_def.handler(args)
        if isinstance(out, str):
            return out
        if inspect.isawaitable(out):
            raise TypeError("Async tool handlers are not supported")
        return str(out)
