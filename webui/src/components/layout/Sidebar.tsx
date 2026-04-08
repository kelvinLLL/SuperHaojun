import { useChatStore, usePanelStore } from "@/stores";
import { Activity, Cpu, Zap, Wrench, Command } from "lucide-react";

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
      className="w-60 shrink-0 overflow-y-auto"
      style={{
        borderLeft: "1px solid var(--border-subtle)",
        background: "var(--bg-secondary)",
      }}
    >
      {/* Token Usage */}
      <section className="p-4" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
        <h3
          className="text-[11px] uppercase tracking-widest mb-3 flex items-center gap-1.5 font-medium"
          style={{ color: "var(--text-dim)" }}
        >
          <Cpu size={11} /> Context
        </h3>
        <div className="mb-2">
          <div className="flex justify-between text-[12px] mb-1.5">
            <span style={{ color: "var(--text-secondary)" }}>
              {tokenUsage.estimated_tokens.toLocaleString()}
            </span>
            <span
              className="font-medium"
              style={{
                color: pct > 80 ? "var(--accent-red)" :
                       pct > 60 ? "var(--accent-yellow)" :
                       "var(--text-dim)",
              }}
            >
              {pct}%
            </span>
          </div>
          <div
            className="h-1 rounded-full overflow-hidden"
            style={{ background: "var(--bg-primary)" }}
          >
            <div
              className="h-full rounded-full transition-all duration-700 ease-out"
              style={{
                width: `${Math.min(pct, 100)}%`,
                background:
                  pct > 80
                    ? "linear-gradient(90deg, var(--accent-orange), var(--accent-red))"
                    : pct > 60
                    ? "linear-gradient(90deg, var(--accent-yellow), var(--accent-orange))"
                    : "linear-gradient(90deg, var(--accent-blue), var(--accent-cyan))",
              }}
            />
          </div>
        </div>
        <div className="flex justify-between text-[10px]" style={{ color: "var(--text-dim)" }}>
          <span>{tokenUsage.message_count} messages</span>
          <span>{tokenUsage.compaction_count} compacts</span>
        </div>
      </section>

      {/* Status */}
      <section className="p-4" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
        <h3
          className="text-[11px] uppercase tracking-widest mb-3 flex items-center gap-1.5 font-medium"
          style={{ color: "var(--text-dim)" }}
        >
          <Activity size={11} /> Status
        </h3>
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <span
              className="status-dot"
              style={{
                background: isStreaming ? "var(--accent-green)" : "var(--text-dim)",
              }}
            />
          </div>
          <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
            {isStreaming ? "Generating..." : "Ready"}
          </span>
        </div>
        {activeToolCalls.length > 0 && (
          <div className="mt-3 space-y-1.5">
            {activeToolCalls.map((tc) => (
              <div
                key={tc.tool_call_id}
                className="flex items-center gap-2 text-[11px] px-2.5 py-1.5 rounded-lg animate-pulse-glow"
                style={{
                  color: "var(--accent-yellow)",
                  background: "rgba(224, 175, 104, 0.08)",
                }}
              >
                <Zap size={10} /> {tc.tool_name}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Tools */}
      <section className="p-4" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
        <h3
          className="text-[11px] uppercase tracking-widest mb-3 flex items-center gap-1.5 font-medium"
          style={{ color: "var(--text-dim)" }}
        >
          <Wrench size={11} /> Tools
          <span
            className="ml-auto px-1.5 py-0.5 rounded-full text-[10px] font-medium"
            style={{ background: "var(--bg-elevated)", color: "var(--text-dim)" }}
          >
            {tools.length}
          </span>
        </h3>
        <div className="space-y-0.5 max-h-44 overflow-y-auto">
          {tools.map((t) => (
            <div
              key={t.name}
              className="text-[11px] py-1 px-2.5 rounded-md truncate transition-colors cursor-default"
              style={{ color: "var(--text-secondary)" }}
              title={t.description}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "var(--bg-hover)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
              }}
            >
              {t.name}
            </div>
          ))}
        </div>
      </section>

      {/* Shortcuts */}
      <section className="p-4">
        <h3
          className="text-[11px] uppercase tracking-widest mb-3 flex items-center gap-1.5 font-medium"
          style={{ color: "var(--text-dim)" }}
        >
          <Command size={11} /> Shortcuts
        </h3>
        <div className="space-y-2 text-[11px]" style={{ color: "var(--text-dim)" }}>
          <div className="flex items-center justify-between">
            <span>Send message</span>
            <kbd
              className="px-1.5 py-0.5 rounded text-[10px] font-mono"
              style={{ background: "var(--bg-elevated)", color: "var(--text-secondary)" }}
            >
              ⌘↵
            </kbd>
          </div>
          <div className="flex items-center justify-between">
            <span>Interrupt</span>
            <kbd
              className="px-1.5 py-0.5 rounded text-[10px] font-mono"
              style={{ background: "var(--bg-elevated)", color: "var(--text-secondary)" }}
            >
              Esc
            </kbd>
          </div>
        </div>
      </section>
    </aside>
  );
}
