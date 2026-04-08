import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessageData } from "@/types";
import { User, Sparkles, Terminal, AlertTriangle } from "lucide-react";

interface MessageCardProps {
  message: ChatMessageData;
}

export function MessageCard({ message }: MessageCardProps) {
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";
  const isTool = message.role === "tool";
  const isSystem = message.role === "system";

  return (
    <div className="animate-slide-up" style={{ paddingTop: isUser ? 16 : 4, paddingBottom: 4 }}>
      {/* User messages */}
      {isUser && (
        <div className="flex items-start gap-3">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5"
            style={{ background: "var(--accent-blue)", opacity: 0.9 }}
          >
            <User size={14} color="#fff" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
                You
              </span>
              <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>
                {new Date(message.timestamp).toLocaleTimeString()}
              </span>
            </div>
            <p
              className="text-sm leading-relaxed"
              style={{ color: "var(--text-primary)", whiteSpace: "pre-wrap" }}
            >
              {message.content}
            </p>
          </div>
        </div>
      )}

      {/* Assistant messages */}
      {isAssistant && (
        <div className="flex items-start gap-3">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5"
            style={{
              background: "linear-gradient(135deg, var(--accent-cyan), var(--accent-teal))",
            }}
          >
            <Sparkles size={14} color="#fff" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
                SuperHaojun
              </span>
              <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>
                {new Date(message.timestamp).toLocaleTimeString()}
              </span>
            </div>
            {message.content && (
              <div className="markdown-body text-sm">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {message.content}
                </ReactMarkdown>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tool result messages */}
      {isTool && (
        <div className="ml-10">
          <div
            className="rounded-xl px-4 py-3 text-xs"
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border-subtle)",
            }}
          >
            <div className="flex items-center gap-1.5 mb-1.5">
              <Terminal size={11} style={{ color: "var(--accent-green)" }} />
              <span className="font-medium" style={{ color: "var(--accent-green)" }}>
                {message.name || "tool"}
              </span>
            </div>
            <pre
              className="text-[12px] font-mono whitespace-pre-wrap break-all"
              style={{
                color: "var(--text-dim)",
                background: "transparent",
                border: "none",
                padding: 0,
                margin: 0,
                maxHeight: 200,
                overflow: "auto",
              }}
            >
              {message.content}
            </pre>
          </div>
        </div>
      )}

      {/* System messages */}
      {isSystem && (
        <div className="flex items-center justify-center py-2">
          <div
            className="flex items-center gap-2 px-4 py-1.5 rounded-full text-[11px]"
            style={{
              background: "rgba(224, 175, 104, 0.08)",
              color: "var(--accent-yellow)",
            }}
          >
            <AlertTriangle size={12} />
            {message.content}
          </div>
        </div>
      )}
    </div>
  );
}
