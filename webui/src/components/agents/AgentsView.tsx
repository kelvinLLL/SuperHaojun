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
    <div className="h-full overflow-y-auto px-5 py-4 space-y-6">
      {/* SubAgent History */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(125, 207, 255, 0.1)" }}
          >
            <Users size={14} style={{ color: "var(--accent-cyan)" }} />
          </div>
          <h2 className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
            SubAgent History
          </h2>
          <span
            className="text-[10px] px-2 py-0.5 rounded-full font-medium"
            style={{ background: "var(--bg-elevated)", color: "var(--text-dim)" }}
          >
            {agentHistory.length}
          </span>
        </div>
        {agentHistory.length === 0 ? (
          <div className="text-xs text-center py-6 rounded-xl" style={{ color: "var(--text-dim)", background: "var(--bg-surface)" }}>
            No agent runs yet
          </div>
        ) : (
          <div className="space-y-2">
            {agentHistory.map((entry, i) => (
              <div
                key={i}
                className="rounded-xl p-3.5"
                style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
              >
                <div className="flex items-center gap-2 mb-2">
                  {entry.success ? (
                    <CheckCircle size={14} style={{ color: "var(--accent-green)" }} />
                  ) : (
                    <XCircle size={14} style={{ color: "var(--accent-red)" }} />
                  )}
                  <span className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
                    {entry.task_id}
                  </span>
                </div>
                <p className="text-[11px] mb-2 leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                  {entry.output.slice(0, 200)}{entry.output.length > 200 ? "..." : ""}
                </p>
                <div className="flex gap-4 text-[10px]" style={{ color: "var(--text-dim)" }}>
                  <span>{entry.tool_calls_made} tools</span>
                  <span>{entry.turns_used} turns</span>
                  <span>{entry.tokens_used.toLocaleString()} tokens</span>
                </div>
                {entry.error && (
                  <div
                    className="mt-2 text-[10px] px-2 py-1.5 rounded-lg"
                    style={{ color: "var(--accent-red)", background: "rgba(247, 118, 142, 0.08)" }}
                  >
                    {entry.error}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Hook Rules */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(224, 175, 104, 0.1)" }}
          >
            <Zap size={14} style={{ color: "var(--accent-yellow)" }} />
          </div>
          <h2 className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
            Hook Rules
          </h2>
          <span
            className="text-[10px] px-2 py-0.5 rounded-full font-medium"
            style={{ background: "var(--bg-elevated)", color: "var(--text-dim)" }}
          >
            {hooks.length}
          </span>
        </div>
        {hooks.length === 0 ? (
          <div className="text-xs text-center py-6 rounded-xl" style={{ color: "var(--text-dim)", background: "var(--bg-surface)" }}>
            No hooks configured
          </div>
        ) : (
          <div className="space-y-1">
            {hooks.map((h, i) => (
              <div
                key={i}
                className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-[11px] transition-colors"
                style={{
                  background: "var(--bg-surface)",
                  opacity: h.enabled ? 1 : 0.4,
                }}
              >
                <span className="font-medium" style={{ color: "var(--accent-yellow)" }}>{h.event}</span>
                <span style={{ color: "var(--text-dim)", fontSize: "10px" }}>→</span>
                <span className="font-mono" style={{ color: "var(--text-secondary)" }}>{h.tool_pattern}</span>
                <span
                  className="ml-auto text-[10px] px-1.5 py-0.5 rounded-md"
                  style={{ background: "var(--bg-hover)", color: "var(--text-dim)" }}
                >
                  P{h.priority}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Hook Log */}
      {hookLog.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center"
              style={{ background: "rgba(255, 158, 100, 0.1)" }}
            >
              <Clock size={14} style={{ color: "var(--accent-orange)" }} />
            </div>
            <h2 className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
              Activity Log
            </h2>
          </div>
          <div className="space-y-0.5 max-h-60 overflow-y-auto">
            {hookLog.map((entry, i) => (
              <div
                key={i}
                className="flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-[10px]"
                style={{
                  background: entry.blocking ? "rgba(247, 118, 142, 0.06)" : "transparent",
                }}
              >
                <span className="font-medium" style={{ color: "var(--accent-yellow)" }}>{entry.event}</span>
                <span style={{ color: "var(--text-dim)" }}>{entry.tool_name || "—"}</span>
                <span
                  className="font-mono"
                  style={{
                    color: entry.exit_code === 0 ? "var(--accent-green)" :
                           entry.exit_code === 2 ? "var(--accent-red)" :
                           "var(--accent-orange)",
                  }}
                >
                  {entry.exit_code}
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
      <section>
        <div className="flex items-center gap-2 mb-3">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(247, 118, 142, 0.1)" }}
          >
            <FileWarning size={14} style={{ color: "var(--accent-red)" }} />
          </div>
          <h2 className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
            Diagnostics
          </h2>
          <span
            className="text-[10px] px-2 py-0.5 rounded-full font-medium"
            style={{ background: "var(--bg-elevated)", color: "var(--text-dim)" }}
          >
            {diagnostics.length}
          </span>
        </div>
        {diagnostics.length === 0 ? (
          <div className="text-xs text-center py-6 rounded-xl" style={{ color: "var(--text-dim)", background: "var(--bg-surface)" }}>
            No diagnostics
          </div>
        ) : (
          <div className="space-y-1 max-h-60 overflow-y-auto">
            {diagnostics.map((d, i) => (
              <div
                key={i}
                className="px-3 py-2 rounded-xl text-[11px]"
                style={{ background: "var(--bg-surface)" }}
              >
                <span className="font-mono" style={{ color: "var(--accent-cyan)" }}>
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
