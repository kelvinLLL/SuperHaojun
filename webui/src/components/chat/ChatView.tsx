import { useRef, useEffect } from "react";
import { useChatStore, usePanelStore } from "@/stores";
import { MessageCard } from "./MessageCard";
import { ToolCallCard } from "./ToolCallCard";
import { StreamingCard } from "./StreamingCard";
import { ChatInput } from "./ChatInput";
import { PermissionModal } from "../shared/PermissionModal";
import { Sparkles, Bot } from "lucide-react";

const SUGGESTIONS = [
  { label: "Explain this code", emoji: "💡" },
  { label: "Fix a bug", emoji: "🔧" },
  { label: "Write tests", emoji: "🧪" },
  { label: "Refactor", emoji: "✨" },
];

interface ChatViewProps {
  onSend: (text: string) => void;
  onPermission: (toolCallId: string, granted: boolean) => void;
}

export function ChatView({ onSend, onPermission }: ChatViewProps) {
  const { messages, streamingText, isStreaming, toolCalls, permissionRequest } = useChatStore();
  const models = usePanelStore((s) => s.models);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText, toolCalls]);

  const isEmpty = messages.length === 0 && !isStreaming;
  const activeModel = models.find((m) => m.active);

  return (
    <div className="flex flex-col h-full relative">
      {/* Message area */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-6">
          {isEmpty && (
            <div className="flex flex-col items-center justify-center min-h-[60vh] gap-5 animate-fade-in select-none">
              <div
                className="w-14 h-14 rounded-2xl flex items-center justify-center"
                style={{
                  background: "linear-gradient(135deg, var(--accent-blue), var(--accent-magenta))",
                  boxShadow: "0 0 40px rgba(122,162,247,0.2)",
                }}
              >
                <Sparkles size={24} color="#fff" />
              </div>
              <div className="text-center">
                <h2
                  className="text-2xl font-bold mb-1.5"
                  style={{
                    background: "linear-gradient(135deg, var(--accent-blue), var(--accent-magenta))",
                    WebkitBackgroundClip: "text",
                    WebkitTextFillColor: "transparent",
                    letterSpacing: "-0.03em",
                  }}
                >
                  What can I help with?
                </h2>
                {activeModel && (
                  <div
                    className="inline-flex items-center gap-1.5 mt-2 px-3 py-1 rounded-full text-[11px]"
                    style={{
                      background: "var(--bg-elevated)",
                      color: "var(--text-dim)",
                      border: "1px solid var(--border-subtle)",
                    }}
                  >
                    <Bot size={10} />
                    {activeModel.name}
                  </div>
                )}
              </div>
              <div className="flex flex-wrap justify-center gap-2 mt-3">
                {SUGGESTIONS.map(({ label, emoji }) => (
                  <button
                    key={label}
                    onClick={() => onSend(label)}
                    className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-medium transition-all duration-200 hover:scale-[1.02]"
                    style={{
                      background: "var(--bg-surface)",
                      color: "var(--text-secondary)",
                      border: "1px solid var(--border-subtle)",
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = "var(--accent-blue)";
                      e.currentTarget.style.background = "var(--bg-elevated)";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = "var(--border-subtle)";
                      e.currentTarget.style.background = "var(--bg-surface)";
                    }}
                  >
                    <span>{emoji}</span>
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {!isEmpty && (
            <div className="space-y-0">
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

              {/* Thinking indicator */}
              {isStreaming && !streamingText && Object.keys(toolCalls).length === 0 && (
                <div className="flex items-start gap-2.5 py-4 animate-fade-in">
                  <div
                    className="w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-1"
                    style={{
                      background: "linear-gradient(135deg, var(--accent-cyan), var(--accent-teal))",
                    }}
                  >
                    <Sparkles size={12} color="#fff" />
                  </div>
                  <div className="flex items-center gap-1.5 pt-1.5">
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                  </div>
                </div>
              )}

              <div ref={bottomRef} />
            </div>
          )}
        </div>
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
