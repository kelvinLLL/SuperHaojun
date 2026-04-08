import { useState, useEffect } from "react";
import { Filter, ChevronDown, ChevronRight } from "lucide-react";

interface RawMessage {
  role: string;
  content: string | null;
  tool_calls?: any[];
  tool_call_id?: string;
  name?: string;
}

const ROLE_COLORS: Record<string, { color: string; bg: string }> = {
  user: { color: "var(--accent-blue)", bg: "rgba(122, 162, 247, 0.1)" },
  assistant: { color: "var(--accent-cyan)", bg: "rgba(125, 207, 255, 0.1)" },
  tool: { color: "var(--accent-green)", bg: "rgba(158, 206, 106, 0.1)" },
  system: { color: "var(--accent-yellow)", bg: "rgba(224, 175, 104, 0.1)" },
};

export function MessagesView() {
  const [messages, setMessages] = useState<RawMessage[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  useEffect(() => {
    fetch("/api/messages")
      .then((r) => r.json())
      .then(setMessages)
      .catch(console.error);
    const iv = setInterval(() => {
      fetch("/api/messages")
        .then((r) => r.json())
        .then(setMessages)
        .catch(() => {});
    }, 3000);
    return () => clearInterval(iv);
  }, []);

  const filtered = filter === "all" ? messages : messages.filter((m) => m.role === filter);
  const filters = ["all", "user", "assistant", "tool", "system"];

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div
        className="flex items-center gap-2 px-5 py-3 shrink-0"
        style={{ borderBottom: "1px solid var(--border-subtle)", background: "var(--bg-secondary)" }}
      >
        <Filter size={13} style={{ color: "var(--text-dim)" }} />
        <div className="flex gap-1">
          {filters.map((r) => (
            <button
              key={r}
              onClick={() => setFilter(r)}
              className="text-[11px] px-3 py-1 rounded-lg font-medium transition-all duration-200"
              style={{
                background: filter === r ? "var(--bg-elevated)" : "transparent",
                color: filter === r ? "var(--text-primary)" : "var(--text-dim)",
                boxShadow: filter === r ? "var(--shadow-sm)" : "none",
              }}
            >
              {r}
            </button>
          ))}
        </div>
        <span
          className="ml-auto text-[11px] px-2 py-0.5 rounded-full font-medium"
          style={{ background: "var(--bg-elevated)", color: "var(--text-dim)" }}
        >
          {filtered.length} / {messages.length}
        </span>
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-5 py-3">
        <div className="space-y-1.5">
          {filtered.map((msg, idx) => {
            const rc = ROLE_COLORS[msg.role] || ROLE_COLORS.system;
            const isExpanded = expandedIdx === idx;

            return (
              <div
                key={idx}
                className="rounded-xl overflow-hidden transition-all duration-200 cursor-pointer"
                style={{
                  background: isExpanded ? "var(--bg-surface)" : "transparent",
                  border: isExpanded ? "1px solid var(--border)" : "1px solid transparent",
                }}
                onClick={() => setExpandedIdx(isExpanded ? null : idx)}
              >
                <div className="flex items-center gap-3 px-4 py-2.5">
                  <span
                    className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-md shrink-0"
                    style={{ color: rc.color, background: rc.bg }}
                  >
                    {msg.role}
                  </span>
                  {msg.name && (
                    <span className="text-[11px] font-mono" style={{ color: "var(--text-dim)" }}>
                      {msg.name}
                    </span>
                  )}
                  <span
                    className="text-xs truncate flex-1"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    {msg.content?.slice(0, 120) || (msg.tool_calls ? `${msg.tool_calls.length} tool calls` : "—")}
                  </span>
                  {isExpanded ? (
                    <ChevronDown size={12} style={{ color: "var(--text-dim)" }} />
                  ) : (
                    <ChevronRight size={12} style={{ color: "var(--text-dim)" }} />
                  )}
                </div>

                {isExpanded && (
                  <div className="px-4 pb-3 animate-fade-in">
                    <pre
                      className="text-[12px] p-3 rounded-lg overflow-auto max-h-80 font-mono"
                      style={{
                        background: "var(--bg-secondary)",
                        color: "var(--text-secondary)",
                        border: "none",
                        margin: 0,
                      }}
                    >
                      {JSON.stringify(msg, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
