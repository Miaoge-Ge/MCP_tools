# MCP（Python，stdio）

[English README](README.md)

这是一个用 Python 实现的轻量 **MCP Server（Model Context Protocol）**，采用 **stdio 模式**运行，通过子进程方式给上层应用提供外部工具能力：识图、联网搜索、天气、提醒，以及一些基础工具。

## 功能

- **stdio MCP server**：适合被宿主程序以子进程方式拉起（stdin/stdout JSON-RPC）。
- **工具列表**：
  - `vision_describe`：识图（OpenAI 兼容多模态网关）
  - `image_save`：保存图片（data URL）到本地目录
  - `web_search`：联网搜索（Search1API / Serper）
  - `weather_query`：天气查询（心知天气 Seniverse）
  - `reminder_create` / `reminder_list` / `reminder_cancel`：提醒（通过 NapCat OneBot HTTP API 投递）
  - `now` / `get_date` / `get_model_name`：基础工具
- 基于官方 MCP Python SDK（FastMCP）。
- **不提交密钥**：默认忽略 `.env`，提供 `.env.example` 模板。

## 运行前提

- Python 3.10+（推荐）
- 需要安装 `mcp` 依赖（见 `requirements.txt`）

## 快速开始

1）创建本地配置：

```bash
cp .env.example .env
```

2）启动 MCP server（stdio 模式）：

```bash
python3 -m pip install -r requirements.txt
python3 server.py
```

注意：stdio 模式下进程可能看起来“没输出”，这是正常的，它在等待 MCP 客户端通过 stdin 发送请求。

## 接入到客户端

stdio 子进程方式的 MCP 配置示例：

```json
{
  "servers": [
    {
      "name": "tools",
      "command": "python3",
      "args": ["server.py"],
      "cwd": "/绝对路径/MCP",
      "envFile": "/绝对路径/MCP/.env",
      "enabled": true
    }
  ]
}
```

## 配置（环境变量）

项目通过环境变量读取配置（通常写在 `.env`）。

### 识图

- `VISION_BASE_URL`：支持多模态的 OpenAI 兼容网关 base url
- `VISION_API_KEY`：key
- `VISION_MODEL`：模型名（例如 `qwen3-vl-plus`）

### 保存图片

- `IMAGE_SAVE_DIR`：`image_save` 保存图片的目录（默认 `./data/images`）

### NapCat（提醒投递）

- `NAPCAT_HTTP_URL`：OneBot HTTP API 地址
- `NAPCAT_HTTP_TOKEN`：如果 NapCat HTTP 开了 token，这里必须一致
- `REMINDER_TIMEZONE`：提醒解析与展示用的时区（IANA 名称），默认 `Asia/Shanghai`
- `TIMEZONE`：时间/日期工具默认时区（IANA 名称），默认 `Asia/Shanghai`

### 联网搜索（可选）

- `SEARCH_API_HOST`、`SEARCH_API_KEY`（Search1API）
- `SERPER_API_KEY`（Serper）

### 天气（可选）

心知天气 Seniverse：
- `SENIVERSE_PUBLIC_KEY`、`SENIVERSE_PRIVATE_KEY`
- `SENIVERSE_API_HOST`（默认 `api.seniverse.com`）

## 安全提示

- 不要提交 `.env` 或任何真实 key。
- 本仓库默认忽略 `.env` / `.env.*`，并提供 `.env.example`。

## 排障

- 识图经常超时：识图链路较慢，优先把“客户端侧”的工具超时调大。
- 提醒投递失败：检查 NapCat HTTP 连通性与 token 是否正确。
