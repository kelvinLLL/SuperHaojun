# SuperHaojun

Personal AI coding agent harness — built as a ground-up reimplementation studying Claude Code's architecture.

Active implementation specs now live in `specs/`. Keep `docs/` for architecture analysis, research notes, and longer-form explanations.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (package manager)
- Node.js 18+ (only for WebUI frontend development)

## Quick Start

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure API keys

```bash
cp .env.example .env
# Edit .env — add your API keys
```

### 3. Configure models

Edit `models.yaml` to define your LLM endpoints:

```yaml
default: gpt-oss-120b-free

providers:
  openrouter:
    base_url: "https://openrouter.ai/api/v1"
    api_key: "${OPENROUTER_API_KEY}"

models:
  gpt-oss-120b-free:
    name: "OpenAI: gpt-oss-120b (free)"
    model_id: "openai/gpt-oss-120b:free"
    provider: openrouter
```

Add multiple profiles to switch between models in the app.

---

## Running

### CLI (terminal)

```bash
uv run superhaojun
```

Starts the interactive REPL. Type `/help` for commands, `Ctrl+C` to exit.

### TUI (rich terminal)

```bash
uv run superhaojun-tui
```

Starts the prompt_toolkit + Rich terminal UI through the same shared runtime assembly used by the CLI and WebUI.

### WebUI (browser)

**Production** (uses pre-built frontend):

```bash
uv run superhaojun-web
# Open: http://localhost:8765
```

**Development** (hot-reload frontend + backend):

Terminal 1 — backend:
```bash
uv run superhaojun-web
```

Terminal 2 — frontend dev server:
```bash
cd webui
npm install      # first time only
npm run dev
# Open: http://localhost:5173
```

The Vite dev server proxies `/api/*` to the backend at `localhost:8765`.

**Build frontend** (outputs to `src/superhaojun/webui/static/`):

```bash
cd webui
npm run build
```

---

## Configuration

### `models.yaml` — model profiles

Defines all LLM endpoints. Supports `${ENV_VAR}` interpolation in `api_key`.

| Field | Description |
|-------|-------------|
| `default` | Which profile is active on startup |
| `models.<key>.name` | Display name in WebUI |
| `models.<key>.model_id` | Model identifier passed to the API |
| `models.<key>.base_url` | OpenAI-compatible API base URL |
| `models.<key>.api_key` | API key (or `${ENV_VAR}`) |
| `models.<key>.provider` | `openai` / `anthropic` / `deepseek` |

### `.env` — secrets

Holds API keys referenced by `models.yaml`. Also used as fallback single-model config if `models.yaml` is absent.

### `.haojun/hooks.json` — hook rules

Lifecycle hook rules (pre/post tool use, session events). Created automatically on first save.

### `.haojun/mcp.json` — MCP servers

MCP server configurations for the current project.

### `~/.haojun/mcp.json` — global MCP servers

User-level MCP servers available across all projects.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SUPERHAOJUN_PORT` | `8765` | WebUI server port |

---

## Project Structure

```
superhaojun/
├── specs/                # Active SDD specs, templates, and doc contracts
├── src/superhaojun/
│   ├── agent.py          # Core agent loop
│   ├── config.py         # ModelConfig + ModelRegistry
│   ├── bus.py            # MessageBus (event routing)
│   ├── tools/            # Built-in tools (read, write, bash, glob, grep…)
│   ├── hooks/            # Lifecycle hooks (14 events, shell + function)
│   ├── mcp/              # MCP client + server manager
│   ├── lsp/              # Language server client
│   ├── agents/           # SubAgent + Coordinator
│   ├── compact/          # Context compaction
│   ├── extensions/       # Repo-local extension runtime
│   ├── memory/           # Persistent memory store
│   ├── session/          # Session persistence (JSONL)
│   ├── prompt/           # System prompt builder (section registry)
│   ├── transport/        # Experimental transport helpers
│   ├── tui/              # Terminal UI (prompt_toolkit + rich)
│   └── webui/            # FastAPI server + static frontend
├── webui/                # React + TypeScript frontend source
│   └── src/
├── models.yaml           # Model profiles (multi-model config)
├── .env                  # API keys (gitignored)
├── docs/                 # Architecture documentation and research notes
└── tests/                # Regression coverage for backend modules
```

---

## Slash Commands

| Command | Description |
|---------|-------------|
| `/help` | List all commands |
| `/clear` | Clear conversation history |
| `/compact` | Manually trigger context compaction |
| `/extensions` | List or toggle repo-local extensions |
| `/memory` | Show memory entries |
| `/mcp list` | List MCP server status |
| `/mcp enable <name>` | Enable a MCP server |
| `/mcp disable <name>` | Disable a MCP server |
| `/mcp reconnect <name>` | Reconnect a MCP server |
| `/agents run <goal>` | Run multi-agent task with LLM planning |
| `/quit` | Exit |

---

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/test_hooks.py -v
```
