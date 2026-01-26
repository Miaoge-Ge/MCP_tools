# MCP (Python, stdio)

[中文说明](README.zh-CN.md)

This repo provides a lightweight **MCP server** (Model Context Protocol) implemented in Python. It runs in **stdio mode** and exposes a small set of tools (vision, web search, weather, reminders, and utilities).

## Features

- **stdio MCP server**: easy to embed as a subprocess.
- **Tools**:
  - `image_understand`: image understanding via an OpenAI-compatible multimodal gateway
  - `file_save`: save files (data URLs or URLs) to local directory (typed subdirs; max 30MB per file)
  - `image_generate`: text-to-image (Ark/OpenAI-compatible and DashScope)
  - `bot_power_off` / `bot_power_on` / `bot_power_status`: group "power" (mute) control (admin-only)
  - `web_search`: search via Search1API or Serper
  - `weather_query`: Seniverse (心知天气)
  - `reminder_create` / `reminder_list` / `reminder_cancel`: reminders delivered via NapCat OneBot HTTP API
  - `now` / `get_date` / `get_model_name`
- Built with the official MCP Python SDK (FastMCP).
- **No secrets committed**: `.env` is ignored; `.env.example` is provided.

## Requirements

- Python 3.10+ (recommended)
- `mcp` Python package (see `requirements.txt`)

## Quick Start

1) Create your local environment file:

```bash
cp .env.example .env
```

2) Start the server (stdio mode):

```bash
python3 -m pip install -r requirements.txt
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
      "cwd": "/absolute/path/to/MCP",
      "envFile": "/absolute/path/to/MCP/.env",
      "enabled": true
    }
  ]
}
```

## Configuration

All configs are loaded from environment variables (typically via `.env`).

### Image understanding

- `VLM_UNDERSTAND_BASE_URL`: OpenAI-compatible chat/completions base URL
- `VLM_UNDERSTAND_API_KEY`: API key
- `VLM_UNDERSTAND_MODEL`: model name (e.g. `qwen3-vl-plus`)

### File saving

- `FILE_SAVE_DIR`: base directory for `file_save` (default `./data/files`)
  - Auto subdirectories by file type: `images/`, `videos/`, `audio/`, `text/`, `files/`, `others/`
  - Max file size: 30MB per single file

### Text-to-image

- `IMAGE_GENERATE_BASE_URL`: Ark/OpenAI compatible base URL (e.g. `https://ark.cn-beijing.volces.com/api/v3`)
- `IMAGE_GENERATE_API_KEY`: API key
- `IMAGE_GENERATE_MODEL`: model name (e.g. `doubao-seedream-4-5-251128`)
- `IMAGE_GENERATE_SIZE`: size (e.g. `2K`, depends on provider)
- `IMAGE_GENERATE_N`: number of images (1-4)
- `IMAGE_GENERATE_WATERMARK`: watermark (true/false)
- `IMAGE_GENERATE_SAVE_DIR`: save dir (default `./data/files/images/generated`)

### Tool quotas (optional)

- `tool_limits.json`: MCP tool quota config file. If missing or empty, no limits.
- `MCP_LIMITS_FILE`: optional override path (default `./tool_limits.json`)
- `MCP_TOOL_USAGE_FILE`: optional usage counter file (default `./data/tool_usage.json`)

Example:

```json
{
  "timezone": "Asia/Shanghai",
  "limits": {
    "web_search": { "per_user_per_day": 20, "per_day": 200 },
    "image_generate": { "per_user_per_day": 5 }
  }
}
```

### Group power (mute) control

- `BOT_ADMIN_QQ_IDS`: comma-separated QQ IDs. Only these users can call `bot_power_off` / `bot_power_on`
- `BOT_POWER_GROUP_IDS`: optional group allowlist (comma-separated). Empty means enabled for all groups
- `BOT_POWER_STATE_FILE`: optional state file path (default `./data/power_state.json`)

### NapCat (for reminders delivery)

- `NAPCAT_HTTP_URL`: OneBot HTTP API base URL
- `NAPCAT_HTTP_TOKEN`: token if enabled on the server
- `REMINDER_TIMEZONE`: timezone used for parsing/displaying reminders (IANA name), default `Asia/Shanghai`
- `TIMEZONE`: default timezone used by time/date tools (IANA name), default `Asia/Shanghai`

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
