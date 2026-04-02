# Architecture Decisions

## 2026-04-02: Initial Scaffolding

### Tech Stack
- **Runtime**: Node.js + tsx (direct TypeScript execution, no build step for dev)
- **Package Manager**: pnpm
- **Core Dependencies**: `@mariozechner/pi-ai` + `@mariozechner/pi-agent-core` v0.64.0
- **Config**: dotenv for `.env` file support

### Why pi-mono's Agent class (not raw agent-loop functions)
pi-agent-core exports two levels of API:
1. **Low-level**: `agentLoop()` / `agentLoopContinue()` — pure functions, return EventStream
2. **High-level**: `Agent` class — stateful wrapper with subscribe/prompt/continue

Chose `Agent` class because:
- Manages message history automatically (`state.messages` grows per turn)
- Event subscription model (`agent.subscribe()`) cleanly separates concerns
- Built-in queuing for steering/follow-up messages (useful for future tool interruption)
- `reset()` for conversation clearing

### Model Configuration Strategy
Custom `createModel()` builds a `Model<"openai-completions">` object manually instead of using `getModel()` from the registry. Reason: the registry only contains known provider models. Our setup uses a custom proxy endpoint that isn't registered.

Key fields:
- `baseUrl`: passed to OpenAI SDK's `baseURL` param
- `compat.supportsStore`: set to `false` — many proxies don't support `store` field
- `compat.supportsDeveloperRole`: set to `true` — GPT-5.x supports developer role
- `reasoning`: auto-detected from model ID pattern (`/o[1-9]|gpt-5/`)

### Streaming Architecture
```
User Input → agent.prompt(text)
                ↓
         Agent internally:
         1. Wraps text as UserMessage
         2. Creates AgentContext snapshot (systemPrompt + messages + tools)
         3. Calls streamFn(model, context, options)
         4. Processes AssistantMessageEventStream
         5. Emits AgentEvents to subscribers
                ↓
         Subscriber receives events:
         - message_start → prepare output
         - message_update → stream text_delta to stdout
         - message_end → finalize output
         - agent_end → ready for next input
```

The `streamFn` is injected at Agent construction, allowing full control over API key resolution and provider options. This is the extension point for future multi-provider support.
