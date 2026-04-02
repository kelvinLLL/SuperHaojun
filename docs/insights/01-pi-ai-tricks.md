# Insight 01: pi-ai Tricks & Gotchas

## TLS Certificate Issue with Proxy Endpoints
**Problem**: Node.js `fetch`/`undici` rejects self-signed or CDN-chained certificates that `curl` accepts.
**Root cause**: `UNABLE_TO_GET_ISSUER_CERT_LOCALLY` — the proxy's CA chain isn't in Node's built-in trust store.
**Fix**: `process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0"` before any network calls.
**Note**: This is fine for personal proxy endpoints. For production, install the CA cert properly.

## OpenAI SDK Compat Flags Matter
pi-ai's openai-completions provider auto-detects compat settings from `baseUrl` pattern matching (e.g., `openrouter.ai`, `api.z.ai`). For unknown proxy URLs, you need to manually set `compat`:
```typescript
compat: {
  supportsStore: false,        // Many proxies don't support the `store` field
  supportsDeveloperRole: true, // GPT-5.x / GPT-4o support developer role
}
```
Without `supportsStore: false`, the SDK sends `"store": false` which some proxies reject.

## pi-ai Provider Registration is Side-Effect Based
```typescript
import "@mariozechner/pi-ai/openai-completions"; // ← registers the provider
```
This import MUST happen before any `streamSimple()` call, otherwise you get:
`Error: No API provider registered for api: openai-completions`

The registration happens at module load time via `registerApiProvider()`.

## Agent.prompt() is Exclusive
Only one `prompt()` can run at a time. Calling it while streaming throws:
`"Agent is already processing a prompt. Use steer() or followUp() to queue messages"`

For steering during execution (e.g., tool interruption), use `agent.steer()`.

## streamFn is Called per LLM Invocation
The `streamFn` passed to Agent constructor is called on EVERY LLM call (not just once). This is important for:
- Resolving short-lived OAuth tokens
- Dynamic headers per request
- Per-call API key rotation

## Agent Event Protocol
Event order for a simple text response:
```
agent_start → turn_start → message_start → message_update* → message_end → turn_end → agent_end
```

For tool use:
```
agent_start → turn_start → message_start → message_update* (with toolcall_*) → message_end
  → tool_execution_start → tool_execution_end → turn_end (with toolResults)
  → turn_start → message_start → ... → agent_end
```

`message_update` carries `assistantMessageEvent` which is the raw stream event from pi-ai (text_delta, thinking_delta, toolcall_delta, etc.).

## convertToLlm: The Message Filter
`Agent.convertToLlm` converts `AgentMessage[]` → `Message[]`. Only three roles pass to LLM: `user`, `assistant`, `toolResult`. Custom messages (like `bashExecution`, `custom`, `branchSummary`) must be converted or filtered.

Default implementation: `messages.filter(m => m.role === "user" || m.role === "assistant" || m.role === "toolResult")`
