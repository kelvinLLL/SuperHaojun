# SuperHaojun Architecture: Phase C & D

> Phase C: 智能增强 — System Prompt 工程 + Context Compaction
> Phase D: 持久化 — Session 管理 + 跨 Session 记忆
>
> **v2 实现**。从 v1 的简易方案重构为参考 Claude Code 成熟模式的架构。
> 本文档记录设计决策、源码实现、与 Claude Code 的对比分析。

---

## 度量快照

| 指标 | Phase C+D v1 | Phase C+D v2 | 变化 |
|------|-------------|-------------|------|
| 源码行数 | ~542 (4 模块) | ~1,490 (4 模块) | +948 (+175%) |
| 文件数 | 8 (.py) | 19 (.py) | +11 |
| prompt/ | 148 行 (1 文件) | 537 行 (11 文件) | Section Registry 拆分 |
| compact/ | 128 行 (1 文件) | 275 行 (4 文件) | +prompts +session_compact |
| session/ | 136 行 (1 文件) | 309 行 (2 文件) | JSONL + SessionWriter |
| memory/ | 130 行 (1 文件) | 369 行 (3 文件) | Markdown + extractor |
| 新增常量模块 | — | `constants.py` (14 行) | 品牌抽象 |

---

## Phase C: 智能增强

### C1. System Prompt 工程 (v2, `prompt/`, 537 行)

#### 架构升级：Section Registry

v1 是 `SystemPromptBuilder` 内 6 个 `_xxx_section()` 硬编码方法串行拼接。v2 引入 Section Registry 模式，每个 section 是独立类：

```
prompt/
├── builder.py                 # SystemPromptBuilder v2 (registry-based, 122 行)
├── context.py                 # PromptContext + GitInfo + gather_git_info (97 行)
├── __init__.py
└── sections/
    ├── __init__.py            # PromptSection ABC (33 行)
    ├── identity.py            # 身份 + 行为准则 (51 行)
    ├── tools.py               # 工具描述列表 (28 行)
    ├── project_instructions.py # 递归指令文件发现 (74 行)
    ├── custom.py              # 用户自定义指令 (25 行)
    ├── environment.py         # 工作目录 + git + platform (37 行)
    ├── memory.py              # 记忆注入 + 指导文本 (31 行)
    └── session_context.py     # session 摘要上下文 (25 行)
```

**核心抽象 — `PromptSection` ABC** (`prompt/sections/__init__.py:12`):

```python
class PromptSection(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def cacheable(self) -> bool:
        return True  # 默认 cacheable

    @abstractmethod
    def build(self, ctx: PromptContext) -> str | None: ...
```

- `cacheable` 属性区分两类 section：稳定内容（identity、tools）vs 每轮变化内容（git status、memory）
- `build()` 返回 `None` 表示跳过（如无 memory 时不注入空段）
- 所有 section 共享 `PromptContext` 数据对象，避免 section 间直接依赖

**Section 注册与排列** (`prompt/builder.py:28`):

```python
def _default_sections() -> list[PromptSection]:
    return [
        # Cacheable (stable across turns)
        IdentitySection(),       # 身份 + 行为 + 安全 + 输出风格
        ToolsSection(),          # 工具名称和描述
        ProjectInstructionsSection(),  # SUPERHAOJUN.md / AGENT.md
        CustomInstructionsSection(),   # 用户自定义指令
        # --- DYNAMIC BOUNDARY ---
        # Uncacheable (may change every turn)
        EnvironmentSection(),    # cwd + git + platform
        MemorySection(),         # 跨 session 记忆 + 指导文本
        SessionContextSection(), # compaction 摘要
    ]
```

Builder 按 registry 顺序遍历，cacheable 在前，uncacheable 在后，中间插入 `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` 标记 (`builder.py:107`):

```python
def build(self) -> str:
    for section in self._sections:
        content = section.build(ctx)
        if section.cacheable:
            cacheable_parts.append(content)
        else:
            uncacheable_parts.append(content)
    parts = cacheable_parts[:]
    if uncacheable_parts:
        parts.append(SYSTEM_PROMPT_DYNAMIC_BOUNDARY)
        parts.extend(uncacheable_parts)
    return "\n\n".join(parts)
```

**品牌抽象** (`constants.py`):

```python
BRAND_NAME = "haojun"
BRAND_DIR = f".{BRAND_NAME}"                    # → ".haojun"
INSTRUCTION_FILES = ("SUPERHAOJUN.md", "AGENT.md")  # 不搜索 CLAUDE.md
SYSTEM_PROMPT_DYNAMIC_BOUNDARY = "--- DYNAMIC CONTEXT BELOW ---"
```

- 所有路径通过 `BRAND_DIR` 引用（`.haojun/sessions/`, `.haojun/memory/`）
- 指令文件排除 `CLAUDE.md`，避免与 Claude Code 本身冲突
- 修改 `BRAND_NAME` 一处即可全品牌切换

**递归指令文件发现** (`prompt/sections/project_instructions.py:33`):

```python
def _discover_instructions(working_dir: str) -> list[str]:
    current = Path(working_dir).resolve()
    while True:
        ancestors.append(current)
        parent = current.parent
        if parent == current: break
        current = parent

    for dir_path in reversed(ancestors):  # root first → cwd last
        for search_dir in [dir_path, dir_path / BRAND_DIR]:
            for filename in INSTRUCTION_FILES:
                # 读取文件，去重（seen_paths），追加
```

- 从 cwd 向上遍历至 filesystem root
- 每层检查目录本身 + `.haojun/` 子目录
- 祖先目录的指令在前（低优先级），当前目录在后（高优先级）
- `seen_paths: set[Path]` 按 resolved path 去重

**Git 5-way 并行采集** (`prompt/context.py:54`):

```python
async def gather_git_info(cwd: str) -> GitInfo:
    branch, status, log, diff_stat, remote = await asyncio.gather(
        _run_git(cwd, "rev-parse", "--abbrev-ref", "HEAD"),
        _run_git(cwd, "status", "--short"),
        _run_git(cwd, "log", "--oneline", "-5"),
        _run_git(cwd, "diff", "--stat", "HEAD"),
        _run_git(cwd, "remote", "-v"),
    )
```

- 每个命令通过 `asyncio.create_subprocess_exec` 异步执行，5s 超时
- 失败静默返回空字符串（partial info is fine）
- status 和 diff_stat 截断到 200 字符
- `GitInfo` 是 frozen dataclass，传入 `PromptContext` 供 `EnvironmentSection` 使用
- 同时保留 `gather_git_info_sync()` 同步 fallback（2-way，用于非 async 上下文）

**IdentitySection 内容** (`prompt/sections/identity.py:13`):

参考 Claude Code 的 system prompt 风格，覆盖：
- 核心身份声明
- 行为准则（concise、match user language、clean code）
- 工具使用原则（dedicated tools > bash、parallel when independent）
- 安全准则（reversibility awareness、confirm destructive actions）
- 输出风格（no framing、no trailing summary）

**MemorySection 指导文本** (`prompt/sections/memory.py:13`):

```python
_MEMORY_GUIDANCE = """\
The following memories were persisted from previous sessions.
Use them as context but verify against current code state before acting.
Memory may be stale — if it conflicts with what you observe, trust current state."""
```

注入 memory 时前置指导文本，告知 LLM 记忆可能过期，应以当前代码状态为准。

**Builder 集成变化**:

- `set_memory_text()` / `set_session_summary()` — 动态更新，仅清除 `_cached_full`（不影响 cacheable 缓存）
- `register_section()` — 运行时添加 section（如 MCP 指令），自动 invalidate
- `invalidate()` — 清除所有缓存，compaction 和 /clear 时调用

#### 对比 Claude Code

| 维度 | SuperHaojun v1 → v2 | Claude Code |
|------|---------------------|-------------|
| 代码量 | 148 → 537 行 | ~730 行 |
| 架构 | 6 个硬编码方法 → Section Registry ABC | Section Registry (全局注册 + cacheable 标记) |
| Sections | 7 个独立类 | 18+ 个注册 section |
| 缓存 | 整 prompt 一把 → cacheable/full 双层 | 每 section 独立缓存 |
| Prompt cache | `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` 标记 | 同名标记 + API `cache_control` 集成 |
| Git 采集 | 串行 2 命令 → 异步并行 5 命令 | `Promise.all` 5 命令 |
| 指令发现 | 固定 2 目录 → cwd 到 root 递归 | 递归扫描 + 过滤策略 |
| 品牌隔离 | `.superhaojun/` 硬编码 → `BRAND_DIR` 常量 | `.claude/` 硬编码 |
| 记忆注入 | 无指导 → 含 staleness 警告文本 | 含完整保存/使用指导说明 |

**v2 收获**: Section Registry 使新增 section 变为"写个类 + 注册"，不改 builder 主逻辑。cacheable/uncacheable 分离为未来 API prompt cache 打下基础。递归发现消除了"只能在 cwd 放指令文件"的限制。

**与 CC 仍有差距**: CC 的每个 section 有独立缓存（我们是 cacheable 部分整体缓存）；CC 集成了 API 层的 `cache_control: {"type": "ephemeral"}`；CC 有自动触发 invalidation 的场景更多（MCP 变化、首次 tool 注册等）。

---

### C2. Context Compaction (v2, `compact/`, 275 行)

#### 架构升级：结构化 Prompt + Circuit Breaker + Session Compact

v1 是单层 `summarize_fn(text)` 调用。v2 三个关键改进：

```
compact/
├── compactor.py       # ContextCompactor v2 (159 行)
├── prompts.py         # 结构化 prompt 模板 (50 行)
├── session_compact.py # Session-level 摘要 (51 行)
└── __init__.py
```

**结构化 Compaction Prompt** (`compact/prompts.py`):

参考 Claude Code 的 9-section prompt 模板，定义 7 段结构化输出格式：

```
COMPACTION_USER_PROMPT:
├── Instructions (6 条保留规则)
│   ├── Preserve ALL file paths, function names, variable names, line numbers
│   ├── Preserve user's original intent and unresolved tasks
│   ├── Preserve error messages and solutions
│   ├── Preserve decisions and rationale
│   ├── Track tool calls and key results
│   └── Be concise — omit pleasantries, repetition, dead ends
└── Output Format (7 个必填章节)
    ├── Primary Request and Intent
    ├── Key Technical Context
    ├── Files Modified or Read
    ├── Current Progress
    ├── Errors and Resolutions
    ├── Active Decisions
    └── Pending Tasks
```

同时定义 `SESSION_SUMMARY_PROMPT` 供 session compact 使用。

**Circuit Breaker** (`compact/compactor.py:88`):

```python
@dataclass
class ContextCompactor:
    cooldown_seconds: float = 30.0
    _last_compact_time: float = 0.0

    @property
    def is_on_cooldown(self) -> bool:
        if self._last_compact_time == 0.0:
            return False
        return (time.monotonic() - self._last_compact_time) < self.cooldown_seconds
```

- 连续 compact 间隔 < 30s 时返回空 `CompactionResult`（不执行压缩）
- 防止"压缩后仍超阈值 → 再压缩 → 再超"的无限循环
- `_last_compact_time` 使用 `time.monotonic()` 保证单调递增

**Token 输出限制** (`compact/compactor.py:145`):

```python
max_summary_tokens = int(self.max_tokens * 0.3)
max_summary_chars = max_summary_tokens * 4
if len(summary) > max_summary_chars:
    summary = summary[:max_summary_chars] + "\n[truncated]"
```

- 压缩摘要不超过 `max_tokens * 0.3`，留足空间给后续对话
- 过长则截断并标注 `[truncated]`

**Full Compaction 流程**:

```
1. should_compact(messages) → token > max_tokens * 0.8?
2. Circuit breaker check → 冷却期内？跳过
3. Split: old_messages + preserved (最近 4 条)
4. Build: COMPACTION_USER_PROMPT.format(conversation=_messages_to_text(old))
5. Call: summarize_fn(prompt_text) — sub-agent LLM 调用
6. Enforce: 截断到 max_tokens * 0.3
7. Return: CompactionResult(summary, removed_count, preserved_count, ...)
8. Agent: messages = [compaction_boundary] + preserved
9. Agent: prompt_builder.invalidate()
```

**Agent 集成不变** (`agent.py:181`): 每次 `handle_user_message()` 结束后检查 `should_compact()`，自动调用 `_auto_compact()`。

**Session Memory Compact** (`compact/session_compact.py`):

```python
async def compact_session(
    messages: list[ChatMessage],
    summarize_fn: Callable[[str], Awaitable[str]] | None = None,
) -> str:
    conversation_text = _messages_to_text(messages)
    prompt = SESSION_SUMMARY_PROMPT.format(conversation=conversation_text)
    return await fn(prompt)
```

- Session 结束时生成 session-level 摘要
- 摘要存储为 `SessionInfo.session_summary` 字段
- 可用于 session 恢复时的 context injection
- 是 Feature 10 auto-extraction 的数据来源

#### 对比 Claude Code

| 维度 | SuperHaojun v1 → v2 | Claude Code |
|------|---------------------|-------------|
| 代码量 | 128 → 275 行 | ~3,960 行 |
| 压缩策略 | 1 层 → Full + Session Memory | 4 层 (micro → cached micro → full → session memory) |
| 摘要 Prompt | 无结构 → 7 段结构化模板 | 9 段结构化 + `<analysis>`/`<summary>` 分离 |
| 安全机制 | 无 → circuit breaker (30s cooldown) | Circuit breaker (3 次失败停止) |
| Token 限制 | 无 → max_tokens * 0.3 | MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20,000 |
| 执行隔离 | 同进程 | Forked subprocess |
| 触发方式 | 仅自动 → 自动 + /compact 手动 | 自动 + 错误触发 + /compact 手动 |
| Session compact | 无 → compact_session() | registerPostSamplingHook 后台运行 |
| Micro-compaction | 无 | 有 (清除旧 tool result, ~530 行) |
| 压缩后恢复 | 无 | 重读 top 5 文件 + top 5 skills |

**v2 收获**: 结构化 prompt 让摘要保留关键上下文（文件路径、决策、错误），而非 v1 的"截断前 500 字符"。Circuit breaker 防止压缩风暴。Session compact 为跨 session 记忆提取提供素材。

**与 CC 仍有差距**: 缺少 micro-compaction（最高性价比的改进——清除旧 tool result 可大幅延迟 full compact）；缺少 cached micro-compaction（API 层 prompt cache）；full compact 仍在同进程执行（CC 用 forked subprocess 隔离）；无压缩后文件恢复机制。

---

## Phase D: 持久化

### D1. Session 管理 (v2, `session/`, 309 行)

#### 架构升级：JSONL 增量写入

v1 每次 `save()` 全量覆写 JSON 文件。v2 切换为 JSONL (JSON Lines) 格式，支持增量追加。

```
session/
├── manager.py   # SessionManager + SessionWriter (304 行)
└── __init__.py
```

**SessionWriter — 增量写入器** (`session/manager.py:53`):

```python
class SessionWriter:
    def __init__(self, path: Path):
        self._path = path
        self._file: TextIO | None = None

    def write_header(self, info: SessionInfo) -> None:
        """Session 元数据作为 JSONL 第一行。"""
        header = {"type": "header", "session_id": ..., "name": ..., "created_at": ...}
        f.write(json.dumps(header) + "\n")
        f.flush()

    def append(self, message: ChatMessage) -> None:
        """单条消息立即追加 + flush。"""
        f.write(json.dumps(_message_to_dict(message)) + "\n")
        f.flush()
```

- 每条消息 `append()` 后立即 `flush()`，崩溃最多丢 1 条
- 支持 context manager (`with SessionWriter(path) as writer:`)
- Lazy open：首次写入时才创建文件

**JSONL 格式**:

```jsonl
{"type":"header","session_id":"abc123","name":"my-session","created_at":1712345678.0,"session_summary":""}
{"type":"message","role":"user","content":"Hello","tool_calls":null,"tool_call_id":null,"name":null}
{"type":"message","role":"assistant","content":"Hi there!","tool_calls":null,"tool_call_id":null,"name":null}
```

- 第一行 `type: "header"` — session 元数据（ID、名称、创建时间、摘要）
- 后续行 `type: "message"` — 逐条消息
- `SessionInfo` 新增 `session_summary` 字段，存储 session compact 摘要

**向后兼容** (`session/manager.py:97`):

```python
def _is_jsonl(path: Path) -> bool:
    first_line = text.split("\n", 1)[0].strip()
    obj = json.loads(first_line)
    return "type" in obj  # JSONL header has "type"; old JSON has "messages"

def _load_legacy_json(path: Path) -> tuple[dict | None, list[ChatMessage]]:
    data = json.loads(path.read_text())
    messages = [_message_from_dict(m) for m in data.get("messages", [])]
```

- `_find_session_file()` 优先查找 `.jsonl`，fallback 到 `.json`
- `load()` 自动检测格式，两种都能读
- `save()` 总是写 JSONL 格式；如果存在旧 `.json` 文件则删除

**JSONL 读取容错** (`session/manager.py:128`):

```python
for line in path.read_text().strip().split("\n"):
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        continue  # Skip corrupted lines
```

- 逐行解析，跳过损坏行
- 部分文件损坏不影响其余消息恢复

**两种写入模式**:

1. `save(name, messages)` — 全量写入（删除旧文件，重写 header + 所有消息）
2. `create_writer(name)` — 返回 `(SessionInfo, SessionWriter)` 用于增量追加

**存储路径**: `.haojun/sessions/{safe_name}.jsonl`（通过 `BRAND_DIR` 常量引用）

#### 对比 Claude Code

| 维度 | SuperHaojun v1 → v2 | Claude Code |
|------|---------------------|-------------|
| 代码量 | 136 → 309 行 | ~552 行 |
| 存储格式 | JSON 全量覆写 → JSONL 增量追加 | JSONL (全局单文件 `history.jsonl`) |
| 崩溃安全 | 差（全量覆写中断 = 数据丢失） → 好（flush per message） | 好（append + flush） |
| 格式检测 | 无 → `_is_jsonl()` 自动识别 | 无需（始终 JSONL） |
| 向后兼容 | 无 → 自动读取旧 JSON 格式 | 无需 |
| 元数据 | 嵌入 JSON 顶层 → JSONL 首行 header | 每行都有 project + sessionId 字段 |
| 存储范围 | 每 session 一文件（本地） | 全局单文件 + 远程 CCR |
| Session 摘要 | 无 → `session_summary` 字段 | SESSION_NOTES.md |
| 大内容处理 | 无 | Hash-keyed 外部 store（paste > 1KB） |

**v2 收获**: JSONL 增量写入解决了 v1 最大的实用性问题——长对话的写入性能和崩溃安全。SessionWriter 的 `append()` + `flush()` 模式保证每条消息立即持久化。向后兼容让迁移无感。

**与 CC 仍有差距**: CC 是全局单文件存储所有项目的 session（通过 `project` + `sessionId` 过滤），适合跨项目搜索。CC 的 history.jsonl 只存用户输入（完整对话靠远程恢复），我们存完整消息。缺少大内容外存机制。

---

### D2. 跨 Session 记忆 (v2, `memory/`, 369 行)

#### 架构升级：Markdown 存储 + 自动提取

v1 是单 JSON 文件存储所有记忆条目。v2 切换为 Markdown 文件集 + LLM 自动提取。

```
memory/
├── store.py      # MemoryStore v2 — markdown backend (268 行)
├── extractor.py  # Auto-extraction via LLM (95 行)
└── __init__.py
```

**Markdown 存储格式**:

```
.haojun/memory/
├── MEMORY.md                              # 索引（自动生成）
├── user_full_stack_engineer_a1b2c3d4.md   # 各 topic 文件
├── feedback_tdd_preferred_e5f6g7h8.md
├── project_ai_harness_i9j0k1l2.md
└── reference_claude_code_repo_m3n4o5p6.md
```

**单条记忆文件** — 带 YAML frontmatter:

```markdown
---
name: Full Stack Engineer
description: 用户角色和技术背景
type: user
id: a1b2c3d4...
created_at: 1712345678.0
---
独立开发者 / 全栈工程师，主要使用 Python、JSX、TSX。
```

**MEMORY.md 索引** — 自动生成，按类别分组:

```markdown
# Memory Index

## User
- [Full Stack Engineer](user_full_stack_engineer_a1b2c3d4.md) — 用户角色和技术背景

## Project
- [AI Harness](project_ai_harness_i9j0k1l2.md) — 自建 AI harness 项目背景
```

**MemoryEntry 扩展** (`memory/store.py:44`):

```python
@dataclass
class MemoryEntry:
    category: MemoryCategory
    content: str
    entry_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: float = field(default_factory=time.time)
    name: str = ""          # 新增：标题
    description: str = ""   # 新增：简述（用于 MEMORY.md 索引和相关性判断）
```

- v2 新增 `name` 和 `description` 字段
- `name` 自动从 content 前 50 字符生成（如未手动指定）
- `description` 用于 MEMORY.md 索引行的描述

**Markdown 序列化/反序列化** (`memory/store.py:60`):

```python
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)", re.DOTALL)

def _entry_to_markdown(entry: MemoryEntry) -> str:
    return f"---\nname: {entry.name}\ndescription: {entry.description}\ntype: {entry.category.value}\nid: {entry.entry_id}\ncreated_at: {entry.created_at}\n---\n{entry.content}\n"

def _entry_from_markdown(text: str) -> MemoryEntry | None:
    match = _FRONTMATTER_RE.match(text)
    # 解析 frontmatter key: value 对 → 构造 MemoryEntry
```

**文件名生成** (`memory/store.py:104`):

```python
def _safe_filename(entry: MemoryEntry) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", entry.name.lower())[:30].strip("_")
    return f"{entry.category.value}_{slug}_{entry.entry_id[:8]}.md"
```

- 格式: `{category}_{slug}_{id_prefix}.md`
- slug 从 name 生成，最长 30 字符，非字母数字替换为 `_`
- ID 前缀保证唯一性

**Legacy 迁移** (`memory/store.py:134`):

```python
def _migrate_legacy(self) -> None:
    if not self._legacy_path.exists(): return
    data = json.loads(self._legacy_path.read_text())
    for item in data:
        entry = MemoryEntry(...)
        self._write_entry(entry)
    self._legacy_path.unlink()  # 迁移后删除旧文件
```

- 构造时自动检测 `memory.json`
- 逐条转换为 markdown 文件
- 迁移成功后删除旧 JSON 文件

**MemoryStore API 保持兼容**:

```python
store.add(category, content, name="", description="") -> MemoryEntry
store.get(entry_id) -> MemoryEntry | None
store.list_entries(category?) -> list[MemoryEntry]
store.delete(entry_id) -> bool
store.search(query) -> list[MemoryEntry]
store.to_prompt_text() -> str
```

- `add()` → 写 markdown 文件 + 重建 MEMORY.md 索引
- `delete()` → 遍历 `.md` 文件查找 `id:` 匹配行 → 删除文件 + 重建索引
- `search()` → 内存中子串匹配（与 v1 相同）
- `to_prompt_text()` → 按类别分组生成注入文本（与 v1 格式一致）

**自动记忆提取** (`memory/extractor.py`):

```python
EXTRACTION_SYSTEM_PROMPT = """
You extract key facts and insights from a coding session summary.
Return a JSON array of objects: {category, content, name}

Rules:
- Only extract durable facts, not transient details
- Skip tasks in progress or temporary state
- Max 5 items per extraction
- Return [] if nothing worth remembering
"""

async def extract_memories(
    summary: str,
    llm_fn: Callable[[str, str], Awaitable[str]],
) -> list[MemoryEntry]:
```

- 输入：session summary（来自 Feature 8b session compact）
- 通过 LLM 调用提取值得持久化的记忆条目
- 输出最多 5 条 `MemoryEntry`（未持久化，调用方决定是否 `store.add()`）
- JSON 解析容错：自动剥离 markdown fences，`JSONDecodeError` 返回空列表
- Category 容错：未知类别 fallback 到 `USER`

**集成流程**:

```
Session 结束 / compact 完成
  → compact_session(messages) → session_summary
  → asyncio.create_task(extract_and_save(summary, store))  # 非阻塞
  → extract_memories(summary, llm_fn) → list[MemoryEntry]
  → store.add(entry.category, entry.content, entry.name)
```

- 非阻塞：`asyncio.create_task()` 在后台运行，不阻塞主对话
- 失败静默：extraction 异常不影响主流程
- 去重依赖 LLM 判断：extraction prompt 可传入现有记忆作为上下文（extractor.py 当前版本暂未实现此功能，留作增量优化）

#### 对比 Claude Code

| 维度 | SuperHaojun v1 → v2 | Claude Code |
|------|---------------------|-------------|
| 代码量 | 130 → 369 行 | ~2,400+ 行 |
| 存储格式 | 单 JSON 文件 → Markdown 文件集 (MEMORY.md + topic files) | Markdown 文件集 (同模式) |
| Frontmatter | 无 → name, description, type, id, created_at | name, description, type |
| 索引 | 无 → MEMORY.md 自动生成 (按类别分组) | MEMORY.md (max 200 行 / 25KB) |
| 人可编辑性 | 差 (JSON) → 优 (Markdown) | 优 (Markdown) |
| 自动提取 | 无 → LLM extraction from session summary | Session memory → post-sampling hook 后台提取 |
| 非阻塞 | N/A → asyncio.create_task | registerPostSamplingHook |
| Prompt 指导 | 无 → staleness 警告 + verification 指导 | 完整保存/使用/不保存规则 |
| Legacy 迁移 | N/A → 自动检测 memory.json → 转换为 markdown → 删除 | N/A |
| 分类系统 | user/feedback/project/reference (一致) | 一致 + team scope |
| 搜索 | 内存子串 → 内存子串 (未变) | 文件系统 walk + 内容匹配 |
| 容量限制 | 无 → 无 | 200 行 / 25KB |
| 团队支持 | 无 | private/team 双目录 |

**v2 收获**: Markdown 格式让记忆文件人可读可编辑——这是 Claude Code 记忆系统的核心优势，现在 SuperHaojun 也具备。自动提取从"用户手动 `/memory add`"进化为"session compact 后 LLM 自动识别值得记住的信息"。Legacy 迁移保证 v1 用户无痛升级。

**与 CC 仍有差距**: CC 的自动提取更深度集成（post-sampling hook 在每次 LLM 输出后运行，而非仅在 session 结束时）；CC 有 team scope 支持共享记忆；CC 有容量保护（200 行 / 25KB）；CC 的 extraction 提示将现有记忆作为上下文传入做去重判断。

---

## 综合分析：v1 → v2 的进化

### 设计模式一致性

v2 四个模块共享的架构模式：

- **ABC + Registry**: `PromptSection` ABC + section registry（prompt）, `MemoryCategory` StrEnum + markdown files（memory）
- **Frozen dataclass**: `GitInfo`, `CompactionResult`, `SessionInfo`, `MemoryEntry`
- **依赖注入**: `compactor.summarize_fn`, `extract_memories.llm_fn`, `PromptSection.build(ctx)`
- **品牌常量**: 所有路径通过 `BRAND_DIR` 引用
- **向后兼容**: Session JSON→JSONL 迁移, Memory JSON→Markdown 迁移
- **Prompt 模板分离**: `prompts.py` 集中管理所有 LLM prompt 模板

### v1 → v2 量级变化

| 模块 | v1 行数 | v2 行数 | 增长 | 关键变化 |
|------|--------|--------|------|---------|
| prompt/ | 148 | 537 | 3.6x | 1 文件 → 11 文件, Section Registry |
| compact/ | 128 | 275 | 2.1x | +结构化 prompt +circuit breaker +session compact |
| session/ | 136 | 309 | 2.3x | +SessionWriter +JSONL +向后兼容 |
| memory/ | 130 | 369 | 2.8x | +Markdown +frontmatter +extractor +legacy 迁移 |
| **总计** | **542** | **1,490** | **2.7x** | |

### 与 Claude Code 的量级对比

| 模块 | SuperHaojun v2 | Claude Code | 比例 |
|------|---------------|-------------|------|
| System Prompt | 537 行 | ~730 行 | 1:1.4 |
| Compaction | 275 行 | ~3,960 行 | 1:14 |
| Session | 309 行 | ~552 行 | 1:1.8 |
| Memory | 369 行 | ~2,400+ 行 | 1:6.5 |
| **总计** | **1,490 行** | **~7,640+ 行** | **1:5.1** |

v2 将总体比例从 1:14 缩小到 1:5.1。Prompt 和 Session 模块已接近 Claude Code 的量级，这两个模块的核心能力（Section Registry、JSONL 增量写入）也已对齐。Compaction 和 Memory 仍有较大差距，主要体现在 micro-compaction（CC ~530 行）和团队记忆 + 深度自动提取（CC ~2,400 行）上。

### 后续迭代优先级

**高价值（建议 Phase E 之前完成）:**
1. **Micro-compaction** — 清除旧 tool result 内容，保留消息结构。性价比最高的 compaction 改进，大幅延迟 full compact 触发
2. **Auto-extraction 去重** — extraction prompt 传入现有记忆做去重判断
3. **Prompt cache API 集成** — 利用 `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` 标记实际设置 `cache_control`

**中等价值（可在 Phase E/F 并行推进）:**
4. **Memory 容量保护** — MEMORY.md 最大行数 / 总大小限制
5. **Compaction subprocess 隔离** — summarize_fn 在独立进程中运行
6. **Git info async 集成** — builder.build() 改为 async，使用 `gather_git_info()` 而非 sync fallback

**低优先级（按需）:**
7. 大消息外存（tool result > 阈值时外存 hash-keyed）
8. Memory 文件系统搜索（替代内存子串匹配）
9. Compaction 后文件恢复（重读 top N 文件）
