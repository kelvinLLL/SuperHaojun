import { useChatStore, usePanelStore } from "@/stores";
import { Activity, Cpu, Zap, FileWarning, Eye, Wrench } from "lucide-react";

export function Sidebar() {
  const { sidebarOpen } = usePanelStore();
  const { tokenUsage, tools, toolCalls, isStreaming } = useChatStore();

  if (!sidebarOpen) return null;

  const pct = tokenUsage.max_tokens > 0
    ? Math.round((tokenUsage.estimated_tokens / tokenUsage.max_tokens) * 100)
    : 0;

  const activeToolCalls = Object.values(toolCalls).filter((t) => !t.done);

  return (
    <aside
      className="w-64 shrink-0 border-l overflow-y-auto"
      style={{ borderColor: "var(--border)", background: "var(--bg-secondary)" }}
    >
      {/* Token Usage */}
      <section className="p-3 border-b" style={{ borderColor: "var(--border)" }}>
        <h3
          className="text-[11px] uppercase tracking-wider mb-2 flex items-center gap-1.5"
          style={{ color: "var(--text-dim)" }}
        >
          <Cpu size={12} /> Context Window
        </h3>
        <div className="mb-1">
          <div className="flex justify-between text-[11px] mb-1">
            <span style={{ color: "var(--text-secondary)" }}>
              {tokenUsage.estimated_tokens.toLocaleString()} tokens
            </span>
            <span style={{ color: pct > 80 ? "var(--accent-red)" : "var(--text-dim)" }}>
              {pct}%
            </span>
          </div>
          <div
            className="h-1.5 rounded-full overflow-hidden"
            style={{ background: "var(--bg-primary)" }}
          >
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${Math.min(pct, 100)}%`,
                background:
                  pct > 80 ? "var(--accent-red)" :
                  pct > 60 ? "var(--accent-yellow)" :
                  "var(--accent-blue)",
              }}
            />
          </div>
        </div>
        <div className="flex justify-between text-[10px]" style={{ color: "var(--text-dim)" }}>
          <span>{tokenUsage.message_count} msgs</span>
          <span>{tokenUsage.compaction_count} compactions</span>
        </div>
      </section>

      {/* Status */}
      <section className="p-3 border-b" style={{ borderColor: "var(--border)" }}>
        <h3
          className="text-[11px] uppercase tracking-wider mb-2 flex items-center gap-1.5"
          style={{ color: "var(--text-dim)" }}
        >
          <Activity size={12} /> Status
        </h3>
        <div className="flex items-center gap-2 text-xs">
          <span
            className="status-dot"
            style={{
              background: isStreaming ? "var(--accent-green)" : "var(--text-dim)",
            }}
          />
          <span style={{ color: "var(--text-secondary)" }}>
            {isStreaming ? "Generating..." : "Idle"}
          </span>
        </div>
        {activeToolCalls.length > 0 && (
          <div className="mt-2 space-y-1">
            {activeToolCalls.map((tc) => (
              <div
                key={tc.tool_call_id}
                className="flex items-center gap-1.5 text-[11px] animate-pulse-glow"
                style={{ color: "var(--accent-yellow)" }}
              >
                <Zap size={10} /> {tc.tool_name}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Tools */}
      <section className="p-3 border-b" style={{ borderColor: "var(--border)" }}>
        <h3
          className="text-[11px] uppercase tracking-wider mb-2 flex items-center gap-1.5"
          style={{ color: "var(--text-dim)" }}
        >
          <Wrench size={12} /> Tools ({tools.length})
        </h3>
        <div className="space-y-0.5 max-h-40 overflow-y-auto">
          {tools.map((t) => (
            <div
              key={t.name}
              className="text-[11px] py-0.5 px-1 rounded truncate"
              style={{ color: "var(--text-secondary)" }}
              title={t.description}
            >
              {t.name}
            </div>
          ))}
        </div>
      </section>

      {/* Keyboard shortcuts */}
      <section className="p-3">
        <h3
          className="text-[11px] uppercase tracking-wider mb-2 flex items-center gap-1.5"
          style={{ color: "var(--text-dim)" }}
        >
          <Eye size={12} /> Shortcuts
        </h3>
        <div className="space-y-1 text-[10px]" style={{ color: "var(--text-dim)" }}>
          <div><kbd className="px-1 rounded" style={{ background: "var(--bg-surface)" }}>⌘ Enter</kbd> Send</div>
          <div><kbd className="px-1 rounded" style={{ background: "var(--bg-surface)" }}>Esc</kbd> Interrupt</div>
        </div>
      </section>
    </aside>
  );
}
