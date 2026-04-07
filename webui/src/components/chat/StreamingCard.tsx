import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot } from "lucide-react";

interface StreamingCardProps {
  text: string;
}

export function StreamingCard({ text }: StreamingCardProps) {
  return (
    <div
      className="rounded-lg px-4 py-3"
      style={{
        background: "var(--bg-surface)",
        borderLeft: "3px solid var(--accent-cyan)",
      }}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <Bot size={14} style={{ color: "var(--accent-cyan)" }} />
        <span
          className="text-[11px] font-semibold uppercase tracking-wider"
          style={{ color: "var(--accent-cyan)" }}
        >
          Agent
        </span>
        <span
          className="w-1.5 h-1.5 rounded-full animate-pulse-glow ml-2"
          style={{ background: "var(--accent-cyan)" }}
        />
      </div>
      <div className="markdown-body text-sm" style={{ color: "var(--text-secondary)" }}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      </div>
    </div>
  );
}
