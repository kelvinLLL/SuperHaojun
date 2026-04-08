import { useRef, useEffect } from "react";
import { useChatStore } from "@/stores";
import { MessageCard } from "./MessageCard";
import { ToolCallCard } from "./ToolCallCard";
import { StreamingCard } from "./StreamingCard";
import { ChatInput } from "./ChatInput";
import { PermissionModal } from "../shared/PermissionModal";
import { Sparkles } from "lucide-react";

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

  const isEmpty = messages.length === 0 && !isStreaming;

  return (
    <div className="flex flex-col h-full relative">
      {/* Message area */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-6">
          {isEmpty && (
            <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 animate-fade-in">
              <div
                className="w-16 h-16 rounded-2xl flex items-center justify-center"
                style={{
                  background: "linear-gradient(135deg, var(--accent-blue), var(--accent-magenta))",
                  boxShadow: "var(--shadow-glow-blue)",
                }}
              >
                <Sparkles size={28} color="#fff" />
              </div>
              <div className="text-center">
                <h2
                  className="text-xl font-semibold mb-2"
                  style={{ color: "var(--text-primary)", letterSpacing: "-0.02em" }}
                >
                  SuperHaojun
                </h2>
                <p
                  className="text-sm max-w-md"
                  style={{ color: "var(--text-dim)", lineHeight: 1.7 }}
                >
                  AI-powered coding assistant. Ask me anything about code,
                  architecture, debugging, or let me help build your project.
                </p>
              </div>
              <div className="flex gap-2 mt-2">
                {["Explain this code", "Fix a bug", "Write tests"].map((text) => (
                  <button
                    key={text}
                    onClick={() => onSend(text)}
                    className="px-4 py-2 rounded-xl text-xs font-medium btn-hover"
                    style={{
                      background: "var(--bg-elevated)",
                      color: "var(--text-secondary)",
                      border: "1px solid var(--border)",
                    }}
                  >
                    {text}
                  </button>
                ))}
              </div>
            </div>
          )}

          {!isEmpty && (
            <div className="space-y-1">
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
                <div className="flex items-start gap-3 py-4 animate-fade-in">
                  <div
                    className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5"
                    style={{
                      background: "linear-gradient(135deg, var(--accent-cyan), var(--accent-teal))",
                    }}
                  >
                    <Sparkles size={14} color="#fff" />
                  </div>
                  <div className="flex items-center gap-1.5 pt-2">
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
