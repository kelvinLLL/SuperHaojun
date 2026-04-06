# SuperHaojun Architecture Document

> A personal AI coding agent harness, built from scratch in Python.
> Informed by deep study of Claude Code's architecture, but not a clone — a redesign with different trade-offs.

---

## 1. Project Identity

**SuperHaojun** is a terminal-based AI coding assistant that communicates with LLMs via the OpenAI-compatible API. It can read/write/edit files, execute shell commands, search codebases, and manage multi-turn conversations with streaming responses.

| Metric | Value |
|--------|-------|
| Language | Python 3.12+, strict typing |
| Package manager | uv |
| LLM communication | openai SDK (direct, no framework) |
| Source lines | ~2,600 (src) + ~1,300 (tests) |
| Test files | 10 test modules |
| Dependencies | openai, pydantic-settings, httpx |

---

## 2. Design Methodology

### 2.1 Learn from the best, then redesign

The project started with a comprehensive reverse-engineering study of Claude Code (Anthropic's official CLI agent, ~100k+ lines TypeScript). 12 deep-dive documents were produced covering every subsystem. Rather than porting Claude Code to Python, we extracted its **design principles** and rebuilt with Python-native patterns, resulting in an order-of-magnitude simpler codebase that retains the architectural strengths.

### 2.2 Incremental feature delivery

Features are delivered one at a time in strict dependency order. Each feature:
1. Defines its interface contract (ABC or protocol)
2. Writes failing tests first (TDD)
3. Implements the minimal viable version
4. Documents insights and trade-off decisions

### 2.3 Architecture-first iteration

When a foundational assumption proves wrong, we fix the architecture before adding more features. This happened once already:

- **v1 (EventEmitter pattern)**: Agent yielded `AsyncIterator[AgentEvent]`. Worked for text streaming, but couldn't support true permission request-response (consumer can't "reply" into an iterator), cross-process communication, or message replay.
- **v2 (Transport + MessageBus)**: Replaced with a message-passing architecture inspired by Claude Code's Transport → Bridge → Handler pattern. This is the current architecture.

---

## 3. Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                        main.py (REPL)                        │
│  Registers handlers on MessageBus for rendering + user input │
└──────────────┬───────────────────────────────┬───────────────┘
               │  bus.on("text_delta", ...)    │  bus.emit(PermissionResponse)
               ▼                               ▼
┌──────────────────────────────────────────────────────────────┐
│                     MessageBus (bus.py)                       │
│  • Message routing by TYPE discriminator                     │
│  • UUID deduplication (BoundedUUIDSet, ring buffer)          │
│  • Request-response coordination (expect / wait_for)         │
│  • Async handler dispatch (sync or coroutine)                │
└──────────────┬───────────────────────────────┬───────────────┘
               │  bus.emit(TextDelta)           │  bus.wait_for("permission_response")
               ▼                               ▼
┌──────────────────────────────────────────────────────────────┐
│                      Agent (agent.py)                         │
│  • Conversation history (ChatMessage list)                   │
│  • Streaming LLM calls (openai SDK)                          │
│  • Tool call detection + execution loop                      │
│  • Permission flow via bus request-response                  │
└──────────────┬───────────────────────────────┬───────────────┘
               │                               │
    ┌──────────▼──────────┐       ┌────────────▼────────────┐
    │   ToolRegistry      │       │  PermissionChecker      │
    │   7 built-in tools  │       │  rule matching engine   │
    └─────────────────────┘       └─────────────────────────┘
```

### Data flow for a user message:

```
1. User types "read pyproject.toml"
2. REPL sends:  agent.handle_user_message("read pyproject.toml")
3. Agent emits: bus.emit(AgentStart)  →  bus.emit(TurnStart)
4. Agent calls: openai streaming API
5. LLM returns: tool_call(read_file, {path: "pyproject.toml"})
6. Agent emits: bus.emit(TurnEnd(finish_reason="tool_calls"))
7. Permission:  checker.check("read_file", "read") → ALLOW
8. Agent emits: bus.emit(ToolCallStart(...))
9. Tool runs:   ReadFileTool.execute(path="pyproject.toml")
10. Agent emits: bus.emit(ToolCallEnd(...))
11. Loop back:   Agent calls LLM again with tool result
12. LLM returns: text response summarizing the file
13. Agent emits: bus.emit(TextDelta(...))  ×N chunks
14. Agent emits: bus.emit(TurnEnd) → bus.emit(AgentEnd)
```

For a **dangerous tool** (e.g., bash), step 7 changes:
```
7a. checker.check("bash", "dangerous") → ASK
7b. Agent:  future = bus.expect("permission_response", match_id=tool_call_id)
7c. Agent:  bus.emit(PermissionRequest(...))
7d. REPL handler prompts: "Allow? [y/n]"
7e. User types: "y"
7f. REPL:   bus.emit(PermissionResponse(granted=True))
7g. Agent:  response = await future  →  granted=True  →  proceed
```

---

## 4. Module-by-Module Design

### 4.1 Message Protocol (`messages.py`)

**What**: Defines all structured messages as frozen dataclasses with a `TYPE` class variable for discrimination.

**Why this design**:
- Frozen dataclasses are immutable value objects — safe to pass across async boundaries
- `TYPE` ClassVar acts as a discriminated union tag (like TypeScript's `type` literal field)
- Every message carries `id` (UUID for dedup) and `timestamp` (epoch seconds)
- `message_to_dict()` / `message_from_dict()` provide serialization at transport boundaries
- A decorator-based `_REGISTRY` maps TYPE strings to classes for deserialization

**Message taxonomy**:

| Direction | Messages | Purpose |
|-----------|----------|---------|
| Outbound (Agent → Consumer) | TextDelta, ToolCallStart, ToolCallEnd, PermissionRequest, TurnStart, TurnEnd, AgentStart, AgentEnd, Error | Agent lifecycle events |
| Inbound (Consumer → Agent) | UserMessage, PermissionResponse, Interrupt | User actions and control |

**Trade-offs**:
- (+) Messages are transport-ready: `to_dict()` produces JSON-serializable dicts
- (+) UUID enables dedup across reconnects (future WebSocket/SSE transport)
- (+) Type registry enables open extension without modifying deserialization code
- (-) No schema validation (unlike Claude Code's Zod schemas). Acceptable for now — all producers are internal

**Contrast with Claude Code**: Claude Code defines 25+ message types via Zod schemas in `coreSchemas.ts`. We use Python dataclasses with a simpler `@_register` decorator pattern. Same principle (discriminated union on `type`), lighter implementation.

### 4.2 Transport Layer (`transport/`)

**What**: Abstract message delivery across boundaries. Currently one implementation.

**Interface** (`Transport` ABC):
```python
async def send(message) -> None
async def receive() -> Message
async def close() -> None
```

**LocalTransport**: Two linked `asyncio.Queue` instances. `create_pair()` returns `(agent_side, consumer_side)` where A's outbound is B's inbound.

**Why this design**:
- Decouples message delivery from message semantics
- Same `send()`/`receive()` contract works for in-process queues, WebSocket, stdio, or HTTP SSE
- `create_pair()` pattern mirrors Unix socketpair — two ends, bidirectional
- Adding a new transport (e.g., for sub-agents via subprocess stdio) requires zero changes to Agent or MessageBus

**Contrast with Claude Code**: Claude Code has 5 transport implementations (WebSocket, Hybrid, SSE, CCR, stdio) built over years. We start with one and the ABC ensures the same extension path is available.

### 4.3 MessageBus (`bus.py`)

**What**: Central message dispatcher. Routes messages by type, deduplicates, and coordinates request-response flows.

**Core mechanisms**:

1. **`emit(message)`**: Dedup check → resolve any pending waiters → dispatch to registered handlers
2. **`on(type, handler)`**: Register a handler (sync or async) for a message type
3. **`expect(type, match_id)`**: Create an `asyncio.Future` that resolves when a matching message arrives
4. **`wait_for(type, match_id)`**: Convenience for `await expect(...)`

**BoundedUUIDSet**: Ring buffer + set for O(1) dedup with bounded memory. When the ring wraps, the oldest UUID is evicted. Capacity: 2000 messages (configurable). Directly mirrors Claude Code's implementation in `bridgeMessaging.ts`.

**Why this design**:
- **Not EventEmitter**: EventEmitter is fire-and-forget broadcast. MessageBus adds dedup + request-response coordination. The `expect()`/`wait_for()` pattern enables true blocking request-response (e.g., permission flow) without callback hell.
- **Async handler dispatch**: `asyncio.create_task(handler(msg))` for coroutine handlers. This means a permission request handler can prompt the user (blocking I/O via `run_in_executor`) without blocking other message processing.
- **Waiter resolution before handler dispatch**: This ensures `await bus.wait_for(...)` resolves before handlers run, preventing race conditions in the permission flow.

**Trade-offs**:
- (+) Permission flow is now truly interactive (not auto-approve)
- (+) Dedup is built-in, not bolted on
- (+) Same pattern scales to cross-process (just swap transport)
- (-) More moving parts than a simple iterator
- (-) Handler ordering is registration-order (not priority-based). Sufficient for now.

**Contrast with Claude Code**: Claude Code's Bridge (`replBridge.ts`, 2400 lines) handles session lifecycle, reconnection, epoch negotiation, flush gating, and echo filtering in addition to routing. Our MessageBus (~130 lines) focuses on the core: routing + dedup + request-response. The rest will be added when the corresponding features demand it.

### 4.4 Agent (`agent.py`)

**What**: Stateful conversation engine. Manages chat history, streams LLM responses, detects tool calls, orchestrates execution.

**Key design decisions**:

1. **Dataclass, not class hierarchy**: `Agent` is a `@dataclass` with explicit fields. No inheritance, no mixins. Easy to construct in tests with mock dependencies.

2. **MessageBus-driven, not iterator-driven**: `handle_user_message()` is `async def`, not `async generator`. It emits messages through the bus instead of yielding events. This enables bidirectional communication (the agent can wait for responses).

3. **Tool execution strategy — two-phase concurrent/sequential**:
   ```
   Phase 1: asyncio.gather(*[run(tc) for tc in concurrent_safe_tools])
   Phase 2: for tc in sequential_tools: await run(tc)
   ```
   Tools declare `is_concurrent_safe` (default True). Read-only tools run in parallel; write/dangerous tools run sequentially. This matches Claude Code's `toolOrchestration.ts` pattern.

4. **Permission as request-response**:
   ```python
   future = self.bus.expect("permission_response", match_id=tc.id)
   await self.bus.emit(PermissionRequest(...))
   response = await future  # blocks until consumer responds
   ```
   The `expect()` call sets up the Future BEFORE emitting the request, preventing race conditions where the response arrives before we're listening.

5. **Streaming accumulation**: Tool call arguments arrive as partial JSON chunks across multiple stream deltas, indexed by `tool_call.index`. We accumulate into a `dict[int, ToolCallInfo]` buffer and concatenate after the stream ends.

**Contrast with Claude Code**: Claude Code's query loop (`query.ts`, ~2000 lines) handles context compaction, reactive retry, file state caching, and multi-agent delegation in addition to the core loop. Our Agent (~265 lines) implements only the core loop. Each additional concern will be a separate module that hooks into the bus.

### 4.5 Tool System (`tools/`)

**What**: Pluggable tool framework with 7 built-in tools.

**Design pattern**: Abstract Base Class with 4 required + 2 optional properties:

| Property | Required | Purpose |
|----------|----------|---------|
| `name` | Yes | OpenAI function calling identifier |
| `description` | Yes | Helps LLM decide when to use the tool |
| `parameters` | Yes | JSON Schema for arguments |
| `execute(**kwargs)` | Yes | Run the tool, return result string |
| `is_concurrent_safe` | No (default: True) | Can this run in parallel? |
| `risk_level` | No (default: "read") | Permission classification |

**Built-in tools**:

| Tool | risk_level | concurrent_safe | Description |
|------|-----------|-----------------|-------------|
| ReadFile | read | True | Read file with line numbers |
| WriteFile | write | False | Create/overwrite file |
| EditFile | write | False | Exact string replacement |
| Bash | dangerous | False | Shell command execution |
| Glob | read | True | File pattern search |
| Grep | read | True | Content search with regex |
| ListDir | read | True | Directory listing |

**`to_openai_tool()`** converts any Tool to the OpenAI function calling format. The ToolRegistry holds all registered tools and provides `to_openai_tools()` for the API call + `get(name)` for execution dispatch.

**Trade-offs**:
- (+) Adding a new tool = one file, one class, 4 properties
- (+) `risk_level` and `is_concurrent_safe` are declarative — the agent loop reads them, tools don't enforce them
- (+) JSON Schema parameters are the OpenAI-native format — no translation layer
- (-) No input validation beyond what JSON Schema provides (Claude Code uses Zod for runtime validation)
- (-) `execute()` returns `str` only — no structured results (sufficient for LLM consumption)

**Contrast with Claude Code**: Claude Code's `Tool.ts` interface has ~30 methods (permissions, UI hints, progress callbacks, destructiveness checks, help text). Our Tool ABC has 6 properties. The minimal surface keeps the learning curve flat; we'll expand only when a feature demands it.

### 4.6 Command System (`commands/`)

**What**: `/slash` command framework with 7 built-in commands.

Same ABC pattern as tools: `Command` base class with `name`, `description`, `execute(args, context)`.

`CommandRegistry` provides `get()` for dispatch and `completions(prefix)` for autocomplete suggestions. The REPL intercepts `/`-prefixed input before it reaches the agent.

**Built-in commands**: /help, /clear, /quit, /exit, /messages, /model, /tools

**Trade-offs**:
- (+) Clean separation: commands are UI concerns, tools are LLM concerns
- (+) `completions()` enables future Tab-completion
- (-) Commands access agent internals via `CommandContext.agent` — loose coupling but not fully decoupled

### 4.7 Permission System (`permissions/`)

**What**: Three-tier permission checking for tool execution.

**Decision enum**: `ALLOW | DENY | ASK`

**Matching priority**:
1. Exact tool name rule (`_tool_rules["bash"] → DENY`)
2. Risk level rule (`_risk_rules["dangerous"] → ASK`)
3. Default policy (`read → ALLOW`, `write/dangerous → ASK`)

**How ASK works** (with MessageBus):
- Agent emits `PermissionRequest` via bus
- REPL handler receives it, prompts user, emits `PermissionResponse`
- Agent awaits the response via `bus.wait_for()`

**Trade-offs**:
- (+) Declarative rules — can be loaded from config file
- (+) `allow_always()` / `deny_always()` for session-level overrides
- (-) No persistent rule storage yet (Feature 9 will add this)
- (-) No per-input validation (e.g., "allow bash but only for `git` commands")

---

## 5. Configuration (`config.py`)

**EnvConfig** (pydantic-settings BaseSettings): Auto-reads from `.env` file and environment variables. Fields: `openai_api_key`, `openai_base_url`, `model_id`, `model_provider`.

**ModelConfig** (frozen dataclass): Immutable runtime config. Auto-detects `is_reasoning` from model name pattern (matches `o1`-`o9`, `gpt-5`).

**SSL handling**: Custom `ssl.SSLContext` with `check_hostname=False` for personal proxy endpoints. Scoped to a single `httpx.AsyncClient` instance — more precise than global `NODE_TLS_REJECT_UNAUTHORIZED=0`.

---

## 6. Architectural Decisions Log

### Why Python, not TypeScript

- User's primary language; strongest ecosystem for ML/data/automation
- openai Python SDK has feature parity with the JS version
- pydantic-settings > dotenv for type-safe configuration
- uv provides npm-like speed for Python package management

### Why openai SDK directly, not a framework

- `chat.completions.create(stream=True)` + function calling covers 100% of agent needs
- Agent loop is ~100 lines of core logic — a framework would add abstraction without reducing complexity
- Direct SDK means we control every parameter, retry, and error path
- LangChain/pydantic-ai can be evaluated later if multi-provider switching becomes a priority

### Why Transport+MessageBus, not EventEmitter

| Concern | EventEmitter | Transport+MessageBus |
|---------|-------------|---------------------|
| Permission flow | Can't block-and-wait in an iterator | `expect()` + `wait_for()` enables true request-response |
| Cross-process | In-memory only | Transport abstraction works across process boundaries |
| Deduplication | Not built-in | BoundedUUIDSet ring buffer, O(1) |
| Serialization | Objects in memory | `to_dict()`/`from_dict()` at transport boundary |
| Message replay | Lost on reconnect | UUID + timestamp enable future replay |
| Extensibility | New consumer = new iterator consumer | New consumer = register handlers on bus |

### Why BoundedUUIDSet (ring buffer), not unbounded Set

Unbounded sets grow forever in long sessions. Ring buffer caps memory at `O(capacity)` while providing O(1) lookup. Oldest UUIDs are evicted — acceptable because dedup only needs to cover the recent window (retransmissions happen within seconds, not hours).

---

## 7. What's Not Here Yet (and Where It Will Go)

| Future Feature | Integration Point | Principle |
|---------------|-------------------|-----------|
| Context Compaction | New module `compact/`, hooks into agent before LLM call | Token counting + LLM-generated summary |
| System Prompt Engineering | New module `prompt/`, agent reads at turn start | Dynamic assembly from project context + user instructions |
| Session Persistence | New module `session/`, serializes `ChatMessage` list | Messages already have `to_dict()` — storage is straightforward |
| Memory System | New module `memory/`, cross-session key-value store | Loaded into system prompt at session start |
| Hooks | Handler registration on MessageBus | `bus.on("tool_call_start", hook_fn)` — zero new abstractions |
| MCP Integration | New Transport implementation + tool registration | MCP server tools register into existing ToolRegistry |
| Multi-Agent | Each sub-agent gets its own MessageBus + Transport pair | LocalTransport for in-process, StdioTransport for subprocess |
| TUI / IDE | Replace REPL handlers with rich rendering | Same bus, different handlers — no agent changes needed |

The architecture is designed so that each future feature is **additive** (new module + handler registration), not **invasive** (modifying existing modules).
