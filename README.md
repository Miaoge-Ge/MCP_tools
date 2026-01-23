# MCP Tools (Python, stdio)

[中文说明](README.zh-CN.md)

This repo provides a lightweight **MCP server** (Model Context Protocol) implemented in Python. It runs in **stdio mode** and exposes a small set of tools (vision, web search, weather, reminders, and utilities).

## Features

- **stdio MCP server**: easy to embed as a subprocess.
- **Tools**:
  - `vision_describe`: image understanding via an OpenAI-compatible multimodal gateway
  - `web_search`: search via Search1API or Serper
  - `weather_query`: Seniverse (心知天气)
  - `reminder_create` / `reminder_list` / `reminder_cancel`: reminders delivered via NapCat OneBot HTTP API
  - `now` / `get_date` / `get_model_name`
- **Decorator-style tool registration**: tools are declared with `@tool(...)` and registered automatically.
- **No secrets committed**: `.env` is ignored; `.env.example` is provided.

## Requirements

- Python 3.10+ (recommended)

## Quick Start

1) Create your local environment file:

```bash
cp .env.example .env
```

2) Start the server (stdio mode):

```bash
python3 server.py
```

Note: in stdio mode, the process may appear “silent” because it waits for MCP JSON-RPC messages on stdin.

## Integrate with a client

Example MCP client configuration (stdio subprocess):

```json
{
  "servers": [
    {
      "name": "tools",
      "command": "python3",
      "args": ["server.py"],
      "cwd": "/absolute/path/to/mcp_tools",
      "envFile": "/absolute/path/to/mcp_tools/.env",
      "enabled": true
    }
  ]
}
```

## Configuration

All configs are loaded from environment variables (typically via `.env`).

### Vision

- `VISION_BASE_URL`: OpenAI-compatible base URL (multimodal supported)
- `VISION_API_KEY`: API key
- `VISION_MODEL`: model name (e.g. `qwen3-vl-plus`)

### NapCat (for reminders delivery)

- `NAPCAT_HTTP_URL`: OneBot HTTP API base URL
- `NAPCAT_HTTP_TOKEN`: token if enabled on the server

### Web search (optional)

- `SEARCH_API_HOST`, `SEARCH_API_KEY` (Search1API)
- `SERPER_API_KEY` (Serper)

### Weather (optional)

Seniverse:
- `SENIVERSE_PUBLIC_KEY`, `SENIVERSE_PRIVATE_KEY`
- `SENIVERSE_API_HOST` (default `api.seniverse.com`)

## Security

- Do not commit `.env` or any real keys.
- This repo ignores `.env` / `.env.*` by default, and ships `.env.example`.

## Troubleshooting

- Vision tool fails with timeout: increase the client-side MCP/tool timeout (vision calls can be slower).
- Reminders not delivered: verify NapCat HTTP is reachable and token is correct.

