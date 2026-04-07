# SuperHaojun Architecture: Phase E & F

> Phase E: 扩展与集成 — Hooks 系统 + MCP 集成 + LSP 集成
> Phase F: 高级能力 — Multi-Agent + TUI
>
> 本文档记录设计决策、源码实现、与 Claude Code 的对比分析。

---

## 度量快照

| 指标 | Phase C+D v2 结束 | Phase E+F 结束 | 增量 |
|------|------------------|---------------|------|
| 源码行数 | ~3,480 | ~5,264 | +1,784 |
| 模块数 | 13 | 18 | +5 (hooks, mcp, lsp, agents, tui) |
| 新增文件 | — | 16 (.py) | — |
| 新增外部依赖 | — | prompt_toolkit, rich | TUI 层 |

### 新模块行数

| 模块 | 行数 | 文件数 | 核心职责 |
|------|------|--------|---------|
| hooks/ | 276 | 3 | 配置驱动的 pre/post 工具钩子 |
| mcp/ | 374 | 4 | MCP 服务器连接 + 工具适配 |
| lsp/ | 501 | 3 | 语言服务器客户端 + 代码智能聚合 |
| agents/ | 292 | 4 | SubAgent + AgentTool + Coordinator |
| tui/ | 320 | 3 | prompt_toolkit 输入 + rich 渲染 |
| **合计** | **1,763** | **17** | |

---

## Phase E: 扩展与集成

### E1. Hooks 系统 (`hooks/`, 276 行)

#### 架构概览

Hooks 系统允许用户在工具执行前后注入自定义 shell 命令。配置驱动，无需修改代码。

```
hooks/
├── config.py    # HookConfig + HookRule + HookTiming (131 行)
├── runner.py    # HookRunner — 执行引擎 (139 行)
└── __init__.py
```

#### 配置模型 (`hooks/config.py`)

**HookRule** — 单条钩子规则 (frozen dataclass):

```python
@dataclass(frozen=True)
class HookRule:
    tool_pattern: str      # glob 模式或精确名称，如 "bash", "write_*"
    timing: HookTiming     # "pre" 或 "post"
    command: str           # shell 命令模板，支持变量替换
    timeout: int = 10      # 最大执行秒数
    enabled: bool = True   # 是否启用
```

- `tool_pattern` 使用 `fnmatch.fnmatch()` 进行 glob 匹配
- `command` 支持 `{tool_name}`, `{arguments}`, `{result}` (仅 post), `{cwd}` 占位符

**HookConfig** — 规则集合，支持 JSON 文件持久化:

```json
// .haojun/hooks.json
{
  "hooks": [
    {
      "tool_pattern": "bash",
      "timing": "pre",
      "command": "echo 'About to run: {arguments}'",
      "timeout": 5
    },
    {
      "tool_pattern": "write_*",
      "timing": "post",
      "command": "echo 'Wrote file' >> /tmp/hook.log"
    }
  ]
}
```

- `HookConfig.load(path)` — 从 JSON 加载，文件缺失或格式错误返回空配置
- `HookConfig.save(path)` — 序列化到 JSON（供命令行管理）
- `get_rules(tool_name, timing)` — 按工具名 + 时机查询匹配规则

#### 执行引擎 (`hooks/runner.py`)

**HookRunner** — 执行 hook 命令:

```python
@dataclass
class HookRunner:
    config: HookConfig
    working_dir: str = "."

    async def run_pre_hooks(self, tool_name, arguments) -> list[HookResult]
    async def run_post_hooks(self, tool_name, arguments, result="") -> list[HookResult]
    @staticmethod
    def all_passed(results) -> bool
```

**执行流程**:

1. `get_rules(tool_name, timing)` 查找匹配规则
2. 对匹配规则并行执行 (`asyncio.gather`)
3. 变量替换：`rule.command.format(tool_name=..., arguments=..., result=..., cwd=...)`
4. `asyncio.create_subprocess_shell()` 执行，`asyncio.wait_for(timeout)` 限时
5. 返回 `HookResult(rule, exit_code, stdout, stderr, timed_out)`

**Pre/Post 语义差异**:

- **Pre-hook**: `exit_code != 0` 或 `timed_out` → 工具执行被阻止
- **Post-hook**: 失败仅 log 警告，不影响工具结果
- Agent 集成 (`agent.py:241-257`): pre-hook 检查在 ToolCallStart 之后、`tool.execute()` 之前；post-hook 在 execute 之后、ToolCallEnd 之前

**错误处理**:

- 占位符缺失：`format()` 的 `KeyError` 被捕获，退化为原始命令
- 超时：`proc.kill()` 强制终止，返回 `timed_out=True`
- 进程异常：捕获 `Exception`，返回 `exit_code=-1`

#### 对比 Claude Code

| 维度 | SuperHaojun | Claude Code |
|------|-------------|-------------|
| 代码量 | 276 行 (3 文件) | ~3,721 行 (17 文件) |
| 配置格式 | JSON (`.haojun/hooks.json`) | Frontmatter YAML + JSON settings + runtime API |
| Hook 类型 | 1 种 (shell command) | 5 种 (Command, Prompt, Agent, HTTP, Function) |
| 生命周期事件 | 2 (pre/post tool) | 23 (SessionStart, PreToolUse, PostToolUse, Stop...) |
| 匹配策略 | glob 模式 | Matcher 优先级链 (Local > Project > User > Plugin) |
| 执行 | `asyncio.create_subprocess_shell` | 多种执行器 (shell, LLM prompt, subagent, HTTP) |
| Hook 变量 | 4 个占位符 | 完整事件 context 注入 |
| 配置来源 | 单文件 | 多源合并 (policy, user, project, local) |

**收获**: 276 行实现了核心的 pre/post shell hook 能力，覆盖最常用场景（如 lint、logging、审计）。glob 匹配 + 变量替换 + 超时保护提供了足够的灵活性。

**差距**: CC 的 hook 系统是一个完整的插件运行时——支持 LLM prompt 注入 hook（动态修改 system prompt）、agent hook（触发子 agent）、HTTP hook（webhook 回调）。CC 的 23 个生命周期事件覆盖了从 session 启动到退出的全链路，而我们只挂接了工具执行。

---

### E2. MCP 集成 (`mcp/`, 374 行)

#### 架构概览

实现 Model Context Protocol 客户端，连接外部 MCP 服务器，将其工具适配为本地 `Tool` ABC 实例，统一注册到 `ToolRegistry`。

```
mcp/
├── config.py    # MCPServerConfig + load_mcp_configs (78 行)
├── client.py    # MCPClient — JSON-RPC 2.0 over stdio (214 行)
├── adapter.py   # MCPToolAdapter — Tool ABC 包装 (71 行)
└── __init__.py
```

#### 配置 (`mcp/config.py`)

```python
@dataclass(frozen=True)
class MCPServerConfig:
    name: str               # 服务器标识符
    transport: str = "stdio" # "stdio" 或 "sse"
    command: str = ""        # stdio 模式的启动命令
    args: list[str] = ()    # 命令参数
    env: dict[str, str] = {} # 额外环境变量
    url: str = ""            # SSE 模式的 URL
    enabled: bool = True
```

配置文件 `.haojun/mcp.json`:

```json
{
  "servers": [
    {
      "name": "filesystem",
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    }
  ]
}
```

#### JSON-RPC 客户端 (`mcp/client.py`)

**MCPClient** — 完整的 MCP 协议客户端，纯 asyncio 实现（无外部 MCP SDK 依赖）:

```python
class MCPClient:
    async def start() -> None     # spawn subprocess + initialize handshake
    async def stop() -> None      # graceful shutdown
    async def list_tools() -> list[MCPToolInfo]    # tools/list
    async def call_tool(name, arguments) -> str    # tools/call
```

**Initialize 握手** (`client.py:138`):

```
Client → Server: {"method": "initialize", "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "superhaojun"}}}
Server → Client: {"result": {"capabilities": {...}}}
Client → Server: {"method": "notifications/initialized"}
```

**内部架构**:

- `_write(message)` — JSON + newline 写入 subprocess stdin
- `_read_loop()` — 异步任务，持续读取 stdout，按 `id` 匹配 pending Futures
- `_pending: dict[int, asyncio.Future]` — request-id → Future 映射
- 每个请求 30s 超时，超时后清理 pending entry
- Server notification（无 id）仅 debug log，不处理
- 错误响应 → `future.set_exception(RuntimeError(...))`

**Lifecycle**:

```
MCPClient.start()
  → asyncio.create_subprocess_exec(command, *args, stdin=PIPE, stdout=PIPE)
  → asyncio.create_task(_read_loop)  # background reader
  → _initialize()                    # handshake
MCPClient.stop()
  → notifications/cancelled
  → stdin.close()
  → process.terminate() (5s timeout → kill)
  → reader_task.cancel()
```

#### Tool 适配 (`mcp/adapter.py`)

**MCPToolAdapter** — 将 MCP 服务器工具包装为本地 `Tool` ABC:

```python
class MCPToolAdapter(Tool):
    @property
    def name(self) -> str:
        return f"mcp__{self._server_name}__{self._tool_name}"  # 避免命名冲突

    @property
    def description(self) -> str:
        return f"[MCP:{self._server_name}] {self._description}"

    @property
    def risk_level(self) -> str:
        return "write"  # 外部工具默认 write 级别

    async def execute(self, **kwargs) -> str:
        return await self._client.call_tool(self._tool_name, kwargs)
```

- 工具名前缀 `mcp__{server}__{tool}` 避免与内置工具冲突
- 描述前缀 `[MCP:server_name]` 让 LLM 知道工具来源
- `risk_level` 默认 `"write"` — 外部工具保守处理
- `is_concurrent_safe` 默认 `True` — MCP 调用是独立的 RPC
- `execute()` 异常被包装为错误字符串返回（不抛出）

**注册流程**:

```python
client = MCPClient(config)
await client.start()
tools = await client.list_tools()
for tool_info in tools:
    adapter = MCPToolAdapter(client, tool_info.name, tool_info.description, tool_info.input_schema, config.name)
    registry.register(adapter)
```

适配后的 MCP 工具与内置工具（ReadFile、Bash 等）在 `ToolRegistry` 中完全一致——LLM 不感知差异，调度器统一处理并发/串行策略。

#### 对比 Claude Code

| 维度 | SuperHaojun | Claude Code |
|------|-------------|-------------|
| 代码量 | 374 行 (4 文件) | ~12,310 行 (23 文件) |
| Transport | stdio (已实现), SSE (配置预留) | stdio + SSE + StreamableHTTP + InProcess |
| 依赖 | 纯 asyncio (无 MCP SDK) | `@modelcontextprotocol/sdk` |
| 协议版本 | `2024-11-05` | 同版本 |
| 工具发现 | `tools/list` → MCPToolAdapter 注册 | 同 + 动态刷新 + elicitation handlers |
| 工具命名 | `mcp__{server}__{tool}` 前缀 | `mcp__` 类似前缀 |
| 配置 | `.haojun/mcp.json` 静态加载 | 插件驱动 + 动态配置 |
| UI | 无 | React 组件管理连接状态 |
| 错误恢复 | 超时 → kill | 自动重连 + 状态机 |

**收获**: 374 行实现了完整的 MCP 客户端协议——initialize 握手、tools/list 发现、tools/call 执行、graceful shutdown。纯 asyncio 实现无外部 SDK 依赖，JSON-RPC 逻辑清晰。MCPToolAdapter 让 MCP 工具无缝融入现有工具系统。

**差距**: CC 的 MCP 支持 4 种 transport（我们仅 stdio），有自动重连和状态机管理，有 UI 组件展示连接状态，有 elicitation handlers 自动响应用户提示。我们的配置是静态加载（启动时读取），CC 支持运行时动态增删 MCP 服务器。

---

### E3. LSP 集成 (`lsp/`, 501 行)

#### 架构概览

实现 Language Server Protocol 客户端，连接语言服务器获取代码智能能力，以被动模式注入 agent 上下文。

```
lsp/
├── client.py    # LSPClient — JSON-RPC 2.0 with Content-Length framing (337 行)
├── service.py   # LSPService — 多服务器协调 + 上下文聚合 (149 行)
└── __init__.py
```

#### LSP 客户端 (`lsp/client.py`)

**数据类型**:

```python
@dataclass(frozen=True)
class Diagnostic:      # 诊断信息（错误/警告）
    file_path: str
    line: int
    character: int
    severity: int       # 1=Error, 2=Warning, 3=Info, 4=Hint
    message: str

@dataclass(frozen=True)
class HoverInfo:       # 悬停信息（类型、文档）
    contents: str
    line: int
    character: int

@dataclass(frozen=True)
class Location:        # 代码位置（定义、引用）
    uri: str
    line: int
    character: int
```

**LSPClient** — 完整 LSP 客户端:

```python
class LSPClient:
    # Lifecycle
    async def start(workspace_root) -> None
    async def stop() -> None

    # Document sync
    async def did_open(file_path, language_id, text) -> None
    async def did_change(file_path, text, version) -> None
    async def did_close(file_path) -> None

    # Intelligence queries
    async def get_diagnostics(file_path) -> list[Diagnostic]
    async def hover(file_path, line, character) -> HoverInfo | None
    async def definition(file_path, line, character) -> list[Location]
    async def references(file_path, line, character) -> list[Location]
```

**与 MCP Client 的关键差异 — Content-Length 帧协议**:

MCP 使用 newline-delimited JSON，LSP 使用 HTTP-style Content-Length 头:

```python
def _write(self, message):
    body = json.dumps(message)
    header = f"Content-Length: {len(body.encode('utf-8'))}\r\n\r\n"
    self._process.stdin.write(header.encode() + body.encode())

async def _read_loop(self):
    while True:
        # 读取 Content-Length: N\r\n\r\n 头
        # readexactly(N) 读取 body
        data = json.loads(body)
        self._handle_message(data)
```

**被动 Diagnostics 收集**:

```python
def _handle_message(self, data):
    if data.get("method") == "textDocument/publishDiagnostics":
        self._handle_diagnostics(data.get("params", {}))
```

- 语言服务器主动推送 `textDocument/publishDiagnostics` 通知
- 客户端缓存到 `_diagnostics: dict[str, list[Diagnostic]]`
- 无需轮询，服务器变化时自动更新

**Initialize 能力声明**:

```python
"capabilities": {
    "textDocument": {
        "hover": {"contentFormat": ["markdown", "plaintext"]},
        "publishDiagnostics": {"relatedInformation": True},
        "definition": {"linkSupport": True},
        "references": {},
    }
}
```

#### LSP 服务层 (`lsp/service.py`)

**LSPService** — 多语言服务器协调:

```python
class LSPService:
    def add_server(config: LSPServerConfig) -> None     # 注册服务器配置
    async def start_all(workspace_root) -> None          # 启动所有服务器
    async def stop_all() -> None                         # 关闭所有服务器
    async def open_file(file_path, content?) -> None     # 自动路由到对应服务器
    async def get_diagnostics(file_path) -> list         # 按语言路由查询
    async def get_all_diagnostics() -> list              # 聚合所有诊断
    def to_prompt_context() -> str                       # 生成 prompt 注入文本
```

**语言检测** (`_detect_language`):

```python
ext_map = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".jsx": "javascriptreact",
    ".ts": "typescript", ".tsx": "typescriptreact",
    ".rs": "rust", ".go": "go", ...
}
```

通过文件扩展名路由到对应语言服务器。

**Prompt 上下文注入** (`to_prompt_context`):

```python
def to_prompt_context(self) -> str:
    lines = ["## LSP Context"]
    for lang_id, client in self._clients.items():
        total_diags = sum(len(d) for d in client._diagnostics.values())
        lines.append(f"- {lang_id}: {status} ({total_diags} diagnostics)")
        # Include error-level diagnostics (max 5 per file)
        for d in errors[:5]:
            lines.append(f"  ERROR {d.file_path}:{d.line+1}: {d.message}")
```

- 仅注入 error 级别诊断（severity=1），跳过 warning/info/hint
- 每个文件最多 5 条错误，防止 prompt 膨胀
- 输出格式适合直接拼入 system prompt

#### 对比 Claude Code

| 维度 | SuperHaojun | Claude Code |
|------|-------------|-------------|
| 代码量 | 501 行 (3 文件) | ~2,460 行 (7 文件) |
| 协议实现 | 纯 asyncio + Content-Length 帧 | vscode-jsonrpc 库 |
| 集成模式 | 被动（diagnostics 收集）+ 主动（hover/definition/references） | 同——被动 diagnostics + 主动 LSPTool |
| 服务器管理 | LSPService 多服务器协调 | LSPServerManager 扩展名路由 |
| 错误恢复 | 无 | 状态机 (stopped→starting→running) + 崩溃重启 (max 3) |
| 文件同步 | did_open/did_change/did_close | 同 + 文件 watcher 自动触发 |
| Prompt 注入 | `to_prompt_context()` error-only | `passiveFeedback.ts` diagnostics 去重 + 注入 |
| 语言检测 | 扩展名 dict 映射 | 同（扩展名映射） |

**收获**: 501 行实现了完整的 LSP 客户端——Content-Length 帧协议、initialize 握手、document sync、被动 diagnostics 收集、主动 hover/definition/references 查询。LSPService 聚合层让多语言服务器协调变得简单。`to_prompt_context()` 让 agent 自动感知当前文件的编译错误。

**差距**: CC 有崩溃自动重启（状态机 + max 3 restarts），我们没有。CC 用文件 watcher 自动触发 did_open/did_change，我们需要手动调用。CC 的 diagnostics 有去重逻辑，防止相同错误反复注入。

---

## Phase F: 高级能力

### F1. Multi-Agent (`agents/`, 292 行)

#### 架构概览

实现三种 multi-agent 模式：SubAgent (隔离子任务)、AgentTool (LLM 可调用的子 agent 工具)、Coordinator (并行任务分发)。

```
agents/
├── sub_agent.py   # SubAgent — 隔离执行单元 (74 行)
├── agent_tool.py  # AgentTool — Tool ABC 包装 (83 行)
├── coordinator.py # Coordinator — 并行任务分发 (122 行)
└── __init__.py
```

#### SubAgent (`agents/sub_agent.py`)

**核心设计**: SubAgent 是一个轻量级 Agent 副本，拥有独立的 MessageBus 和对话历史，共享父 agent 的 `ModelConfig` 和 `ToolRegistry`。

```python
@dataclass
class SubAgent:
    config: ModelConfig
    registry: ToolRegistry
    system_prompt: str = "You are a helpful sub-agent. Complete the assigned task concisely."
    max_turns: int = 10

    async def run(self, task: str) -> str:
        bus = MessageBus()               # 独立 bus，无 cross-talk
        agent = Agent(config=self.config, bus=bus, registry=self.registry, ...)
        # 收集 text_delta → 返回拼接结果
```

**关键隔离点**:

- **独立 MessageBus**: SubAgent 的输出不会渲染到终端（无 render handlers）
- **独立对话历史**: 不污染父 agent 的 `messages` 列表
- **共享工具和配置**: 不重复初始化 LLM client 和工具注册
- **文本收集**: 通过 `bus.on("text_delta", collector)` 收集输出，最后拼接返回

**错误处理**: `try/except Exception` 包裹整个 `handle_user_message`，错误返回为 `"SubAgent error: {exc}"`。`finally` 确保 `agent.close()` 清理资源。

#### AgentTool (`agents/agent_tool.py`)

将 SubAgent 能力暴露为一个 Tool ABC 实例，让主 agent 的 LLM 可以自主决定何时 fork 子 agent：

```python
class AgentTool(Tool):
    name = "agent"
    description = "Delegate a subtask to an independent sub-agent..."
    parameters = {"task": {"type": "string", ...}}

    async def execute(self, **kwargs) -> str:
        sub = SubAgent(config=self._config, registry=self._registry, ...)
        return await sub.run(kwargs["task"])
```

- **注册到 ToolRegistry** 后，LLM 可在对话中自主调用 `agent(task="...")`
- `is_concurrent_safe = True` — 多个 SubAgent 可并行执行
- `risk_level = "read"` — SubAgent 继承工具权限，自身不需额外授权

#### Coordinator (`agents/coordinator.py`)

**并行任务分发器**:

```python
@dataclass
class Coordinator:
    config: ModelConfig
    registry: ToolRegistry
    max_concurrent: int = 5
    max_turns_per_task: int = 10

    async def run(tasks: list[TaskSpec]) -> list[TaskResult]
    async def run_sequential(tasks: list[TaskSpec]) -> list[TaskResult]
```

**TaskSpec / TaskResult**:

```python
@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    description: str
    system_prompt: str = ""    # 可选覆盖默认 prompt

@dataclass(frozen=True)
class TaskResult:
    task_id: str
    output: str
    success: bool = True
```

**并行执行策略**:

```python
async def run(self, tasks):
    semaphore = asyncio.Semaphore(self.max_concurrent)  # 限制并发数
    async def bounded_run(spec):
        async with semaphore:
            return await self._run_one(spec)
    results = await asyncio.gather(*(bounded_run(s) for s in tasks), return_exceptions=True)
```

- `asyncio.Semaphore(max_concurrent)` 控制最大并行 SubAgent 数（默认 5）
- `return_exceptions=True` 保证单个 task 失败不影响其他
- 失败 task 返回 `TaskResult(success=False, output="Error: ...")`
- `run_sequential()` 提供有序执行模式（用于存在依赖的任务链）

#### 对比 Claude Code

| 维度 | SuperHaojun | Claude Code |
|------|-------------|-------------|
| 代码量 | 292 行 (4 文件) | ~4,524 行 (26 文件) |
| SubAgent | 独立 MessageBus + 文本收集 | 独立 context window + 结果流式传输 |
| AgentTool | Tool ABC 包装 + 单参数 task | 同——Tool 接口 + task 委托 |
| Coordinator | Semaphore 限并发 + gather | Coordinator mode + Swarm mode |
| 任务通信 | 返回最终文本 | `<task-notification>` XML + `SendMessageTool` 续传 |
| 配置 | 代码层配置 (max_concurrent, max_turns) | React 创建向导 + 多步骤 UI |
| Worker 隔离 | 同进程独立 MessageBus | 多进程隔离 |

**收获**: 292 行覆盖了 multi-agent 的三个核心模式。SubAgent 通过独立 MessageBus 实现真正的上下文隔离——子 agent 的对话不会泄露到主 agent。Coordinator 用 Semaphore 优雅地控制并发，同时支持并行和顺序两种执行模式。AgentTool 让 LLM 自主决定何时 fork，无需人工干预。

**差距**: CC 支持 Swarm mode（多个 agent 协作，Lead + Teammates），有 `SendMessageTool` 实现 agent 间续传通信。CC 的子 agent 在独立进程中运行（更强隔离），有 React UI 创建/管理 agent。我们的 SubAgent 仍在同进程内运行，任务完成后无法续传。

---

### F2. TUI (`tui/`, 320 行)

#### 架构概览

用 `prompt_toolkit` + `rich` 替换原有的 ANSI 转义码渲染，提供 Markdown 渲染、语法高亮、styled panels 和输入历史。

```
tui/
├── app.py       # TUIApp — 完整 TUI 应用 (123 行)
├── renderer.py  # TUIRenderer — MessageBus 渲染器 (182 行)
└── __init__.py
```

#### TUIRenderer (`tui/renderer.py`)

**Rich Theme** 定义:

```python
THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "dim": "dim",
    "tool": "magenta",
    "prompt": "bold cyan",
})
```

**MessageBus 渲染 Handler 注册**:

```python
def register(self, bus: MessageBus) -> None:
    bus.on("agent_start", self._on_agent_start)
    bus.on("agent_end", self._on_agent_end)
    bus.on("text_delta", self._on_text_delta)
    bus.on("tool_call_start", self._on_tool_call_start)
    bus.on("tool_call_end", self._on_tool_call_end)
    bus.on("error", self._on_error)
    bus.on("permission_request", self._on_permission_request)
```

**渲染策略**:

- **text_delta**: 累积到 `_text_buffer`，在 `agent_end` 时一次性渲染为 `rich.Markdown`
- **tool_call_start**: `Text.assemble()` 组合图标 + 工具名 + 截断参数
- **tool_call_end**: 启发式判断——如果结果像代码（含 `def`/`class`/`import` 或多行），用 `rich.Panel + Syntax` 渲染；否则用 `Text.assemble` 行内展示
- **permission_request**: `rich.Panel` 展示权限详情，`console.input()` 获取用户决策
- **error**: `[error]` 样式标记

**代码检测启发式**:

```python
def _looks_like_code(text: str) -> bool:
    indicators = ["def ", "class ", "import ", "function ", "const ", "let ", "var "]
    return any(ind in text for ind in indicators) or text.count("\n") > 3
```

**Welcome Banner**:

```python
def print_welcome(self, model_id, base_url, tool_count, cmd_count):
    self.console.print(Panel(
        Text.assemble(
            ("🤖 SuperHaojun Agent\n", "bold cyan"),
            (f"   Model: {model_id} @ {base_url}\n", ""),
            (f"   Tools: {tool_count} | Commands: {cmd_count}\n", "dim"),
            ("   Type /help for commands, /quit to exit", "dim"),
        ),
        border_style="cyan",
    ))
```

#### TUIApp (`tui/app.py`)

**完整 TUI 应用**:

```python
class TUIApp:
    def __init__(self, agent, cmd_registry, console?, history_file?):
        self.renderer = TUIRenderer(console=console)
        self.renderer.register(agent.bus)         # 渲染器挂载到 bus
        self._session = PromptSession(
            history=FileHistory(hf),              # 输入历史持久化
            auto_suggest=AutoSuggestFromHistory(), # 历史自动补全
        )

    async def run(self):
        # REPL loop: prompt_async → command dispatch / agent.handle_user_message
```

**prompt_toolkit 集成**:

- `PromptSession` — 管理输入状态
- `FileHistory` — 输入历史保存到 `~/.haojun/input_history`
- `AutoSuggestFromHistory` — 基于历史的灰色建议文本
- `prompt_async()` — 异步获取输入（不阻塞 event loop）
- HTML prompt: `<cyan><b>❯ </b></cyan>` 替代原来的 `YELLOW you> RESET`

**与 main.py 的关系**:

`TUIApp` 是 `main.py` 中 REPL loop 的 rich 替代。两者共存：
- `main.py` — 原有 ANSI 终端（零依赖，fallback）
- `tui/app.py` — rich TUI（需要 prompt_toolkit + rich）
- 通过命令行参数或配置选择使用哪个

**关键设计**: TUIRenderer 通过 `bus.on()` 注册——完全复用 MessageBus 架构。只要替换 render handlers（从 ANSI `sys.stdout.write` 到 `rich.Console.print`），整个渲染层就切换了。这验证了 Phase A 的 MessageBus 设计——UI 层是可插拔的 Handler。

#### 对比 Claude Code

| 维度 | SuperHaojun | Claude Code |
|------|-------------|-------------|
| 代码量 | 320 行 (3 文件) | ~19,842 行 (17+ 文件) |
| 渲染框架 | rich + prompt_toolkit | 自定义 Ink 重实现 (React reconciler) |
| Markdown | `rich.Markdown` | 自定义 Markdown → Ink components |
| 语法高亮 | `rich.Syntax` (Pygments) | 自定义 ANSI colorization |
| 布局引擎 | rich 内建布局 | Yoga layout engine |
| 输入 | prompt_toolkit (history + suggest) | 自定义 Kitty keyboard protocol |
| 文本选择 | 无 | 自定义 selection + copy |
| 搜索高亮 | 无 | inline search highlighting |
| IDE 集成 | 无 | VS Code extension via LSP |

**收获**: 320 行利用 rich + prompt_toolkit 两个成熟库，实现了 Markdown 渲染、语法高亮、styled panels、输入历史、auto-suggest。这是投入产出比极高的选择——两个库加起来提供了 CC 自定义 Ink 实现约 60% 的视觉效果，代码量却是 1/62。

**差距**: CC 自研了一个完整的 Ink 重实现（React reconciler + Yoga 布局 + 终端 I/O 抽象），支持文本选择、搜索高亮、Kitty 键盘协议等高级功能。这些是产品级 TUI 所需的，但对 coding agent 的核心能力不是关键路径。CC 还有 VS Code 扩展，我们没有 IDE 集成。

---

## 综合分析

### Phase E+F 的设计模式一致性

五个新模块复用了项目已建立的架构模式：

- **Frozen dataclass** 做数据载体: `HookRule`, `MCPServerConfig`, `MCPToolInfo`, `Diagnostic`, `HoverInfo`, `Location`, `TaskSpec`, `TaskResult`
- **JSON 文件配置**: `.haojun/hooks.json`, `.haojun/mcp.json`
- **ABC 适配**: `MCPToolAdapter(Tool)`, `AgentTool(Tool)` — 外部能力统一为 Tool 接口
- **asyncio 子进程**: MCP Client 和 LSP Client 共享相同的 `create_subprocess_exec` + read_loop + pending Futures 模式
- **MessageBus 可插拔**: TUIRenderer 通过 `bus.on()` 注册，与 main.py 的 ANSI handler 完全等价

### JSON-RPC 双客户端对比

MCP Client 和 LSP Client 都是 JSON-RPC 2.0 客户端，但帧协议不同：

| 维度 | MCP Client | LSP Client |
|------|-----------|-----------|
| 帧格式 | Newline-delimited JSON | Content-Length header + body |
| 写入 | `json.dumps(msg) + "\n"` | `Content-Length: N\r\n\r\n` + body |
| 读取 | `readline()` | `readline()` header → `readexactly(N)` body |
| Server 通知 | debug log only | `publishDiagnostics` 缓存到 `_diagnostics` |
| 超时 | 30s per request | 30s per request |

### 与 Claude Code 的量级对比

| 模块 | SuperHaojun | Claude Code | 比例 |
|------|-------------|-------------|------|
| Hooks | 276 行 | ~3,721 行 | 1:13 |
| MCP | 374 行 | ~12,310 行 | 1:33 |
| LSP | 501 行 | ~2,460 行 | 1:5 |
| Multi-Agent | 292 行 | ~4,524 行 | 1:15 |
| TUI | 320 行 | ~19,842 行 | 1:62 |
| **Phase E+F 合计** | **1,763 行** | **~42,857 行** | **1:24** |

### 全项目累计

| 阶段 | SuperHaojun | Claude Code (对应部分) | 比例 |
|------|-------------|----------------------|------|
| Phase A+B (消息架构 + 核心工具) | ~1,990 行 | ~15,000+ 行 | ~1:8 |
| Phase C+D (Prompt + Compact + Session + Memory) | ~1,490 行 | ~7,640+ 行 | ~1:5 |
| Phase E+F (Hooks + MCP + LSP + Agents + TUI) | ~1,763 行 | ~42,857 行 | ~1:24 |
| **全项目** | **~5,264 行** | **~65,000+ 行** | **~1:12** |

Phase E+F 的比例差距（1:24）显著大于 C+D（1:5），主要因为 CC 在 MCP（12k 行）和 TUI（20k 行）上投入了大量代码用于多 transport 支持和自研渲染引擎。这些是产品级投入，对核心 agent 能力的边际收益递减。

### 后续迭代优先级

**高价值:**
1. **Hook 生命周期扩展** — 增加 `session_start`, `session_end`, `compact` 等事件，覆盖更多扩展点
2. **MCP SSE transport** — 实现 SSE 连接，支持远程 MCP 服务器
3. **LSP 崩溃重启** — 状态机 + max retries，保证长期运行稳定性

**中等价值:**
4. **Agent 间通信** — SubAgent 返回结构化结果（而非纯文本），支持续传
5. **TUI tab 补全** — prompt_toolkit 的 `Completer` 集成命令自动补全
6. **Hook Prompt 类型** — 支持 LLM prompt 作为 hook（动态修改上下文）

**低优先级:**
7. MCP 运行时动态增删服务器
8. LSP 文件 watcher 自动同步
9. IDE 扩展 (VS Code)
