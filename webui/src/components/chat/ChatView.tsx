import { useRef, useEffect } from "react";
import { useChatStore } from "@/stores";
import { MessageCard } from "./MessageCard";
import { ToolCallCard } from "./ToolCallCard";
import { StreamingCard } from "./StreamingCard";
import { ChatInput } from "./ChatInput";
import { PermissionModal } from "../shared/PermissionModal";

interface ChatViewProps {
  onSend: (text: string) => void;
  onPermission: (toolCallId: string, granted: boolean) => void;
}

export function ChatView({ onSend, onPermission }: ChatViewProps) {
  const { messages, streamingText, isStreaming, toolCalls, permissionRequest } = useChatStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText, toolCalls]);

  return (
    <div className="flex flex-col h-full">
      {/* Message area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.length === 0 && !isStreaming && (
          <div className="flex flex-col items-center justify-center h-full gap-4">
            <div className="text-4xl">⚡</div>
            <h2 className="text-lg font-semibold" style={{ color: "var(--accent-cyan)" }}>
              SuperHaojun
            </h2>
            <p className="text-sm" style={{ color: "var(--text-dim)" }}>
              AI-powered coding assistant. Type a message to start.
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <MessageCard key={msg.id} message={msg} />
        ))}

        {/* Active tool calls */}
        {Object.values(toolCalls).map((tc) => (
          <ToolCallCard key={tc.tool_call_id} toolCall={tc} />
        ))}

        {/* Streaming text */}
        {isStreaming && streamingText && (
          <StreamingCard text={streamingText} />
        )}

        {/* Streaming indicator (no text yet) */}
        {isStreaming && !streamingText && Object.keys(toolCalls).length === 0 && (
          <div
            className="flex items-center gap-2 px-4 py-3 rounded-lg animate-pulse-glow"
            style={{ background: "var(--bg-surface)" }}
          >
            <div
              className="w-2 h-2 rounded-full"
              style={{ background: "var(--accent-cyan)" }}
            />
            <span className="text-xs" style={{ color: "var(--text-dim)" }}>
              Thinking...
            </span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <ChatInput onSend={onSend} disabled={isStreaming} />

      {/* Permission modal */}
      {permissionRequest && (
        <PermissionModal
          request={permissionRequest}
          onRespond={onPermission}
        />
      )}
    </div>
  );
}
