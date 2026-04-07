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
    <div
      className="rounded-lg overflow-hidden animate-slide-in"
      style={{
        background: "var(--bg-secondary)",
        border: `1px solid ${toolCall.done ? "var(--border)" : "var(--accent-yellow)"}`,
      }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left transition-colors"
        style={{ background: "transparent" }}
      >
        {toolCall.done ? (
          <Check size={14} style={{ color: "var(--accent-green)" }} />
        ) : (
          <Loader size={14} className="animate-spin" style={{ color: "var(--accent-yellow)" }} />
        )}
        <Wrench size={12} style={{ color: "var(--text-dim)" }} />
        <span className="text-xs font-medium" style={{ color: "var(--text-primary)" }}>
          {toolCall.tool_name}
        </span>
        <span className="text-[10px] ml-auto" style={{ color: "var(--text-dim)" }}>
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </span>
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-2">
          <div>
            <div className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "var(--text-dim)" }}>
              Arguments
            </div>
            <pre className="text-[11px] p-2 rounded overflow-x-auto" style={{ background: "var(--bg-primary)" }}>
              {JSON.stringify(toolCall.arguments, null, 2)}
            </pre>
          </div>
          {toolCall.result !== undefined && (
            <div>
              <div className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "var(--text-dim)" }}>
                Result
              </div>
              <pre
                className="text-[11px] p-2 rounded overflow-x-auto max-h-60 overflow-y-auto"
                style={{
                  background: "var(--bg-primary)",
                  color: "var(--text-secondary)",
                }}
              >
                {toolCall.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
