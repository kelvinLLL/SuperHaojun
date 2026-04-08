import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Sparkles } from "lucide-react";

interface StreamingCardProps {
  text: string;
}

export function StreamingCard({ text }: StreamingCardProps) {
  return (
    <div className="flex items-start gap-3 py-1">
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
          <span
            className="w-1.5 h-1.5 rounded-full animate-pulse-glow"
            style={{ background: "var(--accent-cyan)" }}
          />
        </div>
        <div className="markdown-body text-sm">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
