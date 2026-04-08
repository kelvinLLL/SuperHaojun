import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessageData } from "@/types";
import { Sparkles, Terminal, AlertCircle, ChevronRight, TerminalSquare } from "lucide-react";

interface MessageCardProps {
  message: ChatMessageData;
}

export function MessageCard({ message }: MessageCardProps) {
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";
  const isTool = message.role === "tool";
  const isSystem = message.role === "system";

  const time = new Date(message.timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="animate-slide-up" style={{ marginTop: isUser ? 20 : 6, marginBottom: 2 }}>
      {/* ── User bubble (right-aligned) ── */}
      {isUser && (
        <div className="flex justify-end">
          <div className="max-w-[75%]">
            <div
              className="rounded-2xl rounded-br-md px-4 py-2.5 text-sm leading-relaxed"
              style={{
                background: "linear-gradient(135deg, rgba(122,162,247,0.22), rgba(125,207,255,0.13))",
                border: "1px solid rgba(122,162,247,0.18)",
                color: "var(--text-primary)",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {message.content}
            </div>
            <div
              className="text-[10px] text-right mt-1 mr-1"
              style={{ color: "var(--text-dim)" }}
            >
              {time}
            </div>
          </div>
        </div>
      )}

      {/* ── Assistant message (left-aligned, no bubble) ── */}
      {isAssistant && (
        <div className="flex items-start gap-2.5 max-w-[85%]">
          <div
            className="w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-1"
            style={{
              background: "linear-gradient(135deg, var(--accent-cyan), var(--accent-teal))",
            }}
          >
            <Sparkles size={12} color="#fff" />
          </div>
          <div className="flex-1 min-w-0">
            {message.content && (
              <div className="markdown-body text-sm">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {message.content}
                </ReactMarkdown>
              </div>
            )}
            <div className="text-[10px] mt-1" style={{ color: "var(--text-dim)" }}>
              {time}
            </div>
          </div>
        </div>
      )}

      {/* ── Tool result (compact inline) ── */}
      {isTool && (
        <div className="ml-8">
          <div
            className="rounded-lg px-3 py-2 text-xs"
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border-subtle)",
            }}
          >
            <div className="flex items-center gap-1.5">
              <Terminal size={10} style={{ color: "var(--accent-green)" }} />
              <span className="font-mono font-medium text-[11px]" style={{ color: "var(--accent-green)" }}>
                {message.name || "tool"}
              </span>
              <ChevronRight size={10} style={{ color: "var(--text-dim)" }} />
            </div>
            <pre
              className="text-[11px] font-mono whitespace-pre-wrap break-all mt-1.5"
              style={{
                color: "var(--text-dim)",
                background: "transparent",
                border: "none",
                padding: 0,
                margin: 0,
                maxHeight: 160,
                overflow: "auto",
              }}
            >
              {message.content}
            </pre>
          </div>
        </div>
      )}

      {/* ── System message: command output or error ── */}
      {isSystem && (() => {
        const isError = message.name === "error";
        const isCommand = message.name === "command";
        const accent = isError ? "var(--accent-red, #f7768e)" : "var(--accent-magenta)";
        const bgAlpha = isError ? "rgba(247,118,142,0.06)" : "rgba(187,154,247,0.06)";
        const borderAlpha = isError ? "rgba(247,118,142,0.15)" : "rgba(187,154,247,0.12)";
        const Icon = isError ? AlertCircle : isCommand ? TerminalSquare : TerminalSquare;

        return (
          <div className="flex justify-center my-2">
            <div
              className="inline-flex items-start gap-2 rounded-xl px-4 py-2.5"
              style={{
                background: bgAlpha,
                border: `1px solid ${borderAlpha}`,
                maxWidth: "min(90%, 640px)",
              }}
            >
              <Icon
                size={13}
                className="shrink-0 mt-0.5"
                style={{ color: accent }}
              />
              <pre
                className="text-xs font-mono whitespace-pre-wrap break-words"
                style={{
                  color: "var(--text-secondary)",
                  background: "transparent",
                  border: "none",
                  padding: 0,
                  margin: 0,
                  overflowX: "auto",
                }}
              >
                {message.content}
              </pre>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
