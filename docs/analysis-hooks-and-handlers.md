# 分析：Hooks 与 Handler 运行时架构

> 深度分析 Claude Code 的 Hook 系统、Handler 系统及其运行时集成，
> 对比 SuperHaojun 当前实现的差距，并设计重构方案。

---

## 一、Claude Code 的 Hook 系统全貌

### 1.1 生命周期事件（27 个）

CC 的 hook 系统定义了 27 个生命周期事件（`HOOK_EVENTS`），覆盖了从 session 启动到退出的全链路：

| 分类 | 事件 | 语义 | 阻塞性 |
|------|------|------|--------|
| **Session 生命周期** | `SessionStart` | session 启动/恢复/清空/compact 后 | fire-and-forget |
| | `SessionEnd` | session 结束，清理阶段 | fire-and-forget |
| | `Setup` | 仓库初始化/维护 | fire-and-forget |
| **工具执行** | `PreToolUse` | 工具执行前 | **blocking** (exit=2 阻止) |
| | `PostToolUse` | 工具执行后 | fire-and-forget |
| | `PostToolUseFailure` | 工具执行失败后 | fire-and-forget |
| **用户交互** | `UserPromptSubmit` | 用户提交 prompt | **blocking** |
| | `PermissionRequest` | 权限对话框弹出 | **blocking** |
| | `PermissionDenied` | auto-mode 分类器拒绝工具调用 | fire-and-forget |
| **Agent 输出** | `Stop` | assistant 回复完成，返回用户前 | **blocking** (可 re-prompt) |
| | `StopFailure` | API 错误导致 turn 结束 | fire-and-forget |
| **Sub-Agent** | `SubagentStart` | 子 agent 启动 | fire-and-forget |
| | `SubagentStop` | 子 agent 完成 | fire-and-forget |
| **Compaction** | `PreCompact` | 压缩前 | fire-and-forget |
| | `PostCompact` | 压缩后 | fire-and-forget |
| **任务管理** | `TaskCreated` | 任务创建 | fire-and-forget |
| | `TaskCompleted` | 任务完成 | fire-and-forget |
| **MCP** | `Elicitation` | MCP 服务器请求用户输入 | fire-and-forget |
| | `ElicitationResult` | 用户响应 MCP elicitation | fire-and-forget |
| **环境变化** | `FileChanged` | 监控的文件变化（chokidar watcher） | fire-and-forget |
| | `CwdChanged` | 工作目录变化 | fire-and-forget |
| | `ConfigChange` | 配置文件变化 | fire-and-forget |
| | `WorktreeCreate` | git worktree 创建 | fire-and-forget |
| | `WorktreeRemove` | git worktree 删除 | fire-and-forget |
| **观测性** | `InstructionsLoaded` | 指令文件加载（只读） | fire-and-forget |
| | `Notification` | 通知发送 | fire-and-forget |
| | `TeammateIdle` | 团队成员即将 idle | fire-and-forget |

**关键设计原则：只有 4 个事件是 blocking 的**（`PreToolUse`, `UserPromptSubmit`, `PermissionRequest`, `Stop`），其余全部 fire-and-forget。这保证了系统的响应性——hook 不会成为瓶颈。

### 1.2 Hook 类型（5 种执行器）

CC 支持 5 种 hook 类型，每种有不同的执行语义：

| 类型 | 执行方式 | 输入 | 输出 | 特殊能力 |
|------|---------|------|------|---------|
| **Command** | shell 子进程 | JSON via stdin | exit code + stdout | **可异步后台**（`{"async": true}`） |
| **Prompt** | 单次 LLM 推理 | hook prompt + context JSON | `{ok: bool, reason?: str}` | 用 LLM 做验证判断 |
| **Agent** | 子 agent 多轮对话 | 同 Command | 结构化决策 | 多轮推理后做决策 |
| **HTTP** | POST 请求 | JSON body | JSON response | 外部 webhook 集成 |
| **Function** | 内存 TypeScript 回调 | `(messages, signal) => bool` | boolean | **直接访问对话历史**，session-only |

**Command Hook 的异步模式** 是独特设计：hook 可以在第一行输出 `{"async": true}` 声明自己是后台任务，主循环不等待其完成。这通过 `AsyncHookRegistry` 管理——全局注册表追踪后台 hook，主循环轮询 `checkForAsyncHookResponses()`。

### 1.3 配置来源与优先级

CC 的 hook 配置从 4 个来源合并，有严格的优先级：

```
┌─ Policy Settings (管理员) ────────── priority 0 (最高)
│  └─ 可完全禁用所有 hook 或仅允许 managed hook
├─ Local Settings (.claude/settings.local.json) ─ priority 0
├─ Project Settings (.claude/settings.json) ─── priority 1
├─ User Settings (~/.claude/settings.json) ──── priority 2
├─ Plugin Hooks (runtime 注册) ─────────────── priority 999
└─ Built-in Hooks ─────────────────────────── priority 999 (最低)
```

**额外来源**:
- **Frontmatter Hooks**: `.claude/agents/*.md` 和 `.claude/skills/*.md` 的 YAML frontmatter 中定义的 hook，通过 `registerFrontmatterHooks()` 转换为 session hook
- **Session Hooks**: 运行时通过 `addSessionHook()` / `addFunctionHook()` 动态注入，scoped to session ID

**Policy 控制**:
- `disableAllHooks: true` → 禁用所有 hook
- `allowManagedHooksOnly: true` → 仅运行 SDK/plugin hook，阻止用户自定义 hook
- `strictPluginOnlyCustomization: true` → 阻止自定义 agent 的 frontmatter hook

---

## 二、Handler 与 Hook 的架构关系

这是理解 CC 运行时的关键：**Handler 和 Hook 是不同层次的抽象，它们通过事件驱动连接**。

### 2.1 Handler = 消息路由层

CC 中 "Handler" 出现在两个场景：

**场景 1：Bridge 消息 Handler**（`bridgeMessaging.ts:132`）

```
WebSocket/SSE/CCR 消息进入
  → handleIngressMessage(data, dedup, ...)
    → 解析 JSON → UUID 去重
    → 路由到 onInboundMessage()      ← 用户/助手消息
    → 路由到 onPermissionResponse()   ← 权限对话框响应
    → 路由到 onControlRequest()       ← 控制请求 (initialize, set_model, can_use_tool)
```

这是 **Transport 层的消息分发**——对应 SuperHaojun 的 `MessageBus.emit()` + `bus.on()` handler。

**场景 2：LSP 通知 Handler**（`passiveFeedback.ts:125`）

```
LSP Server 推送 textDocument/publishDiagnostics
  → registerLSPNotificationHandlers(manager)
    → manager.onNotification("textDocument/publishDiagnostics", callback)
    → callback 将 diagnostics 存入诊断追踪系统
```

这是 **外部协议的事件监听**——对应 SuperHaojun 的 `LSPClient._handle_diagnostics()`。

### 2.2 Hook = 可扩展的行为注入层

Hook 不是 handler——它是**在 handler 处理完消息后、在特定业务节点上触发的可扩展行为**。

```
[External Event] ──→ [Handler 路由消息] ──→ [业务逻辑更新状态] ──→ [Hook 执行点]
```

### 2.3 关键连接：Handler 触发业务逻辑，业务逻辑触发 Hook

```
┌──────────────────────────────────────────────────────────┐
│                    CC 运行时分层                          │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Transport Layer (Handler)                               │
│  ├─ Bridge: handleIngressMessage()                       │
│  ├─ LSP: registerLSPNotificationHandlers()               │
│  └─ MCP: client.on("notification", ...)                  │
│       │                                                  │
│       ▼                                                  │
│  Business Logic (Query Loop + Tool Execution)            │
│  ├─ query.ts: agent 主循环                               │
│  ├─ toolExecution.ts: 工具调度                            │
│  ├─ compact.ts: 上下文压缩                               │
│  └─ sessionStart.ts: session 生命周期                     │
│       │                                                  │
│       ▼                                                  │
│  Hook Layer (Extensible Behavior Injection)              │
│  ├─ toolHooks.ts: PreToolUse / PostToolUse               │
│  ├─ stopHooks.ts: Stop / StopFailure                     │
│  ├─ sessionStart.ts: SessionStart / Setup                │
│  ├─ fileChangedWatcher.ts: FileChanged / CwdChanged      │
│  └─ hooks.ts: executeHooks() — 统一执行引擎              │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

**所以 LSP 被动触发的链路是**：

```
LSP Server 推送 diagnostics
  → Handler: LSPClient._handle_diagnostics() 缓存到 _diagnostics dict
  → Prompt 注入: LSPService.to_prompt_context() 在下一轮 build prompt 时读取
  → Agent 自然感知错误信息，自行决定是否修复

（注意：LSP diagnostics 不直接触发 hook。它走的是 "被动注入 prompt → LLM 感知" 路径。）
```

**而文件变化的自动触发链路是**：

```
chokidar 文件 watcher 检测到 change/add/unlink
  → fileChangedWatcher.ts: handleFileEvent(path, event)
  → executeFileChangedHooks(path, event)  ← fire-and-forget
  → Hook 可输出 watchPaths 动态更新监控列表
  → Hook 可输出 systemMessages 注入到对话 transcript
  → 通过 notifyCallback 传递给主循环
```

### 2.4 两条自动触发路径的本质区别

| | LSP Diagnostics | FileChanged Hooks |
|---|---|---|
| **触发源** | 语言服务器主动推送 | chokidar 文件系统事件 |
| **触发机制** | Handler 缓存 → prompt 注入 → LLM 读取 | Hook 执行 → 结果注入 transcript |
| **时机** | 下一轮 LLM 调用时才生效 | 立即执行 hook，结果异步注入 |
| **自动性** | 完全自动（只要 LSP server 推送） | 需要配置 FileChanged hook + 监控路径 |
| **阻塞性** | 非阻塞（被动） | 非阻塞（fire-and-forget） |

---

## 三、CC Hook 执行引擎详解

### 3.1 核心执行函数

CC 的 hook 执行引擎是一个 **AsyncGenerator**（`hooks.ts:1952`）：

```typescript
async function* executeHooks({
  hookInput, toolUseID, matchQuery?, signal?, timeoutMs?,
  toolUseContext?, messages?, forceSyncExecution?, requestPrompt?,
}): AsyncGenerator<AggregatedHookResult>
```

使用 AsyncGenerator 而非简单 Promise 的原因：
- 可以在 hook 执行过程中 **yield 进度消息**（UX 反馈）
- 支持 **增量聚合结果**（多个 hook 并行，逐个完成时更新）
- 支持 **AbortSignal** 优雅取消
- 主循环可以 `for await` 渐进式处理

### 3.2 执行流程

```
executeHooks(hookInput)
  │
  ├─ [1] Trust Check: shouldSkipHookDueToTrust()
  │      → 工作区未信任 → 跳过所有 hook
  │
  ├─ [2] Match: getMatchingHooks(appState, sessionId, hookEvent, hookInput)
  │      → 从 4 个来源合并：snapshot + registered + session + function
  │      → sortMatchersByPriority() 按优先级排序
  │
  ├─ [3] Yield Progress: 为每个匹配 hook 发出进度消息
  │
  ├─ [4] Parallel Execution: 所有匹配 hook 并行执行
  │      ├─ Command → create_subprocess + stdin JSON + 读取 stdout
  │      ├─ Prompt  → 单次 LLM 调用 + Zod 验证输出
  │      ├─ Agent   → 启动子 agent + 多轮对话 + 提取决策
  │      ├─ HTTP    → POST 请求 + JSON 解析
  │      └─ Function → 直接调用 callback(messages, signal)
  │
  ├─ [5] Result Processing: processHookJSONOutput()
  │      ├─ 解析 JSON 或视为 plaintext
  │      ├─ 验证 hookJSONOutputSchema
  │      ├─ 提取 hookSpecificOutput
  │      └─ 应用 exit code 语义
  │
  └─ [6] Aggregation → AggregatedHookResult
         ├─ blockingErrors? → blocking error 数组
         ├─ additionalContexts? → 拼接
         ├─ permissionBehavior? → allow > ask > deny (保守合并)
         ├─ updatedInput? → 最后一个生效
         └─ watchPaths? → 拼接（用于 FileChanged watcher）
```

### 3.3 Exit Code 语义

| Exit Code | 含义 | 行为 |
|-----------|------|------|
| `0` | 成功 | 输出显示在 transcript，不阻塞 |
| `2` | 阻塞错误 | 显示给 model，**阻止后续操作** |
| 其他 | 非阻塞错误 | 显示给用户，工具调用继续 |
| 超时 | 自动非阻塞错误 | 同"其他" |

### 3.4 Hook 在 Agent Loop 中的注入点

```
┌─────────────────────────────────────────────────────────┐
│                Agent Loop (query.ts)                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─ SessionStart ─────────────────────┐                 │
│  │  → executeSessionStartHooks()      │                 │
│  │  → 注入 additionalContexts         │                 │
│  │  → 设置 FileChanged watcher        │                 │
│  └────────────────────────────────────┘                 │
│                                                         │
│  ┌─ UserPromptSubmit ─────────────────┐                 │
│  │  → hook 可修改/阻止用户输入        │                  │
│  └────────────────────────────────────┘                 │
│                                                         │
│  while (tool_loop):                                     │
│    LLM 调用 → 流式接收                                   │
│    if tool_calls:                                       │
│      for each tool_call:                                │
│        ┌─ PreToolUse ─────────────────┐                 │
│        │  → exit=2 阻止执行            │                 │
│        │  → permissionBehavior 修改    │                 │
│        │  → updatedInput 修改参数      │                 │
│        └──────────────────────────────┘                 │
│        tool.execute()                                   │
│        ┌─ PostToolUse ────────────────┐                 │
│        │  → additionalContexts 注入   │                 │
│        │  → 可修改 MCP tool 输出       │                 │
│        └──────────────────────────────┘                 │
│    else: break                                          │
│                                                         │
│  ┌─ Stop ─────────────────────────────┐                 │
│  │  → exit=2 → re-prompt model       │                  │
│  │  → preventContinuation → 终止      │                 │
│  └────────────────────────────────────┘                 │
│                                                         │
│  ┌─ PreCompact / PostCompact ─────────┐                 │
│  │  → 压缩前后通知                     │                 │
│  └────────────────────────────────────┘                 │
│                                                         │
│  ┌─ SessionEnd ───────────────────────┐                 │
│  │  → clearSessionHooks(sessionId)    │                 │
│  │  → 资源清理                         │                 │
│  └────────────────────────────────────┘                 │
│                                                         │
│  ═══════════ 并行运行 ═══════════════                    │
│  FileChanged watcher (chokidar)                         │
│  → 文件变化 → executeFileChangedHooks() → 异步注入       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 四、SuperHaojun 当前实现差距分析

### 4.1 当前实现概览

```python
# hooks/config.py
class HookRule:
    tool_pattern: str     # glob 匹配
    timing: HookTiming    # "pre" | "post"
    command: str           # shell 模板
    timeout: int = 10

class HookConfig:
    rules: list[HookRule]
    def get_rules(tool_name, timing) -> list[HookRule]
    def load(path) / save(path)        # JSON 持久化

# hooks/runner.py
class HookRunner:
    async def run_pre_hooks(tool_name, arguments) -> list[HookResult]
    async def run_post_hooks(tool_name, arguments, result) -> list[HookResult]
    def all_passed(results) -> bool

# agent.py:240-257 — 集成点
if self.hook_runner:
    pre_results = await self.hook_runner.run_pre_hooks(tc.name, kwargs)
    if not self.hook_runner.all_passed(pre_results):
        return "Blocked by pre-hook"
# ... tool.execute() ...
if self.hook_runner:
    await self.hook_runner.run_post_hooks(tc.name, kwargs, result=result)
```

### 4.2 逐项差距对照

| 维度 | SuperHaojun 当前 | Claude Code | 差距级别 |
|------|-----------------|-------------|---------|
| 生命周期事件 | 2 (pre/post tool) | 27 | **严重** |
| Hook 类型 | 1 (shell command) | 5 (command/prompt/agent/http/function) | **严重** |
| 配置来源 | 1 (JSON 文件) | 4+ (settings + frontmatter + runtime + plugin) | 中等 |
| 优先级系统 | 无 | 4 级优先级链 | 中等 |
| 执行模式 | 同步等待 | AsyncGenerator + 进度 yield | 中等 |
| exit code 语义 | 0=pass, 非 0=fail | 0=success, 2=blocking, other=non-blocking | 中等 |
| 异步 hook | 不支持 | Command hook 可后台运行 | 低 |
| 文件监控 | 无 | chokidar watcher + FileChanged 事件 | **严重** |
| Session 隔离 | 无 | Map\<sessionId, SessionStore> | 低 |
| Policy 控制 | 无 | disableAllHooks / managedOnly | 低 |
| 与 MessageBus 集成 | HookRunner 独立于 bus | Hook 结果可注入 transcript（via bus） | 中等 |
| Hook 修改能力 | 只能 pass/fail | 可修改工具参数（updatedInput）、修改权限（permissionBehavior） | **严重** |

### 4.3 最关键的 3 个差距

1. **生命周期覆盖不足**：只有 `PreToolUse`/`PostToolUse`，缺少 `SessionStart`、`Stop`、`UserPromptSubmit`、`PreCompact`、`FileChanged` 等关键事件。用户无法在 session 启动时注入上下文、在 LLM 输出后做验证、在文件变化时触发动作。

2. **Hook 只能 pass/fail，不能修改行为**：CC 的 hook 可以返回 `updatedInput`（修改工具参数）、`additionalContexts`（注入额外上下文给 LLM）、`permissionBehavior`（修改权限决策）。我们的 hook 只有 "通过/阻止" 二元判断。

3. **无文件变化监控**：CC 通过 chokidar watcher + FileChanged hook 实现文件变化自动触发，是 CC 对代码库变动自动响应的核心机制。我们完全缺失这个能力。

---

## 五、重构方案

### 5.1 目标架构

```
┌─────────────────────────────────────────────────────────────┐
│                  SuperHaojun Hook Runtime v2                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─ HookEvent Enum ──────────────────────────┐              │
│  │  SessionStart, SessionEnd,                │              │
│  │  UserPromptSubmit,                        │              │
│  │  PreToolUse, PostToolUse,                 │              │
│  │  Stop, StopFailure,                       │              │
│  │  PreCompact, PostCompact,                 │              │
│  │  SubagentStart, SubagentStop,             │              │
│  │  FileChanged, CwdChanged,                 │              │
│  │  ConfigChange                             │              │
│  └───────────────────────────────────────────┘              │
│                                                             │
│  ┌─ HookExecutor (type dispatch) ────────────┐              │
│  │  CommandExecutor → shell subprocess       │              │
│  │  FunctionExecutor → Python callback       │              │
│  │  (Prompt/HTTP 后续可选加入)                │              │
│  └───────────────────────────────────────────┘              │
│                                                             │
│  ┌─ HookRegistry ────────────────────────────┐              │
│  │  Config hooks (JSON file)                 │              │
│  │  Runtime hooks (addHook() API)            │              │
│  │  Function hooks (Python callbacks)        │              │
│  │  → match(event, context) → list[Hook]     │              │
│  │  → priority sorting                       │              │
│  └───────────────────────────────────────────┘              │
│                                                             │
│  ┌─ HookRunner v2 ──────────────────────────┐               │
│  │  async execute(event, context) → HookResult              │
│  │  → 并行执行所有匹配 hook                  │               │
│  │  → exit code 语义 (0/2/other)            │               │
│  │  → 结果聚合: blocking_errors,            │               │
│  │    additional_contexts, updated_input     │               │
│  └───────────────────────────────────────────┘              │
│                                                             │
│  ┌─ FileWatcher ─────────────────────────────┐              │
│  │  watchdog / polling 文件监控              │               │
│  │  → FileChanged 事件 → hook 执行           │              │
│  │  → 动态更新监控路径                        │              │
│  └───────────────────────────────────────────┘              │
│                                                             │
│  ┌─ MessageBus 集成 ─────────────────────────┐              │
│  │  Hook 结果可 emit 到 bus                   │              │
│  │  → additional_contexts 注入 transcript    │              │
│  │  → blocking_error 通知 agent              │              │
│  └───────────────────────────────────────────┘              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 HookEvent — 扩展生命周期

```python
class HookEvent(StrEnum):
    # Session 生命周期
    SESSION_START = "session_start"
    SESSION_END = "session_end"

    # 用户交互
    USER_PROMPT_SUBMIT = "user_prompt_submit"

    # 工具执行（已有，保留）
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"

    # Agent 输出
    STOP = "stop"                    # assistant 回复完成前
    STOP_FAILURE = "stop_failure"    # API 错误导致 turn 结束

    # Compaction
    PRE_COMPACT = "pre_compact"
    POST_COMPACT = "post_compact"

    # Sub-Agent
    SUBAGENT_START = "subagent_start"
    SUBAGENT_STOP = "subagent_stop"

    # 环境变化
    FILE_CHANGED = "file_changed"
    CWD_CHANGED = "cwd_changed"
    CONFIG_CHANGE = "config_change"
```

首期实现 15 个事件（CC 的 27 个中去掉 MCP elicitation、teammate、worktree、notification、instructions_loaded、permission 相关——这些依赖我们暂未需要的功能）。

### 5.3 HookType — 支持 Command + Function

```python
class HookType(StrEnum):
    COMMAND = "command"      # shell 子进程（已有，增强）
    FUNCTION = "function"    # Python 回调（新增，session-only）
    # PROMPT = "prompt"      # 后续可选：用 LLM 做 hook 判断
    # HTTP = "http"          # 后续可选：webhook 回调
```

首期只实现 Command + Function 两种。Command 是用户配置的 shell 脚本，Function 是运行时注册的 Python 回调（用于内部组件如 LSP 被动诊断注入）。

### 5.4 HookResult — 从二元到结构化

```python
@dataclass(frozen=True)
class HookResult:
    hook: HookRule
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    # 新增：结构化输出（从 stdout JSON 解析）
    additional_context: str = ""     # 注入给 LLM 的额外上下文
    updated_input: dict | None = None  # 修改后的工具参数
    blocking: bool = False           # exit_code == 2

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@dataclass(frozen=True)
class AggregatedHookResult:
    """聚合多个 hook 的结果。"""
    results: list[HookResult]
    blocking_errors: list[str]           # 所有 blocking error 消息
    additional_contexts: list[str]       # 拼接后注入 transcript
    updated_input: dict | None = None    # 最后一个 updatedInput 生效

    @property
    def should_block(self) -> bool:
        return len(self.blocking_errors) > 0
```

**Exit code 语义对齐 CC**:
- `0` → success
- `2` → blocking error（阻止工具执行 / 重新 prompt model）
- 其他 → non-blocking error（记录但不阻止）

**stdout JSON 解析**: 如果 hook 的 stdout 是合法 JSON 且包含 `additional_context` / `updated_input` 字段，则提取为结构化结果。否则视为纯文本。

### 5.5 HookRegistry — 多来源统一注册

```python
@dataclass
class HookRegistry:
    """统一管理所有 hook 来源。"""
    _config_hooks: list[HookRule] = field(default_factory=list)       # 从 JSON 文件加载
    _runtime_hooks: list[HookRule] = field(default_factory=list)      # addHook() 动态注册
    _function_hooks: list[FunctionHook] = field(default_factory=list) # Python 回调

    def load_config(self, path: Path) -> None: ...
    def add_hook(self, rule: HookRule) -> None: ...
    def add_function_hook(self, event: HookEvent, callback, priority=0) -> None: ...
    def clear_runtime_hooks(self) -> None: ...

    def match(self, event: HookEvent, context: HookContext) -> list[MatchedHook]:
        """查询所有匹配的 hook，按优先级排序。"""
        # 合并 config + runtime + function hooks
        # 按 priority 排序
```

### 5.6 Agent Loop 集成点扩展

```python
# agent.py — 新增 hook 集成点

async def handle_user_message(self, user_input: str) -> None:
    # ── USER_PROMPT_SUBMIT hook ──
    hook_result = await self.hook_registry.execute(
        HookEvent.USER_PROMPT_SUBMIT,
        HookContext(user_input=user_input),
    )
    if hook_result.should_block:
        await self.bus.emit(Error(message="Blocked by hook"))
        return
    if hook_result.updated_input:
        user_input = hook_result.updated_input.get("text", user_input)

    self.messages.append(ChatMessage(role="user", content=user_input))
    await self.bus.emit(AgentStart())

    while True:
        # ... LLM 调用 + tool loop ...

        # ── PRE_TOOL_USE hook (已有，增强) ──
        hook_result = await self.hook_registry.execute(
            HookEvent.PRE_TOOL_USE,
            HookContext(tool_name=tc.name, arguments=kwargs),
        )
        if hook_result.should_block:
            return f"Blocked: {hook_result.blocking_errors[0]}"
        if hook_result.updated_input:
            kwargs = hook_result.updated_input  # hook 可修改工具参数
        if hook_result.additional_contexts:
            # 注入额外上下文给 LLM
            self._inject_context(hook_result.additional_contexts)

        result = await tool.execute(**kwargs)

        # ── POST_TOOL_USE hook (已有，增强) ──
        await self.hook_registry.execute(
            HookEvent.POST_TOOL_USE,
            HookContext(tool_name=tc.name, arguments=kwargs, result=result),
        )

    # ── STOP hook ──
    hook_result = await self.hook_registry.execute(
        HookEvent.STOP,
        HookContext(assistant_message="".join(text_chunks)),
    )
    if hook_result.should_block:
        # Re-prompt: 将 blocking error 作为用户消息，让 LLM 重新回答
        self.messages.append(ChatMessage(
            role="user",
            content=f"[Hook feedback]: {hook_result.blocking_errors[0]}",
        ))
        continue  # 重新进入 LLM 调用

    await self.bus.emit(AgentEnd())

    # ── PRE_COMPACT / POST_COMPACT hook ──
    if self.compactor and self.compactor.should_compact(self.messages):
        await self.hook_registry.execute(HookEvent.PRE_COMPACT, HookContext())
        await self._auto_compact()
        await self.hook_registry.execute(HookEvent.POST_COMPACT, HookContext())
```

### 5.7 FileWatcher — 文件变化自动触发

```python
# hooks/watcher.py — 新增

class FileWatcher:
    """监控文件变化，触发 FileChanged hook。"""

    def __init__(self, hook_registry: HookRegistry, bus: MessageBus):
        self._registry = hook_registry
        self._bus = bus
        self._watch_paths: set[str] = set()
        self._observer: Observer | None = None  # watchdog 库

    def start(self, paths: list[str]) -> None:
        """启动文件监控。"""
        self._watch_paths = set(paths)
        # 使用 watchdog 库或 polling fallback
        # 检测到变化 → _on_file_changed()

    async def _on_file_changed(self, path: str, event_type: str) -> None:
        """文件变化回调 — fire-and-forget。"""
        result = await self._registry.execute(
            HookEvent.FILE_CHANGED,
            HookContext(file_path=path, change_type=event_type),
        )
        # 动态更新监控路径
        if result.watch_paths:
            self.update_paths(result.watch_paths)
        # 将 hook 输出注入 transcript
        for ctx in result.additional_contexts:
            await self._bus.emit(SystemMessage(content=ctx))

    def update_paths(self, paths: list[str]) -> None: ...
    def stop(self) -> None: ...
```

使用 `watchdog` 库（Python 标准文件监控）或 polling fallback。CC 用 `chokidar`（Node.js），`watchdog` 是 Python 生态的对应物。

### 5.8 LSP 被动诊断 → Function Hook 桥接

LSP 被动诊断不直接触发 FileChanged hook（与 CC 一致），而是通过 Function Hook 注册到 `POST_TOOL_USE` 事件：

```python
# 在 main.py 初始化时
def lsp_diagnostic_hook(context: HookContext) -> HookResult:
    """在工具执行后检查 LSP 诊断，注入到上下文。"""
    if context.tool_name in ("write_file", "edit_file"):
        diags = lsp_service.get_diagnostics(context.arguments.get("path", ""))
        errors = [d for d in diags if d.severity == 1]
        if errors:
            return HookResult(
                additional_context=f"LSP errors in {path}:\n" + "\n".join(
                    f"  L{d.line}: {d.message}" for d in errors[:5]
                )
            )
    return HookResult()  # no-op

hook_registry.add_function_hook(
    HookEvent.POST_TOOL_USE,
    callback=lsp_diagnostic_hook,
    priority=100,  # 低优先级，在用户 hook 之后
)
```

这样每次写入/编辑文件后，LSP 诊断自动检查并注入上下文，LLM 在下一轮会看到编译错误。

### 5.9 实现优先级

| 优先级 | 模块 | 说明 |
|--------|------|------|
| **P0** | HookEvent 枚举扩展 (15 个事件) | 架构基础 |
| **P0** | HookResult 结构化 (blocking/context/updatedInput) | 从二元到结构化 |
| **P0** | HookRegistry (多来源 + 优先级排序) | 替代当前 HookConfig |
| **P0** | Agent Loop 集成点扩展 (6 个位置) | SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, Stop, Compact |
| **P1** | FunctionHook 支持 | Python 回调注册，LSP 诊断桥接依赖此 |
| **P1** | Exit code 语义对齐 (0/2/other) | 对齐 CC |
| **P1** | FileWatcher (watchdog) | 文件变化自动触发 |
| **P2** | Command hook 异步模式 (`{"async": true}`) | 后台 hook |
| **P2** | HookContext 完整化 | 传递 messages、session_id 等完整上下文 |
| **P3** | Prompt hook / HTTP hook | 后续按需 |

---

## 六、总结

CC 的 hook 系统本质是一个 **可扩展的行为注入层**，位于 Transport Handler 和业务逻辑之间。理解其架构的关键在于：

1. **Handler 是消息路由**（Transport 层），**Hook 是行为注入**（Business 层）。Handler 路由消息到业务逻辑，业务逻辑在特定节点触发 hook。

2. **LSP 被动触发走的不是 hook 路径**，而是 "Handler 缓存 diagnostics → prompt 注入 → LLM 下一轮自然感知"。文件变化自动触发走的是 "chokidar watcher → FileChanged hook → 结果注入 transcript" 路径。两者独立但互补。

3. **Hook 的核心价值不是 pass/fail，而是结构化修改**——修改工具参数、注入额外上下文、修改权限决策。这使得 hook 从"看门人"升级为"协作者"。

4. **AsyncGenerator 模式是执行引擎的灵魂**——允许进度反馈、增量聚合、优雅取消。SuperHaojun 可以用 Python 的 `async for` + `asyncio.gather` 实现等价效果。

当前 SuperHaojun 的 hook 系统只覆盖了 CC 能力的约 5%（2/27 事件，1/5 类型，无结构化输出，无文件监控）。本重构方案通过扩展到 15 个事件、2 种类型、结构化结果、FileWatcher，将覆盖率提升到约 50%，同时保持代码量在合理范围（预计 ~600 行 vs CC 的 ~3,700 行）。
