import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessageData } from "@/types";
import { User, Bot, Terminal, AlertCircle } from "lucide-react";

interface MessageCardProps {
  message: ChatMessageData;
}

const ROLE_CONFIG = {
  user: {
    icon: User,
    label: "You",
    borderColor: "var(--accent-blue)",
    bgColor: "var(--bg-surface)",
  },
  assistant: {
    icon: Bot,
    label: "Agent",
    borderColor: "var(--accent-cyan)",
    bgColor: "var(--bg-surface)",
  },
  tool: {
    icon: Terminal,
    label: "Tool",
    borderColor: "var(--accent-green)",
    bgColor: "var(--bg-secondary)",
  },
  system: {
    icon: AlertCircle,
    label: "System",
    borderColor: "var(--accent-yellow)",
    bgColor: "var(--bg-secondary)",
  },
} as const;

export function MessageCard({ message }: MessageCardProps) {
  const cfg = ROLE_CONFIG[message.role] || ROLE_CONFIG.system;
  const Icon = cfg.icon;

  return (
    <div
      className="rounded-lg px-4 py-3 animate-slide-in"
      style={{
        background: cfg.bgColor,
        borderLeft: `3px solid ${cfg.borderColor}`,
      }}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <Icon size={14} style={{ color: cfg.borderColor }} />
        <span
          className="text-[11px] font-semibold uppercase tracking-wider"
          style={{ color: cfg.borderColor }}
        >
          {message.name || cfg.label}
        </span>
        <span className="text-[10px] ml-auto" style={{ color: "var(--text-dim)" }}>
          {new Date(message.timestamp).toLocaleTimeString()}
        </span>
      </div>

      {message.content && (
        <div className="markdown-body text-sm" style={{ color: "var(--text-secondary)" }}>
          {message.role === "user" ? (
            <p style={{ whiteSpace: "pre-wrap" }}>{message.content}</p>
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          )}
        </div>
      )}
    </div>
  );
}
