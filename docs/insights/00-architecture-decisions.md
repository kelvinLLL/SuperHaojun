# Architecture Decisions

## 2026-04-03: Python Rewrite

### Why Python over TypeScript
- 用户主力语言，生态更强（数据处理、ML、自动化）
- openai SDK Python 版功能对等，streaming 原生支持
- pydantic-settings 比 dotenv 更强（类型安全、默认值、验证）
- uv 替代 pnpm，极快的包管理

### Why openai SDK directly (not pi-mono, not LangChain)
- pi-mono 是 TypeScript-only，无法被 Python 项目复用
- openai SDK 的 `chat.completions.create(stream=True)` + function calling 已覆盖全部需求
- 自建轻量 Agent loop：~80 行代码，完全可控，渐进式扩展
- LangChain 过度封装，pydantic-ai 可作为后续多 provider 扩展方案

### Agent Architecture (Python 版)
```
User Input → Agent.chat(text)
                ↓
         1. 追加 user message 到 self.messages
         2. _build_messages() → system + history
         3. AsyncOpenAI.chat.completions.create(stream=True)
         4. async for chunk → yield delta to caller
         5. 追加 assistant message 到 self.messages
                ↓
         main.py REPL 消费 async iterator，逐 chunk 打印
```

### Config Strategy
- `pydantic-settings.BaseSettings` 自动读 `.env` + 环境变量
- `ModelConfig` frozen dataclass，`is_reasoning` 自动推断
- SSL: `httpx.AsyncClient(verify=ssl_ctx)` 处理代理端点证书问题

### Key Design Choices
- **Agent 是 dataclass** 而非 class —— 简洁，可测试
- **AsyncOpenAI** —— 全异步，streaming 天然 async for
- **httpx 自定义 SSL** —— 比设 NODE_TLS_REJECT_UNAUTHORIZED 更优雅
- **CLI 是 async REPL** —— `asyncio.run` + `run_in_executor` 处理 blocking input
