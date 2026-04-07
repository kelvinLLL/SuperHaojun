import { useState, useEffect } from "react";
import { usePanelStore } from "@/stores";
import type { SubAgentHistoryEntry, HookRule, HookLogEntry, DiagnosticEntry } from "@/types";
import {
  Users, Zap, FileWarning, CheckCircle, XCircle, Clock,
} from "lucide-react";

export function AgentsView() {
  const { agentHistory, setAgentHistory, hooks, setHooks, hookLog, setHookLog, diagnostics, setDiagnostics } = usePanelStore();

  useEffect(() => {
    fetch("/api/agents/history").then((r) => r.json()).then(setAgentHistory).catch(() => {});
    fetch("/api/hooks").then((r) => r.json()).then(setHooks).catch(() => {});
    fetch("/api/hooks/log").then((r) => r.json()).then(setHookLog).catch(() => {});
    fetch("/api/diagnostics").then((r) => r.json()).then(setDiagnostics).catch(() => {});
  }, []);

  return (
    <div className="h-full overflow-y-auto">
      {/* SubAgent History */}
      <section className="p-4">
        <h2
          className="text-xs font-bold uppercase tracking-wider mb-3 flex items-center gap-2"
          style={{ color: "var(--accent-cyan)" }}
        >
          <Users size={14} /> SubAgent History ({agentHistory.length})
        </h2>
        {agentHistory.length === 0 ? (
          <p className="text-xs" style={{ color: "var(--text-dim)" }}>No agent runs yet.</p>
        ) : (
          <div className="space-y-2">
            {agentHistory.map((entry, i) => (
              <div
                key={i}
                className="rounded-lg p-3"
                style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
              >
                <div className="flex items-center gap-2 mb-1">
                  {entry.success ? (
                    <CheckCircle size={14} style={{ color: "var(--accent-green)" }} />
                  ) : (
                    <XCircle size={14} style={{ color: "var(--accent-red)" }} />
                  )}
                  <span className="text-xs font-medium" style={{ color: "var(--text-primary)" }}>
                    {entry.task_id}
                  </span>
                </div>
                <p className="text-[11px] mb-1" style={{ color: "var(--text-secondary)" }}>
                  {entry.output.slice(0, 200)}{entry.output.length > 200 ? "..." : ""}
                </p>
                <div className="flex gap-3 text-[10px]" style={{ color: "var(--text-dim)" }}>
                  <span>🔧 {entry.tool_calls_made} tools</span>
                  <span>🔄 {entry.turns_used} turns</span>
                  <span>📊 {entry.tokens_used.toLocaleString()} tokens</span>
                </div>
                {entry.error && (
                  <div className="mt-1 text-[10px]" style={{ color: "var(--accent-red)" }}>
                    Error: {entry.error}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Hook Rules */}
      <section className="p-4 border-t" style={{ borderColor: "var(--border)" }}>
        <h2
          className="text-xs font-bold uppercase tracking-wider mb-3 flex items-center gap-2"
          style={{ color: "var(--accent-yellow)" }}
        >
          <Zap size={14} /> Hook Rules ({hooks.length})
        </h2>
        {hooks.length === 0 ? (
          <p className="text-xs" style={{ color: "var(--text-dim)" }}>No hooks configured.</p>
        ) : (
          <div className="space-y-1">
            {hooks.map((h, i) => (
              <div
                key={i}
                className="flex items-center gap-2 px-3 py-1.5 rounded text-[11px]"
                style={{
                  background: "var(--bg-surface)",
                  opacity: h.enabled ? 1 : 0.5,
                }}
              >
                <span style={{ color: "var(--accent-yellow)" }}>{h.event}</span>
                <span style={{ color: "var(--text-dim)" }}>→</span>
                <span style={{ color: "var(--text-secondary)" }}>{h.tool_pattern}</span>
                <span className="ml-auto" style={{ color: "var(--text-dim)" }}>
                  P{h.priority}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Hook Log */}
      {hookLog.length > 0 && (
        <section className="p-4 border-t" style={{ borderColor: "var(--border)" }}>
          <h2
            className="text-xs font-bold uppercase tracking-wider mb-3 flex items-center gap-2"
            style={{ color: "var(--accent-orange)" }}
          >
            <Clock size={14} /> Hook Activity Log (last {hookLog.length})
          </h2>
          <div className="space-y-0.5 max-h-60 overflow-y-auto">
            {hookLog.map((entry, i) => (
              <div
                key={i}
                className="flex items-center gap-2 px-2 py-1 rounded text-[10px]"
                style={{
                  background: entry.blocking ? "rgba(247, 118, 142, 0.1)" : "transparent",
                }}
              >
                <span style={{ color: "var(--accent-yellow)" }}>{entry.event}</span>
                <span style={{ color: "var(--text-dim)" }}>{entry.tool_name || "—"}</span>
                <span
                  style={{
                    color: entry.exit_code === 0 ? "var(--accent-green)" :
                           entry.exit_code === 2 ? "var(--accent-red)" :
                           "var(--accent-orange)",
                  }}
                >
                  exit={entry.exit_code}
                </span>
                <span className="ml-auto" style={{ color: "var(--text-dim)" }}>
                  {entry.duration_ms}ms
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Diagnostics */}
      <section className="p-4 border-t" style={{ borderColor: "var(--border)" }}>
        <h2
          className="text-xs font-bold uppercase tracking-wider mb-3 flex items-center gap-2"
          style={{ color: "var(--accent-red)" }}
        >
          <FileWarning size={14} /> Diagnostics ({diagnostics.length})
        </h2>
        {diagnostics.length === 0 ? (
          <p className="text-xs" style={{ color: "var(--text-dim)" }}>No diagnostics.</p>
        ) : (
          <div className="space-y-1 max-h-60 overflow-y-auto">
            {diagnostics.map((d, i) => (
              <div
                key={i}
                className="px-3 py-1.5 rounded text-[11px]"
                style={{ background: "var(--bg-surface)" }}
              >
                <span style={{ color: "var(--accent-cyan)" }}>
                  {d.file.split("/").pop()}:{d.line}
                </span>
                <span className="ml-2" style={{ color: "var(--text-secondary)" }}>
                  {d.message}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
