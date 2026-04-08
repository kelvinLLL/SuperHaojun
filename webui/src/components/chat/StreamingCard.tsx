import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Sparkles } from "lucide-react";

interface StreamingCardProps {
  text: string;
}

export function StreamingCard({ text }: StreamingCardProps) {
  return (
    <div className="flex items-start gap-2.5 max-w-[85%] py-1">
      <div
        className="w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-1"
        style={{
          background: "linear-gradient(135deg, var(--accent-cyan), var(--accent-teal))",
        }}
      >
        <Sparkles size={12} color="#fff" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="markdown-body text-sm">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        </div>
        <span
          className="inline-block w-1.5 h-4 rounded-sm ml-0.5 animate-pulse-glow"
          style={{ background: "var(--accent-cyan)", verticalAlign: "text-bottom" }}
        />
      </div>
    </div>
  );
}
