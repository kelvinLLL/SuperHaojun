# SuperHaojun Architecture: Phase E & F (v2)

> Phase E: 扩展与集成 — Hooks 系统 + MCP 集成 + LSP 集成
> Phase F: 高级能力 — Multi-Agent + TUI
>
> v2 重构：Hooks 15 事件 + 结构化结果，MCP Manager + /mcp 命令，LSP 崩溃重启 + DiagnosticRegistry，Agent 结构化结果 + LLM 规划。

---

## 度量快照

| 指标 | Phase E+F v1 | Phase E+F v2 | 增量 |
|------|-------------|-------------|------|
| 源码行数 | ~5,264 | ~6,081 | +817 |
| 模块数 | 18 | 18 | ±0 |
| 新增文件 | — | +5 (.py) | mcp/{manager,commands}, lsp/{diagnostics,managed}, agents/commands |
| E+F 合计行数 | 1,763 | 2,541 | +778 (+44%) |

### 模块行数 v1 → v2

| 模块 | v1 行数 | v2 行数 | 文件数 | 核心变化 |
|------|--------|--------|--------|---------|
| hooks/ | 276 | 423 | 3 | 14 事件 + 2 类型 + HookRegistry + AggregatedResult |
| mcp/ | 374 | 635 | 6 | MCPManager + /mcp 命令 + 多 scope 配置 |
| lsp/ | 501 | 771 | 5 | DiagnosticRegistry + ManagedLSPClient 崩溃重启 |
| agents/ | 292 | 392 | 5 | SubAgentResult + LLM 规划 + /agents 命令 |
| tui/ | 320 | 320 | 3 | 未变 |
| **合计** | **1,763** | **2,541** | **22** | |

---

## Phase E: 扩展与集成

### E1. Hooks 系统 (`hooks/`, 423 行)

#### 架构概览

v2 将 Hooks 从"pre/post 工具 shell 命令"升级为**完整的生命周期事件系统**——14 个事件点、2 种 hook 类型、结构化结果聚合、multi-source 注册表。

```
hooks/
├── config.py    # HookEvent + HookType + HookRule + HookContext + HookResult + AggregatedHookResult + HookRegistry (239 行)
├── runner.py    # HookRunner — 统一执行引擎 (172 行)
└── __init__.py  # (12 行)
```

#### 14 个生命周期事件 (`HookEvent`)

```python
class HookEvent(StrEnum):
    # Session lifecycle
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    # User interaction
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    # Tool execution
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    # Agent output
    STOP = "stop"
    STOP_FAILURE = "stop_failure"
    # Compaction
    PRE_COMPACT = "pre_compact"
    POST_COMPACT = "post_compact"
    # Sub-Agent
    SUBAGENT_START = "subagent_start"
    SUBAGENT_STOP = "subagent_stop"
    # Environment changes
    FILE_CHANGED = "file_changed"
    CWD_CHANGED = "cwd_changed"
    CONFIG_CHANGE = "config_change"
```

**Blocking 事件**: `PRE_TOOL_USE`, `USER_PROMPT_SUBMIT`, `STOP` — exit_code=2 触发阻塞/重新提示。

#### 两种 Hook 类型

| 类型 | 触发方式 | 持久化 | 用途 |
|------|---------|--------|------|
| `COMMAND` | Shell 命令 + 变量替换 | 可持久化到 hooks.json | 用户自定义 lint、审计、日志 |
| `FUNCTION` | Python async callback | 仅 session-scoped | 内部集成（LSP diagnostics、FileWatcher） |

#### HookRule — 单条钩子规则

```python
@dataclass(frozen=True)
class HookRule:
    tool_pattern: str          # glob 模式，非工具事件用 "*"
    event: HookEvent           # 14 种事件
    hook_type: HookType        # "command" 或 "function"
    command: str = ""          # shell 命令模板 (command 类型)
    callback: Callable | None  # async callable (function 类型)
    timeout: int = 10          # 最大执行秒数
    enabled: bool = True
    priority: int = 100        # 越小越先执行
```

- `tool_pattern` 使用 `fnmatch.fnmatch()` glob 匹配
- `priority` 控制同事件多规则的执行顺序

#### 结构化结果

**HookResult** — 单条 hook 执行结果:

```python
@dataclass(frozen=True)
class HookResult:
    rule: HookRule
    exit_code: int              # 0=success, 2=blocking, other=non-blocking error
    stdout: str
    stderr: str
    timed_out: bool = False
    additional_context: str = ""  # 注入到 agent 上下文的额外信息
    updated_input: dict | None    # 重写工具参数
```

Exit code 语义对齐 CC：
- `0` — 成功
- `2` — 阻塞错误（abort tool / re-prompt）
- 其他 — 非阻塞错误（logged but not fatal）

**AggregatedHookResult** — 同事件多 hook 聚合:

```python
@dataclass(frozen=True)
class AggregatedHookResult:
    results: list[HookResult]

    @property
    def blocking_errors(self) -> list[str]     # exit_code=2 的错误信息
    @property
    def additional_contexts(self) -> list[str]  # 所有额外上下文
    @property
    def updated_input(self) -> dict | None      # 最后一个非 None 的 updated_input (last-win)
    @property
    def should_block(self) -> bool              # 任一 blocking → True
    @property
    def all_passed(self) -> bool                # 全部 success → True
```

#### HookRegistry — 多源规则管理

```python
@dataclass
class HookRegistry:
    _config_rules: list[HookRule]    # 从 hooks.json 加载（持久化）
    _runtime_rules: list[HookRule]   # 运行时添加（session-scoped）

    def add_rule(rule) -> None       # 添加到 runtime
    def remove_rule(index) -> bool   # 从 runtime 移除
    def match(event, tool_name) -> list[HookRule]  # 按 event + tool_name 查找，priority 排序
    def list_hooks() -> list[HookRule]              # 全部规则
    def clear_runtime() -> None                     # 清空 runtime 规则
    def save(path) -> None                          # 持久化 config_rules (仅 command 类型)
    def load(path) -> HookRegistry                  # 从 JSON 加载，兼容 v1 格式
```

**配置兼容**: `load()` 支持 v1 格式（`timing: "pre"/"post"` → `event: PRE_TOOL_USE/POST_TOOL_USE`）。

#### 执行引擎 (`hooks/runner.py`)

**HookRunner v2** — 统一入口 `run_hooks()` 替代 v1 的 `run_pre_hooks()` / `run_post_hooks()`:

```python
@dataclass
class HookRunner:
    registry: HookRegistry
    working_dir: str = "."

    async def run_hooks(event, tool_name="", arguments=None, result="", extra=None) -> AggregatedHookResult
```

**执行流程**:

1. `registry.match(event, tool_name)` — 按事件 + 工具名查找匹配规则（已排序）
2. 构建 `HookContext(event, tool_name, arguments, result, cwd, extra)`
3. `asyncio.gather()` 并行执行所有匹配规则
4. 聚合为 `AggregatedHookResult`

**Command Hook 执行** (`_execute_command`):
- `_substitute()` — 变量替换 `$TOOL_NAME`, `$EVENT`, `$CWD`, `$RESULT`, `$ARGUMENTS`
- `asyncio.create_subprocess_shell()` 执行
- `asyncio.wait_for(timeout)` 限时
- `_parse_stdout_json()` — stdout 若是 JSON，提取 `additional_context` / `updated_input`

**Function Hook 执行** (`_execute_function`):
- `await callback(ctx)` 调用 async callable
- 返回 `dict` → 提取 exit_code, stdout, stderr, additional_context, updated_input
- 返回其他类型 → 字符串化为 stdout
- 超时和异常统一包装为 `HookResult`

#### Agent 集成点 (6 处)

| 集成点 | 位置 | 语义 |
|--------|------|------|
| `USER_PROMPT_SUBMIT` | `agent.py:106-114` | 输入前检查/重写，should_block → emit Error |
| `PRE_TOOL_USE` | `agent.py:269-280` | 工具执行前，should_block → 跳过执行，updated_input → 重写参数 |
| `POST_TOOL_USE` | `agent.py:288-293` | 工具执行后，additional_contexts → 追加到结果 |
| `STOP` | `agent.py:193-200` | Agent 完成输出后，additional_contexts → 注入 system message |
| `PRE_COMPACT` | `agent.py:207-208` | 压缩前通知 |
| `POST_COMPACT` | `agent.py:210-212` | 压缩后通知 |

#### 对比 Claude Code

| 维度 | SuperHaojun v1 | SuperHaojun v2 | Claude Code |
|------|---------------|---------------|-------------|
| 代码量 | 276 行 | 423 行 | ~3,721 行 |
| 生命周期事件 | 2 | 14 | 27 |
| Hook 类型 | 1 (command) | 2 (command + function) | 5 (command, prompt, agent, HTTP, function) |
| 结果结构 | exit_code + stdout/stderr | + additional_context + updated_input + blocking | 同 |
| 注册管理 | HookConfig 单文件 | HookRegistry 多源 + priority | Matcher 优先级链 4 层 |
| v1 兼容 | — | ✓ (timing → event 映射) | — |
| Agent 集成 | 2 处 (pre/post tool) | 6 处 | ~10 处 |

**v2 收获**: 14 个事件覆盖了 agent 的核心生命周期；function hook 类型使内部组件（LSP、FileWatcher）可以编程式集成；AggregatedHookResult 的 blocking/context/input 三语义与 CC 完全对齐；HookRegistry 的 config + runtime 分层为后续 WebUI 动态管理打好基础。

---

### E2. MCP 集成 (`mcp/`, 635 行)

#### 架构概览

v2 新增 MCPManager（统一生命周期管理）和 MCPCommand（/mcp 命令），实现运行时 enable/disable/reconnect + 多 scope 配置合并。

```
mcp/
├── config.py    # MCPServerConfig + MCPServerStatus + multi-scope loader (82 行)
├── client.py    # MCPClient — JSON-RPC 2.0 over stdio (214 行)
├── adapter.py   # MCPToolAdapter — Tool ABC 包装 (71 行)
├── manager.py   # MCPManager — 统一生命周期 (177 行)
├── commands.py  # MCPCommand — /mcp 命令 (76 行)
└── __init__.py  # (15 行)
```

#### 配置 v2 (`mcp/config.py`)

**MCPServerStatus** — 运行时状态枚举:

```python
class MCPServerStatus(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    DISABLED = "disabled"
```

**多 scope 配置合并**:

```python
def load_mcp_configs(project_path, user_path) -> list[MCPServerConfig]:
    user_configs = _load_scope(user_path, "user")
    project_configs = _load_scope(project_path, "project")
    # 按 name 合并：project 覆盖 user
    by_name = {cfg.name: cfg for cfg in user_configs}
    for cfg in project_configs:
        by_name[cfg.name] = cfg
    return list(by_name.values())
```

配置来源:
- `~/.haojun/mcp.json` — 用户级全局配置 (scope="user")
- `.haojun/mcp.json` — 项目级配置 (scope="project")
- 同名服务器：项目级覆盖用户级

#### MCPManager (`mcp/manager.py`)

**统一生命周期管理器**:

```python
@dataclass
class MCPManager:
    _servers: dict[str, MCPServerState]   # name → state
    _tool_registry: ToolRegistry | None   # 可选绑定

    # Lifecycle
    async def start_all()               # 启动所有 enabled 服务器
    async def stop_all()                # 停止所有运行中服务器

    # Runtime control
    async def enable(name) -> bool      # 启用 + 启动
    async def disable(name) -> bool     # 停止 + 禁用
    async def reconnect(name) -> bool   # 重启连接

    # Status API (for /mcp command + WebUI)
    def get_status() -> list[dict]      # 所有服务器状态
    def get_server_tools(name) -> list  # 指定服务器的工具列表
    def list_all_tools() -> list        # 所有运行中服务器的工具
```

**MCPServerState** — 每个服务器的运行时状态:

```python
@dataclass
class MCPServerState:
    config: MCPServerConfig
    status: MCPServerStatus = STOPPED
    client: MCPClient | None = None
    tools: list[MCPToolInfo]
    error: str = ""
```

**自动注册/注销工具**: `_start_server()` 成功后调用 `_register_tools()` → 为每个发现的工具创建 `MCPToolAdapter` 注册到 `ToolRegistry`。`_stop_server()` 调用 `_unregister_tools()` 清理。

**状态暴露**: `get_status()` 返回结构化状态列表 (`name, status, transport, tools_count, error, scope`)，供 `/mcp list` 命令和未来 WebUI 使用。

#### /mcp 命令 (`mcp/commands.py`)

```
/mcp list                    — 列出所有服务器状态
/mcp enable <server-name>    — 启用并启动
/mcp disable <server-name>   — 停止并禁用
/mcp reconnect <server-name> — 重启连接
/mcp tools [server-name]     — 列出工具 (全部或指定服务器)
```

#### JSON-RPC 客户端 (`mcp/client.py`, 未变)

纯 asyncio 实现，无外部 MCP SDK 依赖:
- `start()` — spawn subprocess + initialize handshake (`protocolVersion: "2024-11-05"`)
- `list_tools()` — `tools/list` RPC
- `call_tool()` — `tools/call` RPC，解析 `content[].text`
- `stop()` — `notifications/cancelled` → stdin.close → terminate(5s) → kill
- `_read_loop()` — background task，按 `id` 匹配 pending Futures，30s timeout

#### Tool 适配 (`mcp/adapter.py`, 未变)

```python
class MCPToolAdapter(Tool):
    name = f"mcp__{server_name}__{tool_name}"  # 命名空间隔离
    description = f"[MCP:{server_name}] {description}"
    risk_level = "write"          # 外部工具保守处理
    is_concurrent_safe = True     # MCP 调用是独立 RPC
```

#### 对比 Claude Code

| 维度 | SuperHaojun v1 | SuperHaojun v2 | Claude Code |
|------|---------------|---------------|-------------|
| 代码量 | 374 行 | 635 行 | ~12,310 行 |
| 生命周期管理 | 手动 start/stop | MCPManager 统一管理 | McpManager + 状态机 |
| 运行时控制 | 无 | enable/disable/reconnect | 同 + UI toggle |
| 配置来源 | 单文件 | 双 scope (user + project) | 插件 manifest + 动态配置 |
| 命令 | 无 | /mcp list\|enable\|disable\|reconnect\|tools | /mcp CLI + React UI |
| 状态暴露 | 无 | get_status() API | 同 + WebSocket 推送 |
| Transport | stdio | stdio (SSE 预留) | stdio + SSE + StreamableHTTP |

**v2 收获**: MCPManager 提供了与 CC 对等的运行时控制能力——`enable/disable/reconnect` 动态管理服务器，`get_status()` 暴露内部状态。`/mcp` 命令让用户在对话中直接管理 MCP 连接。双 scope 配置让全局工具和项目特定工具自然分层。

---

### E3. LSP 集成 (`lsp/`, 771 行)

#### 架构概览

v2 新增 DiagnosticRegistry（去重聚合）和 ManagedLSPClient（崩溃重启），提升 LSP 的可靠性和集成深度。

```
lsp/
├── client.py       # LSPClient — JSON-RPC 2.0 + Content-Length 帧 (337 行)
├── diagnostics.py  # DiagnosticRegistry — 去重聚合 (127 行)
├── managed.py      # ManagedLSPClient — 崩溃重启状态机 (137 行)
├── service.py      # LSPService — 多服务器协调 (149 行)
└── __init__.py     # (21 行)
```

#### DiagnosticRegistry (`lsp/diagnostics.py`)

**多源 diagnostic 去重聚合**:

```python
@dataclass(frozen=True)
class DiagnosticSource:
    provider: str      # "lsp:python", "hook:lint" 等
    file_path: str
    line: int
    character: int
    message: str
    severity: int      # 1=error, 2=warning, 3=info, 4=hint

    @property
    def dedup_key(self) -> tuple:
        return (self.file_path, self.line, self.message)
```

```python
@dataclass
class DiagnosticRegistry:
    _diagnostics: dict[str, list[DiagnosticSource]]  # file → diagnostics
    _seen_keys: set[tuple]                            # dedup set

    def update_file(file_path, provider, diagnostics)  # 替换 provider 的诊断
    def inject(file_path, provider, line, message, ...)  # 注入外部诊断 (hook 来源)
    def get_file(file_path) -> list                    # 查询单文件
    def get_errors(file_path?) -> list                 # 仅 error 级别
    def clear_file(file_path) -> None
    def to_prompt_context(max_errors=10) -> str         # 生成 prompt 注入文本
```

关键设计:
- **按 provider 替换**: `update_file()` 先移除该 provider 的旧数据再插入新数据，支持增量更新
- **去重**: `(file_path, line, message)` 三元组去重，避免同一问题被 LSP 和 hook 重复报告
- **外部注入**: `inject()` 允许 hook 产出的 lint 结果进入同一注册表，统一管理
- **prompt 注入**: `to_prompt_context()` 仅输出 error 级别，max 10 条，防止 prompt 膨胀

#### ManagedLSPClient (`lsp/managed.py`)

**崩溃重启状态机**:

```
stopped → starting → running ──→ crashed
                        ↑          │
                        └── starting ←┘ (max 3 次，指数退避)
```

```python
class LSPState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    CRASHED = "crashed"

@dataclass
class ManagedLSPClient:
    command: str
    args: list[str]
    max_restarts: int = 3

    async def start(workspace_root) -> None
    async def stop() -> None
    # 代理所有 LSPClient 方法，自动崩溃恢复
    async def did_open(...) / did_change(...) / did_close(...)
    async def get_diagnostics(...) / hover(...) / definition(...)
```

**`_with_recovery()` 模式**:

```python
async def _with_recovery(self, fn):
    if self._state != RUNNING:
        return None
    try:
        return await fn(self._client)
    except Exception:
        self._state = CRASHED
        await self._try_restart()
        return None
```

- 所有 LSP 操作都经过 `_with_recovery()` 包装
- 操作失败 → 状态切换为 CRASHED → 尝试重启
- 重启使用指数退避: `2^n` 秒 (1s, 2s, 4s)
- 最多 3 次重启，超出后保持 CRASHED 状态

#### LSP Client (`lsp/client.py`, 未变)

Content-Length 帧协议实现:
- `_write()` — `Content-Length: N\r\n\r\n` + JSON body
- `_read_loop()` — readline headers → readexactly(N) body
- `_handle_diagnostics()` — 缓存 `textDocument/publishDiagnostics` 推送
- 支持: did_open/did_change/did_close, hover, definition, references

#### LSP Service (`lsp/service.py`, 未变)

多语言服务器协调层:
- `_detect_language()` — 扩展名 → language_id 映射
- `to_prompt_context()` — 聚合所有服务器的 error diagnostics 注入 prompt
- 每文件最多 5 条 error

#### 对比 Claude Code

| 维度 | SuperHaojun v1 | SuperHaojun v2 | Claude Code |
|------|---------------|---------------|-------------|
| 代码量 | 501 行 | 771 行 | ~2,460 行 |
| Diagnostics 管理 | 内存 dict 缓存 | DiagnosticRegistry 去重 + provider 追踪 | passiveFeedback.ts 去重注入 |
| 崩溃恢复 | 无 | ManagedLSPClient 状态机 (max 3, 指数退避) | 同——状态机 + max restarts |
| 外部诊断注入 | 无 | `inject()` 支持 hook 来源 | — |
| 文件同步 | 手动 did_open/did_change | 同 (FileWatcher 待集成) | chokidar watcher 自动触发 |

**v2 收获**: DiagnosticRegistry 的 dedup + provider 追踪解决了"同一错误被重复报告"的问题；ManagedLSPClient 的状态机 + 指数退避保证了长时间运行的稳定性——LSP 服务器崩溃不会导致 agent 丧失代码智能能力。

---

## Phase F: 高级能力

### F1. Multi-Agent (`agents/`, 392 行)

#### 架构概览

v2 将 SubAgent 的返回值从纯文本升级为**结构化 SubAgentResult**，新增 LLM 自动任务规划、进度回调、token 限制，以及 `/agents` 命令。

```
agents/
├── sub_agent.py   # SubAgent — 结构化结果 + 进度回调 (95 行)
├── agent_tool.py  # AgentTool — Tool ABC 包装 (86 行)
├── coordinator.py # Coordinator — 并行分发 + LLM 规划 (149 行)
├── commands.py    # AgentsCommand — /agents 命令 (45 行)
└── __init__.py    # (17 行)
```

#### SubAgentResult — 结构化结果

v1 返回纯文本，v2 返回:

```python
@dataclass(frozen=True)
class SubAgentResult:
    output: str              # 收集的全部文本输出
    tool_calls_made: int = 0 # 使用了多少次工具
    turns_used: int = 0      # 对话轮次
    tokens_used: int = 0     # token 消耗
    success: bool = True     # 是否成功完成
    error: str = ""          # 错误信息 (失败时)
```

#### SubAgent v2

```python
@dataclass
class SubAgent:
    config: ModelConfig
    registry: ToolRegistry
    system_prompt: str
    max_turns: int = 10
    max_tokens: int = 0            # 0=unlimited
    on_progress: Callable | None   # 实时进度回调
    inherit_permissions: bool      # 是否继承父 agent 的权限

    async def run(task) -> SubAgentResult
```

新增能力:
- **on_progress**: 每次 `text_delta` 触发回调，父级可实时显示子 agent 进度
- **max_tokens**: 防止 runaway 子 agent 消耗过多 token
- **inherit_permissions**: 是否继承父 agent 的 PermissionChecker

**隔离机制**（未变）:
- 独立 `MessageBus` — 子 agent 输出不渲染到终端
- 独立 `messages` 列表 — 不污染父 agent 对话历史
- 共享 `ModelConfig` + `ToolRegistry` — 不重复初始化

#### Coordinator v2 + LLM 规划

```python
@dataclass
class Coordinator:
    async def run(tasks: list[TaskSpec]) -> list[TaskResult]             # 手动任务列表
    async def run_sequential(tasks: list[TaskSpec]) -> list[TaskResult]  # 有序执行
    async def run_with_llm_planning(goal: str) -> list[TaskResult]       # 新增: LLM 自动分解
```

**`run_with_llm_planning()`** 工作流:

1. 构建 planning prompt: "Break down the goal into 2-5 independent subtasks, return JSON"
2. LLM 返回 `[{"task_id": "t1", "description": "..."}, ...]`
3. 解析 JSON（支持 markdown code block 包裹）
4. 调用 `run()` 并行执行所有 subtask

**TaskResult v2**:

```python
@dataclass(frozen=True)
class TaskResult:
    task_id: str
    output: str
    success: bool = True
    tool_calls_made: int = 0
    turns_used: int = 0

    @classmethod
    def from_sub_result(cls, task_id, sub: SubAgentResult) -> TaskResult
```

#### /agents 命令 (`agents/commands.py`)

```
/agents list           — 显示 Coordinator 配置 (max_concurrent, max_turns)
/agents run <goal>     — LLM 自动分解目标 + 并行执行 + 汇报结果
```

#### 对比 Claude Code

| 维度 | SuperHaojun v1 | SuperHaojun v2 | Claude Code |
|------|---------------|---------------|-------------|
| 代码量 | 292 行 | 392 行 | ~4,524 行 |
| SubAgent 返回 | 纯文本 | SubAgentResult (output, tools, turns, tokens, success, error) | 结构化 + 流式传输 |
| 进度回调 | 无 | on_progress callback | SendMessageTool 续传 |
| 任务规划 | 手动 TaskSpec 列表 | + run_with_llm_planning() 自动分解 | Coordinator + Swarm 模式 |
| 命令 | 无 | /agents list\|run | React 创建向导 |
| Token 控制 | 无 | max_tokens 限制 | 同 |

**v2 收获**: SubAgentResult 让父级可以做数据驱动的决策（如"tools 调用超过 N 次就切换策略"），而非只能解析文本。`run_with_llm_planning()` 实现了 CC 的 Coordinator 模式——用户只需说"分析这个项目的测试覆盖率"，系统自动分解为多个子任务并行执行。

---

### F2. TUI (`tui/`, 320 行, 未变)

prompt_toolkit + rich 的终端应用，v2 未修改。

- **TUIRenderer**: MessageBus 渲染 handler，text_delta 累积 → agent_end 时 Markdown 渲染
- **TUIApp**: PromptSession + FileHistory + AutoSuggestFromHistory，async REPL loop

详细文档见 v1 architecture-EF.md。

---

## 综合分析

### v1 → v2 核心模式升级

| 模式 | v1 | v2 |
|------|----|----|
| 事件系统 | 2 事件 (pre/post tool) | 14 事件 (全生命周期) |
| 结果类型 | 扁平 (exit_code + stdout) | 结构化 (HookResult/SubAgentResult) |
| 管理能力 | 静态配置 | 运行时 enable/disable + 状态暴露 |
| 可靠性 | 无恢复 | 崩溃重启 + 状态机 |
| 命令支持 | 无 | /mcp + /agents 命令 |

### 与 Claude Code 的量级对比

| 模块 | SuperHaojun v2 | Claude Code | 比例 |
|------|---------------|-------------|------|
| Hooks | 423 行 | ~3,721 行 | 1:9 |
| MCP | 635 行 | ~12,310 行 | 1:19 |
| LSP | 771 行 | ~2,460 行 | 1:3 |
| Multi-Agent | 392 行 | ~4,524 行 | 1:12 |
| TUI | 320 行 | ~19,842 行 | 1:62 |
| **Phase E+F 合计** | **2,541 行** | **~42,857 行** | **1:17** |

### 全项目累计

| 阶段 | SuperHaojun | Claude Code (对应部分) | 比例 |
|------|-------------|----------------------|------|
| Phase A+B | ~1,990 行 | ~15,000+ 行 | ~1:8 |
| Phase C+D v2 | ~1,490 行 | ~7,640+ 行 | ~1:5 |
| Phase E+F v2 | ~2,541 行 | ~42,857 行 | ~1:17 |
| **全项目** | **~6,081 行** | **~65,000+ 行** | **~1:11** |

v2 重构将 E+F 比例从 1:24 改善到 1:17（+44% 代码量），主要收益来自:
- Hooks: 1:13 → 1:9（事件数和结构化结果大幅靠近 CC）
- MCP: 1:33 → 1:19（MCPManager + 命令 + 多 scope）
- LSP: 1:5 → 1:3（最接近 CC 的模块，崩溃重启 + 去重已覆盖核心能力）
