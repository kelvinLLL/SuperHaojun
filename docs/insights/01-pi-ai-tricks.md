# Insight 01: Python Migration Notes

## TLS Certificate Issue with Proxy Endpoints
**Problem**: Python `httpx`/`aiohttp` rejects self-signed or CDN-chained certificates.
**Fix**: 自定义 `ssl.SSLContext` with `check_hostname=False, verify_mode=CERT_NONE`，传给 `httpx.AsyncClient(verify=ssl_ctx)`。
比 Node.js 的 `NODE_TLS_REJECT_UNAUTHORIZED=0` 更精细 —— 只影响这一个 client。

## pydantic-settings 的 .env 读取行为
**Gotcha**: `BaseSettings(env_file=".env")` 会从 CWD 读取 `.env` 文件，即使环境变量已通过 `monkeypatch.setenv` 设置。
**测试解决方案**: `monkeypatch.chdir(tmp_path)` 切到空目录避免 `.env` 干扰。

## openai SDK Streaming Pattern
```python
stream = await client.chat.completions.create(
    model="gpt-5.4",
    messages=[...],
    stream=True,
)
async for chunk in stream:
    delta = chunk.choices[0].delta
    if delta.content:
        print(delta.content, end="", flush=True)
```
- `stream=True` 返回 `AsyncStream[ChatCompletionChunk]`
- 每个 chunk.choices[0].delta 可能有 `content`、`tool_calls`、`role`
- 第一个 chunk 通常只有 `role="assistant"`，无 content

## asyncio REPL Pattern
```python
async def repl():
    loop = asyncio.get_event_loop()
    while True:
        user_input = await loop.run_in_executor(None, lambda: input("you> "))
        async for chunk in agent.chat(user_input):
            sys.stdout.write(chunk)
```
`input()` 是 blocking 的，`run_in_executor` 把它放到线程池，不阻塞 event loop。

## Agent 作为 AsyncIterator
`Agent.chat()` 返回 `AsyncIterator[str]`（通过 `yield`）。
调用者可以灵活消费：逐 chunk 打印、收集为字符串、传给其他处理器。
这比 pi-mono 的 event subscription 模式更 Pythonic。

## frozen dataclass + __post_init__
```python
@dataclass(frozen=True)
class ModelConfig:
    model_id: str
    is_reasoning: bool = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "is_reasoning", bool(re.search(r"o[1-9]|gpt-5", self.model_id)))
```
frozen dataclass 的 `__post_init__` 需要用 `object.__setattr__` 绕过冻结限制。
