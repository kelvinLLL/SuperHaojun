import { useState } from "react";
import { Wrench, ChevronDown, ChevronRight, Check, Loader } from "lucide-react";

interface ToolCallCardProps {
  toolCall: {
    tool_call_id: string;
    tool_name: string;
    arguments: Record<string, any>;
    result?: string;
    done: boolean;
  };
}

export function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="ml-8 animate-slide-up">
      <div
        className="rounded-lg overflow-hidden"
        style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border-subtle)",
        }}
      >
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center gap-2 px-3 py-2 text-left transition-colors duration-150"
          style={{ background: "transparent" }}
          onMouseEnter={(e) => { e.currentTarget.style.background = "var(--bg-hover)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
        >
          {toolCall.done ? (
            <Check size={11} style={{ color: "var(--accent-green)" }} />
          ) : (
            <Loader size={11} className="animate-spin" style={{ color: "var(--accent-cyan)" }} />
          )}
          <Wrench size={10} style={{ color: "var(--text-dim)" }} />
          <span className="text-[11px] font-mono font-medium" style={{ color: "var(--text-primary)" }}>
            {toolCall.tool_name}
          </span>
          <span className="ml-auto">
            {expanded ? (
              <ChevronDown size={11} style={{ color: "var(--text-dim)" }} />
            ) : (
              <ChevronRight size={11} style={{ color: "var(--text-dim)" }} />
            )}
          </span>
        </button>

        {expanded && (
          <div className="px-3 pb-2.5 space-y-2 animate-fade-in">
            <div>
              <div
                className="text-[10px] uppercase tracking-widest mb-1 font-medium"
                style={{ color: "var(--text-dim)" }}
              >
                Arguments
              </div>
              <pre
                className="text-[11px] p-2.5 rounded-md overflow-x-auto font-mono"
                style={{ background: "var(--bg-secondary)", color: "var(--text-secondary)", border: "none", margin: 0 }}
              >
                {JSON.stringify(toolCall.arguments, null, 2)}
              </pre>
            </div>
            {toolCall.result !== undefined && (
              <div>
                <div
                  className="text-[10px] uppercase tracking-widest mb-1 font-medium"
                  style={{ color: "var(--text-dim)" }}
                >
                  Result
                </div>
                <pre
                  className="text-[11px] p-2.5 rounded-md overflow-x-auto max-h-40 overflow-y-auto font-mono"
                  style={{ background: "var(--bg-secondary)", color: "var(--text-secondary)", border: "none", margin: 0 }}
                >
                  {toolCall.result}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
