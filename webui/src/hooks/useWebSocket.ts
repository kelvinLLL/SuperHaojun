import { useEffect, useRef, useCallback } from "react";
import { useChatStore, usePanelStore } from "@/stores";
import type { WSMessage } from "@/types";

let ws: WebSocket | null = null;

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
        useChatStore.getState().setTools(msg.tools);
        useChatStore.getState().setTokenUsage(msg.token_usage);
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
        console.error("[Agent Error]", msg.message);
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
          isStreaming: false,
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

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      ws?.close();
    };
  }, [connect]);

  return { sendMessage, respondPermission, send };
}
