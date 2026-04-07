import { useState, useEffect } from "react";
import { Search, Filter, Eye, Code } from "lucide-react";

interface RawMessage {
  role: string;
  content: string | null;
  tool_calls?: any[];
  tool_call_id?: string;
  name?: string;
}

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

  const ROLE_COLORS: Record<string, string> = {
    user: "var(--accent-blue)",
    assistant: "var(--accent-cyan)",
    tool: "var(--accent-green)",
    system: "var(--accent-yellow)",
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header / Filter */}
      <div
        className="flex items-center gap-3 px-4 py-3 border-b shrink-0"
        style={{ borderColor: "var(--border)", background: "var(--bg-secondary)" }}
      >
        <Filter size={14} style={{ color: "var(--text-dim)" }} />
        {["all", "user", "assistant", "tool", "system"].map((r) => (
          <button
            key={r}
            onClick={() => setFilter(r)}
            className="text-[11px] px-2 py-0.5 rounded transition-colors"
            style={{
              background: filter === r ? "var(--bg-active)" : "transparent",
              color: filter === r ? "var(--text-primary)" : "var(--text-dim)",
            }}
          >
            {r}
          </button>
        ))}
        <span className="ml-auto text-[11px]" style={{ color: "var(--text-dim)" }}>
          {filtered.length} / {messages.length} messages
        </span>
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto">
        {filtered.map((msg, idx) => (
          <div
            key={idx}
            className="border-b px-4 py-2 cursor-pointer transition-colors"
            style={{
              borderColor: "var(--border)",
              background: expandedIdx === idx ? "var(--bg-surface)" : "transparent",
            }}
            onClick={() => setExpandedIdx(expandedIdx === idx ? null : idx)}
          >
            <div className="flex items-center gap-2">
              <span
                className="text-[10px] font-bold uppercase w-16"
                style={{ color: ROLE_COLORS[msg.role] || "var(--text-dim)" }}
              >
                {msg.role}
              </span>
              {msg.name && (
                <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>
                  [{msg.name}]
                </span>
              )}
              <span
                className="text-xs truncate flex-1"
                style={{ color: "var(--text-secondary)" }}
              >
                {msg.content?.slice(0, 100) || (msg.tool_calls ? `[${msg.tool_calls.length} tool calls]` : "—")}
              </span>
              <Code size={12} style={{ color: "var(--text-dim)" }} />
            </div>

            {expandedIdx === idx && (
              <pre
                className="mt-2 p-3 rounded text-[11px] overflow-auto max-h-80"
                style={{
                  background: "var(--bg-primary)",
                  color: "var(--text-secondary)",
                }}
              >
                {JSON.stringify(msg, null, 2)}
              </pre>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
