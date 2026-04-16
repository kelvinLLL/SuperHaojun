# WebUI Chat Gap Closure Plan

## Scope

- Implement the next `webui-chat` slice focused on two known gaps:
  - end-to-end browser interrupt
  - hydration of historical `init.messages`
- Keep the change explainable and small by reusing existing runtime events instead of adding a parallel browser-only protocol.

## Steps

1. Add failing tests for active-task interruption in the WebUI server.
2. Track the currently running WebUI agent task and cancel it when an `interrupt` message arrives.
3. Surface cancellation through the existing `error` and `agent_end` flow so the browser clears streaming state without losing raw state visibility.
4. Hydrate `init.messages` into the frontend chat store and expose a browser interrupt action.
5. Add a visible interrupt control to the chat surface while streaming is active.
6. Run focused backend verification plus a frontend build check, then update `specs/features/webui-chat.md` to match the shipped behavior.
