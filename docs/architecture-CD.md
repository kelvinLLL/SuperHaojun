# SuperHaojun Architecture: Phase C & D

> Phase C: 智能增强 — System Prompt 工程 + Context Compaction
> Phase D: 持久化 — Session 管理 + 跨 Session 记忆
>
> v1 实现。本文档记录设计决策、源码实现、与 Claude Code 的对比分析，供后续优化迭代参考。

---

## 度量快照

| 指标 | Phase A+B 结束 | Phase C+D 结束 | 增量 |
|------|---------------|---------------|------|
| 源码行数 | ~2,600 | ~3,400 | +800 |
| 测试行数 | ~1,300 | ~1,970 | +670 |
| 模块数 | 9 | 13 | +4 (prompt, compact, session, memory) |
| 测试文件 | 10 | 14 | +4 |
| 新增文件 | — | 8 (.py) | — |

---

## Phase C: 智能增强

### C1. System Prompt 工程 (`prompt/builder.py`, 148 行)

#### 我们的实现

`SystemPromptBuilder` 按固定顺序组装 6 个 section：

```
1. Base Instructions    — 身份、行为准则、代码风格
2. Environment Context  — 工作目录 + git branch/status
3. Project Instructions — AGENT.md / CLAUDE.md / SUPERHAOJUN.md 自动发现
4. Tool Descriptions    — 已注册工具的名称和描述列表
5. Memory              — 来自 MemoryStore.to_prompt_text() 的跨 session 记忆
6. Custom Instructions  — 用户自定义指令（构造时传入）
```

**关键设计点：**

- **指令文件发现**: 扫描 `working_dir` 和 `working_dir/.claude/` 下的 `AGENT.md`, `CLAUDE.md`, `SUPERHAOJUN.md`
- **Git 信息采集**: `subprocess.run(["git", ...], timeout=5)` 获取 branch + status，status 截断到 200 字符
- **缓存策略**: `_cached: str | None`，构建后缓存，`invalidate()` 手动失效（compaction 和 /clear 时调用）
- **Memory 注入**: 构造时传入 `memory_text`，作为独立 section 拼入 prompt

```python
# builder.py 核心流程
def build(self) -> str:
    if self._cached is not None:
        return self._cached
    sections = [self._base_section(), self._environment_section()]
    sections += [s for s in [self._project_instructions_section(),
                             self._tools_section(),
                             self._memory_section(),
                             self._custom_section()] if s]
    self._cached = "\n\n".join(sections)
    return self._cached
```

**Agent 集成**: `agent.py:77` — `_build_messages()` 优先使用 `prompt_builder.build()`，fallback 到静态 `system_prompt` 字段。

#### Claude Code 的实现

Claude Code 的 prompt 系统分布在 ~730 行代码中（`prompts.ts` 914行 + `context.ts` 189行 + `systemPromptSections.ts` 69行）。

**核心差异——Section Registry + 缓存分级：**

```typescript
// Claude Code 的 section 是注册到全局 registry 的 named, cacheable units
systemPromptSection('memory', () => loadMemoryPrompt())
systemPromptSection('env_info_simple', () => getEnvInfoSection())
DANGEROUS_uncachedSystemPromptSection('mcp_instructions', () => getMcpSection())
```

Claude Code 区分**两类 section**：
1. **Cacheable sections** — 跨 turn 缓存，只在显式 invalidate 时重建（base instructions、env info）
2. **Uncacheable sections** — 每次 turn 都重新计算（MCP instructions、token budget）

这两类之间有一个 `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` 标记，告诉 API 层哪些内容可以命中 prompt cache。

**Claude Code 组装的 section 远多于我们的 6 个：**
- Base: intro, system, doing-tasks, actions, tools, tone, style（7 个静态子 section）
- Dynamic: session_guidance, memory, ant_model_override, env_info, language, output_style, mcp_instructions, scratchpad, function_result_clearing, summarize_tool_results, token_budget（11+ 个动态 section）

**Git 信息采集——并行 + 更丰富：**
- `Promise.all([getBranch(), getDefaultBranch(), git status, git log -5, git config user.name])` 五路并行
- `--no-optional-locks` 避免 git lock 阻塞
- Status 截断到 2000 字符（我们是 200）
- 带 diagnostic logging 和 timing

**CLAUDE.md 发现——递归目录扫描 + 过滤：**
- 从项目根目录递归 walk
- 过滤掉 session memory 文件、已注入的 memory 文件
- 支持 `.claude/` 子目录
- 支持团队 memory（team scope）

#### 对比分析

| 维度 | SuperHaojun (v1) | Claude Code |
|------|-----------------|-------------|
| 代码量 | 148 行 | ~730 行 |
| Section 数 | 6 | 18+ |
| 缓存粒度 | 整个 prompt 一把缓存 | 每个 section 独立缓存 + cache/uncache 分级 |
| Git 采集 | 串行，2 个命令 | 并行，5 个命令 |
| 指令文件发现 | 固定 3 个文件名，2 个目录 | 递归扫描，过滤策略，支持团队 scope |
| Prompt cache 感知 | 无 | SYSTEM_PROMPT_DYNAMIC_BOUNDARY 标记 |
| 失效时机 | 手动 invalidate() | 手动 + MCP 变化 + 首次 tool 注册等自动触发 |

**v1 优势**: 极简可控，148 行覆盖核心需求，容易理解和调试。
**v1 短板**: 粒度太粗（一失效就全部重建）、Git 信息有限、不感知 API prompt cache。

---

### C2. Context Compaction (`compact/compactor.py`, 128 行)

#### 我们的实现

`ContextCompactor` 实现了最简的阈值触发 + LLM 摘要压缩：

```
1. estimate_tokens(text) — 字符数 / 4（粗略估算）
2. should_compact(messages) — token 总量 >= max_tokens * threshold (默认 0.8)
3. compact(messages) — 分割为 old + recent → summarize_fn(old) → CompactionResult
```

**核心流程：**

```python
async def compact(self, messages: list[ChatMessage]) -> CompactionResult:
    split_idx = len(messages) - self.preserve_recent  # 默认保留最近 4 条
    old_messages = messages[:split_idx]
    preserved = messages[split_idx:]
    conversation_text = _messages_to_text(old_messages)
    summary = await self.summarize_fn(conversation_text)  # 可注入 LLM 调用
    return CompactionResult(summary=summary, removed_count=..., ...)
```

**Agent 集成**: `agent.py:181` — 每次 `handle_user_message()` 结束后检查 `should_compact()`，自动调用 `_auto_compact()`。压缩结果替换 `self.messages`，并调用 `prompt_builder.invalidate()`。

**关键设计：**
- **`summarize_fn` 依赖注入**: 默认是截断（测试用），生产环境注入 LLM 调用
- **`CompactionResult`** 是 frozen dataclass，含 `summary`, `removed_count`, `preserved_count`, `pre_tokens`, `post_tokens`
- **`to_messages()`** 方法生成一条 `[Conversation compacted]` 系统消息作为边界

#### Claude Code 的实现

Claude Code 的压缩系统是 **~3,960 行代码**，实现了**四层压缩策略**：

**Layer 1 — Micro-compaction（最高频）：**
- 清除旧的 tool result 内容（保留消息结构，替换内容为 `[Old tool result content cleared]`）
- 针对特定工具类型：FILE_READ, BASH, GREP, GLOB, WEB_SEARCH 等
- 时间驱动：距离上次清除超过阈值时触发
- ~530 行 (`microCompact.ts`)

**Layer 2 — Cached micro-compaction（API 级别）：**
- 使用 `cache_control: {"type": "ephemeral"}` 和 edit operations
- 被清除的内容在 API 服务端通过 prompt cache 保留
- Cache hit 时不重新发送旧内容，节省传输
- ~153 行 (`apiMicrocompact.ts`)

**Layer 3 — Full compaction（阈值/错误/手动触发）：**
- 触发条件：
  - 自动: token 数 > `effectiveContextWindow - AUTOCOMPACT_BUFFER_TOKENS` (13k)
  - 错误: `prompt_too_long` API 错误
  - 手动: `/compact` 命令
- 使用**forked subagent**在独立进程中运行，隔离 main context
- 摘要 prompt 模板包含 9 个必填章节（Request, Concepts, Files, Errors, Problem-solving...）
- 输出格式: `<analysis>` (思考过程，丢弃) + `<summary>` (最终摘要)
- 摘要 token 限制: MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20,000
- 压缩后恢复: 重新读取 top 5 文件 + top 5 skills
- **Circuit breaker**: 连续 3 次失败后停止重试
- ~1,705 行 (`compact.ts`) + ~374 行 (`prompt.ts`) + ~351 行 (`autoCompact.ts`)

**Layer 4 — Session memory compaction：**
- 自动提取对话中的关键事实、决策、模式到 `SESSION_NOTES.md`
- 通过 `registerPostSamplingHook()` 在后台非阻塞运行
- 阈值: ~50K tokens 初始化，~80K tokens 每次更新
- ~630 行 (`sessionMemoryCompact.ts`)

**Token 估算——多后端支持：**
- 优先使用 API 的 token counter（Anthropic/Bedrock/Vertex）
- Fallback: ~3.3 字符/token 的本地估算
- ~495 行 (`tokenEstimation.ts`)

#### 对比分析

| 维度 | SuperHaojun (v1) | Claude Code |
|------|-----------------|-------------|
| 代码量 | 128 行 | ~3,960 行 |
| 压缩层数 | 1（全量摘要） | 4（micro → cached micro → full → session memory） |
| Token 估算 | `len(text) // 4` | API counter + fallback estimation（~3.3 chars/token） |
| 触发机制 | 阈值（0.8 * max_tokens） | 阈值 + API 错误 + 手动 + 时间 |
| 摘要生成 | 可注入 `summarize_fn` | Forked subagent + 结构化 prompt（9 章节） |
| 保留策略 | 最近 N 条消息 | 最近消息 + top 5 文件重读 + top 5 skills 恢复 |
| 安全机制 | 无 | Circuit breaker（3 次失败停止） |
| 执行隔离 | 同进程 | Forked subprocess |

**v1 优势**: 128 行实现了完整的"能压缩"能力，`summarize_fn` 注入设计使得测试和替换都很容易。
**v1 短板**: 单层压缩粒度太粗（要么不压缩，要么全量重建）；缺少 micro-compaction（清除旧 tool result 而不丢失结构）；token 估算不够准确；没有压缩后恢复机制。

---

## Phase D: 持久化

### D1. Session 管理 (`session/manager.py`, 136 行)

#### 我们的实现

`SessionManager` 提供 CRUD 操作，以 JSON 文件为存储后端：

```python
class SessionManager:
    def create(name) -> SessionInfo          # 创建元数据
    def save(name, messages) -> SessionInfo   # 序列化 ChatMessage 列表到 JSON
    def load(name) -> list[ChatMessage]       # 反序列化
    def list_sessions() -> list[SessionInfo]  # 扫描目录，按时间倒序
    def delete(name) -> bool                  # 删除文件
```

**存储格式**: 每个 session 一个 JSON 文件，存在 `.superhaojun/sessions/` 下：
```json
{
  "session_id": "uuid",
  "name": "my-session",
  "created_at": 1712345678.0,
  "updated_at": 1712345700.0,
  "message_count": 42,
  "messages": [ { "role": "user", "content": "...", ... }, ... ]
}
```

**关键设计：**
- **文件名安全化**: `"".join(c if c.isalnum() or c in "-_" else "_" for c in name)` 过滤非法字符
- **覆盖保留 ID**: 同名 save 时保留原 `session_id` 和 `created_at`
- **`SessionInfo`** frozen dataclass 只含元数据（不含消息体），用于列表展示

**Main 集成**: `main.py:158-159` — 构造 `SessionManager(storage_dir=".superhaojun/sessions")`，通过 `CommandContext` 传给命令系统。

#### Claude Code 的实现

Claude Code 的 session 系统 ~552 行（`history.ts` 464行 + `sessionHistory.ts` 88行），采用**完全不同的策略**：

**格式: JSONL（行分隔 JSON），而非 JSON 文件**
```
~/.claude/history.jsonl  ← 全局单文件，所有项目共享
```
每行一个 `LogEntry`：
```typescript
LogEntry {
  display: string        // 用户输入文本
  timestamp: number      // 毫秒时间戳
  project: string        // 项目路径（用于过滤）
  sessionId: SessionId   // UUID（用于分组）
  pastedContents?: {...} // 大 paste 内容的哈希引用
}
```

**关键差异：**
1. **全局单文件 vs 每 session 一文件**: Claude Code 用一个 JSONL 存所有项目的所有 session，通过 `project` + `sessionId` 字段过滤。我们用每个 session 一个 JSON 文件。
2. **只存入口信息 vs 完整对话**: Claude Code 的 history.jsonl 只存用户输入文本和元数据，不存 assistant 回复和 tool 调用。完整对话靠远程服务（CCR）恢复。我们直接存完整 `ChatMessage` 列表。
3. **大内容外存**: Paste 内容 > 1KB 时存到外部 hash-keyed store，history.jsonl 只存引用。
4. **Cloud 恢复**: 通过 OAuth + CCR API 的 `fetchLatestEvents()` / `fetchOlderEvents()` 分页拉取完整对话历史。
5. **Session ID 生成**: 启动时 `randomUUID()`，CCR 模式下从 ingress token 继承。

#### 对比分析

| 维度 | SuperHaojun (v1) | Claude Code |
|------|-----------------|-------------|
| 代码量 | 136 行 | ~552 行 |
| 存储格式 | JSON（每 session 一文件） | JSONL（全局单文件）+ 远程 CCR |
| 存储内容 | 完整 ChatMessage 列表 | 仅用户输入 + 元数据（对话靠远程恢复） |
| 位置 | `.superhaojun/sessions/` | `~/.claude/history.jsonl` |
| 查询 | 文件名匹配 | project + sessionId 字段过滤 |
| 大内容处理 | 无（全部 inline） | Hash-keyed 外部 store |
| 远程恢复 | 无 | OAuth + CCR API 分页拉取 |

**v1 优势**: 自包含，每个 session 文件就是完整对话，不依赖外部服务。简单、可调试、可手动编辑。
**v1 短板**: 大对话的 JSON 文件可能很大（全量消息 inline）；没有增量写入（每次 save 全量覆盖）；没有跨项目共享能力。

---

### D2. 跨 Session 记忆 (`memory/store.py`, 130 行)

#### 我们的实现

`MemoryStore` 是一个 JSON 文件支撑的 key-value 记忆存储：

```python
class MemoryCategory(StrEnum):
    USER = "user"           # 用户角色、偏好、知识背景
    FEEDBACK = "feedback"   # 用户对工作方式的反馈和纠正
    PROJECT = "project"     # 项目背景、目标、截止日期
    REFERENCE = "reference" # 外部资源的指针（Linear、Slack、Grafana 等）
```

**API：**
```python
store.add(category, content) -> MemoryEntry      # 新增记忆
store.get(entry_id) -> MemoryEntry | None         # 按 ID 查询
store.list_entries(category?) -> list[MemoryEntry] # 列表（可按类别过滤）
store.delete(entry_id) -> bool                    # 删除
store.search(query) -> list[MemoryEntry]          # 子串搜索
store.to_prompt_text() -> str                     # 生成 prompt 注入文本
```

**存储格式**: `.superhaojun/memory/memory.json`
```json
[
  { "entry_id": "uuid", "category": "project", "content": "...", "created_at": 1712345678.0 }
]
```

**Prompt 注入格式**: `to_prompt_text()` 按类别分组，生成结构化文本：
```
[user]
- User is a full-stack engineer, prefers Python
[project]
- Building an AI harness, Phase C+D in progress
```

**自动加载**: 构造时 `_load_if_exists()` 从磁盘加载；每次 `add()` / `delete()` 后自动 `save()`。

**Main 集成**: `main.py:162-163` — 构造 `MemoryStore`，通过 `to_prompt_text()` 传给 `SystemPromptBuilder`。

#### Claude Code 的实现

Claude Code 的记忆系统 ~2,400+ 行，采用**完全不同的存储范式**：

**格式: Markdown 文件（MEMORY.md + topic 文件），而非 JSON**

```
~/.claude/projects/<slug>/memory/
├── MEMORY.md           ← 入口文件（max 200 行 / 25KB）
├── user_role.md        ← topic 文件
├── feedback_testing.md
└── project_harness.md
```

每个 topic 文件有 YAML frontmatter：
```markdown
---
name: AI Harness Project
description: 项目背景和三阶段计划
type: project
---
用户正在构建自己的 AI harness 框架...
```

MEMORY.md 是索引，每行一个指针：
```markdown
- [Project: AI Harness](project_harness.md) — 自建 AI harness 项目背景
```

**关键差异：**

1. **Markdown vs JSON**: Claude Code 用人可读的 Markdown，用户可以手动编辑。我们用 JSON（程序友好但不便手动编辑）。
2. **入口 + topic 文件 vs 扁平列表**: Claude Code 的 MEMORY.md 是目录，topic 文件是内容。我们是一个 JSON 数组存所有条目。
3. **Team scope**: Claude Code 支持 private/team 双目录结构，团队共享 project/reference 类记忆。我们无团队概念。
4. **自动提取 (Session Memory)**: Claude Code 在后台自动从对话中提取记忆到 `SESSION_NOTES.md`，通过 `registerPostSamplingHook()` 非阻塞运行。我们只有手动 add。
5. **截断保护**: MEMORY.md 最多 200 行 / 25KB。超出时截断并附加警告。
6. **记忆四分类完全一致**: 两者都用 user / feedback / project / reference 四类。
7. **搜索**: Claude Code 用文件系统 walk + 文件内容匹配。我们用内存中的子串搜索。

#### 对比分析

| 维度 | SuperHaojun (v1) | Claude Code |
|------|-----------------|-------------|
| 代码量 | 130 行 | ~2,400+ 行 |
| 存储格式 | 单 JSON 文件 | Markdown 文件集（MEMORY.md + topic 文件） |
| 分类系统 | user/feedback/project/reference（一致） | 一致 + team scope |
| 人可编辑性 | 差（JSON） | 优（Markdown + frontmatter） |
| Prompt 注入 | `to_prompt_text()` 按类别分组 | `loadMemoryPrompt()` 含完整指导说明 |
| 自动提取 | 无（仅手动） | Session memory 后台自动提取 |
| 搜索 | 内存子串匹配 | 文件系统 walk + 内容匹配 |
| 容量限制 | 无 | 200 行 / 25KB |
| 团队支持 | 无 | private/team 双目录 |

**v1 优势**: 130 行实现了完整的 CRUD + search + prompt 注入。JSON 存储使得程序操作简单、序列化可靠。
**v1 短板**: JSON 不便手动编辑；缺少自动提取（Claude Code 的杀手级特性）；没有容量保护（可能无限增长）；记忆注入到 prompt 时缺少"什么该保存/不该保存"的指导说明。

---

## 综合分析：v1 的设计哲学与迭代方向

### v1 的一致性

四个新模块共享相同的设计模式：
- **Frozen dataclass** 做数据载体（CompactionResult, SessionInfo, MemoryEntry）
- **JSON 文件** 做持久化（session/*.json, memory/memory.json）
- **依赖注入** 做扩展点（compactor.summarize_fn, prompt_builder 参数）
- **与 Agent 的集成** 通过 dataclass 字段注入（agent.prompt_builder, agent.compactor）

### 与 Claude Code 的量级对比

| 模块 | SuperHaojun v1 | Claude Code | 比例 |
|------|---------------|-------------|------|
| System Prompt | 148 行 | ~730 行 | 1:5 |
| Compaction | 128 行 | ~3,960 行 | 1:31 |
| Session | 136 行 | ~552 行 | 1:4 |
| Memory | 130 行 | ~2,400+ 行 | 1:18 |
| **总计** | **542 行** | **~7,640+ 行** | **1:14** |

这个比例（1:14）是合理的。Claude Code 是生产级产品，需要处理大量边界情况、多后端、团队协作、远程服务集成。v1 覆盖了核心功能路径。

### 迭代优先级建议

基于对比分析，以下是每个模块最有价值的下一步改进：

**Prompt Builder:**
1. Section 级缓存（而非整个 prompt）
2. Git 信息并行采集 + 更丰富（default branch, log -5, user.name）
3. 递归发现指令文件（不限于固定 3 个文件名）

**Compaction:**
1. **Micro-compaction** — 清除旧 tool result 内容，保留消息结构。这是性价比最高的改进，大幅延迟 full compaction 的触发时机
2. 结构化摘要 prompt（Claude Code 的 9 章节模板）
3. 压缩后文件恢复（重读 top N 文件）
4. Circuit breaker（连续失败停止）
5. 更准确的 token 估算（tiktoken 或 API counter）

**Session:**
1. 增量写入（JSONL 追加而非全量覆盖）
2. 大消息外存（tool result 可能很大）
3. Session 命令集成（/session save, /session load, /session list）

**Memory:**
1. **Markdown 格式**取代 JSON — 人可编辑性是 Claude Code 记忆系统的核心优势
2. 自动提取 — 从对话中自动识别值得记住的信息
3. 容量保护 — 设置最大条目数/大小限制
4. 记忆注入时附加指导说明（什么该保存、什么不该保存）
