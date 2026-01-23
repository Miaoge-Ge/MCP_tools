import traceback

from mcp_tools_core.stdio_rpc import jsonrpc_error, jsonrpc_result, read_message
from mcp_tools_core.tooling import ToolRegistry


def serve(reg: ToolRegistry) -> int:
    while True:
        try:
            msg = read_message()
        except Exception as e:
            jsonrpc_error(None, -32700, "Parse error", {"error": str(e)})
            continue
        if msg is None:
            return 0
        if not isinstance(msg, dict):
            continue

        method = msg.get("method")
        id_ = msg.get("id")
        params = msg.get("params")
        if not method or id_ is None:
            continue

        if method == "initialize":
            pv = params.get("protocolVersion") if isinstance(params, dict) else None
            protocol_version = str(pv or "2024-11-05")
            jsonrpc_result(
                id_,
                {
                    "protocolVersion": protocol_version,
                    "serverInfo": {"name": reg.server_name, "version": reg.server_version},
                    "capabilities": {"tools": {}},
                },
            )
            continue

        if method == "tools/list":
            tools = []
            for t in reg.list_tools():
                tools.append(
                    {
                        "name": t.name,
                        "title": t.title,
                        "description": t.description,
                        "inputSchema": t.input_schema,
                    }
                )
            jsonrpc_result(id_, {"tools": tools})
            continue

        if method == "tools/call":
            if not isinstance(params, dict):
                jsonrpc_result(id_, {"content": [{"type": "text", "text": "参数错误：params 必须是对象"}]})
                continue
            name = str(params.get("name") or "").strip()
            args = params.get("arguments")
            if not isinstance(args, dict):
                args = {}
            if not reg.has_tool(name):
                jsonrpc_result(id_, {"content": [{"type": "text", "text": f"错误：未知工具 {name}"}]})
                continue
            try:
                text = reg.call(name, args)
            except Exception as e:
                text = f"错误：{str(e)}"
            jsonrpc_result(id_, {"content": [{"type": "text", "text": text}]})
            continue

        if method in ("ping", "$/ping"):
            jsonrpc_result(id_, {})
            continue

        jsonrpc_error(id_, -32601, f"Method not found: {method}", {"trace": traceback.format_exc(limit=2)})

