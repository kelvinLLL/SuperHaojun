import { useEffect, useRef, useCallback } from "react";
import { useChatStore, usePanelStore } from "@/stores";
import type { ChatMessageData, RuntimeState, ServerChatMessage, TokenUsage, WSMessage } from "@/types";

let ws: WebSocket | null = null;
const EXPECTED_AGENT_TERMINAL_MESSAGES = new Set(["Interrupted by user."]);

function fetchModels() {
  fetch("/api/config/models")
    .then((r) => r.json())
    .then((models) => usePanelStore.getState().setModels(models))
    .catch(() => {});
}

function fetchCommands() {
  fetch("/api/commands")
    .then((r) => r.json())
    .then((cmds) => usePanelStore.getState().setCommands(cmds))
    .catch(() => {});
}

function fetchExtensions() {
  fetch("/api/extensions")
    .then((r) => r.json())
    .then((extensions) => usePanelStore.getState().setExtensions(extensions))
    .catch(() => {});
}

function toTokenUsage(runtime: RuntimeState): TokenUsage {
  return {
    message_count: runtime.message_count,
    estimated_tokens: runtime.estimated_tokens,
    max_tokens: 128000,
    compaction_count: runtime.compaction_count,
    context_metrics: runtime.prompt_context_metrics,
    provider_usage: runtime.provider_usage,
  };
}

function normalizeMessages(messages: ServerChatMessage[]): ChatMessageData[] {
  return messages.map((message, index) => ({
    id: `init-${index}-${crypto.randomUUID()}`,
    ...message,
  }));
}

export function useWebSocket() {
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const connect = useCallback(() => {
    if (ws?.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.host}/api/ws`;
    ws = new WebSocket(url);

    ws.onopen = () => {
      console.log("[WS] Connected");
      fetchModels();
      fetchCommands();
      fetchExtensions();
    };

    ws.onmessage = (event) => {
      const msg: WSMessage = JSON.parse(event.data);
      handleMessage(msg);
    };

    ws.onclose = () => {
      console.log("[WS] Disconnected, reconnecting in 2s...");
      reconnectTimer.current = setTimeout(connect, 2000);
    };

    ws.onerror = (err) => {
      console.error("[WS] Error:", err);
    };
  }, []);

  const handleMessage = (msg: WSMessage) => {
    switch (msg.type) {
      case "init":
        useChatStore.setState({
          messages: normalizeMessages(msg.messages),
          streamingText: "",
          isStreaming: false,
          toolCalls: {},
          permissionRequest: null,
          tools: msg.tools,
          tokenUsage: msg.token_usage ?? toTokenUsage(msg.runtime),
        });
        usePanelStore.getState().setExtensions(msg.runtime.extensions ?? []);
        break;

      case "runtime_state":
        useChatStore.getState().setTokenUsage(toTokenUsage(msg.runtime));
        usePanelStore.getState().setExtensions(msg.runtime.extensions ?? []);
        break;

      case "agent_start":
        useChatStore.getState().startStreaming();
        break;

      case "text_delta":
        useChatStore.getState().appendDelta(msg.text);
        break;

      case "tool_call_start":
        useChatStore.getState().startToolCall({
          tool_call_id: msg.tool_call_id,
          tool_name: msg.tool_name,
          arguments: msg.arguments,
        });
        break;

      case "tool_call_end":
        useChatStore.getState().endToolCall(msg.tool_call_id, msg.result);
        break;

      case "permission_request":
        useChatStore.getState().setPermission({
          tool_call_id: msg.tool_call_id,
          tool_name: msg.tool_name,
          arguments: msg.arguments,
          risk_level: msg.risk_level,
        });
        break;

      case "agent_end":
        useChatStore.getState().endStreaming();
        break;

      case "model_changed":
        usePanelStore.getState().setActiveModel(msg.key, {
          model_id: msg.model_id,
          provider: msg.provider,
          base_url: msg.base_url,
        });
        // Refresh models list after switch
        fetchModels();
        break;

      case "command_response":
        // Show command output as a system message in chat
        useChatStore.setState((s) => ({
          messages: [
            ...s.messages,
            {
              id: crypto.randomUUID(),
              role: "system" as const,
              name: "command",
              content: `/${msg.command}\n${msg.output}`,
              timestamp: Date.now(),
            },
          ],
        }));
        break;

      case "error":
        if (EXPECTED_AGENT_TERMINAL_MESSAGES.has(msg.message)) {
          console.info("[Agent Status]", msg.message);
        } else {
          console.error("[Agent Error]", msg.message);
        }
        // Add error as system message
        useChatStore.setState((s) => ({
          messages: [
            ...s.messages,
            {
              id: crypto.randomUUID(),
              role: "system",
              name: "error",
              content: msg.message,
              timestamp: Date.now(),
            },
          ],
          permissionRequest: null,
        }));
        break;
    }
  };

  const send = useCallback((data: Record<string, any>) => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data));
    }
  }, []);

  const sendMessage = useCallback((text: string) => {
    useChatStore.getState().addUserMessage(text);
    send({ type: "user_message", text });
  }, [send]);

  const respondPermission = useCallback((toolCallId: string, granted: boolean) => {
    send({ type: "permission_response", tool_call_id: toolCallId, granted });
    useChatStore.getState().setPermission(null);
  }, [send]);

  const interrupt = useCallback(() => {
    send({ type: "interrupt" });
  }, [send]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      ws?.close();
    };
  }, [connect]);

  return { sendMessage, respondPermission, interrupt, send };
}
