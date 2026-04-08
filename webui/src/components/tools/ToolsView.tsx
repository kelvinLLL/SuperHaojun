import { useState, useEffect } from "react";
import { usePanelStore } from "@/stores";
import type { MCPServerStatus } from "@/types";
import {
  Wrench, Server, RefreshCw, Power, PowerOff, AlertTriangle,
} from "lucide-react";

const STATUS_STYLE: Record<string, { color: string; bg: string; label: string }> = {
  running: { color: "var(--accent-green)", bg: "rgba(158, 206, 106, 0.1)", label: "Running" },
  error: { color: "var(--accent-red)", bg: "rgba(247, 118, 142, 0.1)", label: "Error" },
  stopped: { color: "var(--text-dim)", bg: "var(--bg-hover)", label: "Stopped" },
  starting: { color: "var(--accent-yellow)", bg: "rgba(224, 175, 104, 0.1)", label: "Starting" },
  disabled: { color: "var(--text-dim)", bg: "var(--bg-hover)", label: "Disabled" },
};

export function ToolsView() {
  const { mcpServers, setMCPServers } = usePanelStore();
  const [tools, setTools] = useState<{ name: string; description: string }[]>([]);

  useEffect(() => {
    fetch("/api/tools").then((r) => r.json()).then(setTools).catch(() => {});
    fetch("/api/mcp/status").then((r) => r.json()).then(setMCPServers).catch(() => {});
  }, []);

  const mcpAction = async (name: string, action: string) => {
    await fetch(`/api/mcp/${name}/${action}`, { method: "POST" });
    const status = await fetch("/api/mcp/status").then((r) => r.json());
    setMCPServers(status);
  };

  return (
    <div className="h-full overflow-y-auto px-5 py-4">
      {/* Built-in Tools */}
      <section className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(122, 162, 247, 0.1)" }}
          >
            <Wrench size={14} style={{ color: "var(--accent-blue)" }} />
          </div>
          <h2 className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
            Built-in Tools
          </h2>
          <span
            className="text-[10px] px-2 py-0.5 rounded-full font-medium"
            style={{ background: "var(--bg-elevated)", color: "var(--text-dim)" }}
          >
            {tools.length}
          </span>
        </div>
        <div className="grid gap-1.5">
          {tools.map((t) => (
            <div
              key={t.name}
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors duration-200"
              style={{ background: "transparent" }}
              onMouseEnter={(e) => e.currentTarget.style.background = "var(--bg-surface)"}
              onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
            >
              <Wrench size={12} style={{ color: "var(--accent-teal)", opacity: 0.7 }} />
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium" style={{ color: "var(--text-primary)" }}>
                  {t.name}
                </div>
                <div className="text-[10px] truncate" style={{ color: "var(--text-dim)" }}>
                  {t.description}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* MCP Servers */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(187, 154, 247, 0.1)" }}
          >
            <Server size={14} style={{ color: "var(--accent-magenta)" }} />
          </div>
          <h2 className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
            MCP Servers
          </h2>
          <span
            className="text-[10px] px-2 py-0.5 rounded-full font-medium"
            style={{ background: "var(--bg-elevated)", color: "var(--text-dim)" }}
          >
            {mcpServers.length}
          </span>
        </div>
        {mcpServers.length === 0 ? (
          <div
            className="text-xs text-center py-8 rounded-xl"
            style={{ color: "var(--text-dim)", background: "var(--bg-surface)" }}
          >
            No MCP servers configured
            <div className="text-[10px] mt-1 font-mono" style={{ color: "var(--text-dim)", opacity: 0.6 }}>
              .haojun/mcp.json
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            {mcpServers.map((srv) => {
              const st = STATUS_STYLE[srv.status] || STATUS_STYLE.stopped;
              return (
                <div
                  key={srv.name}
                  className="rounded-xl p-3.5 transition-all duration-200"
                  style={{
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div className="flex items-center gap-2.5 mb-2">
                    <span className="status-dot" style={{ background: st.color }} />
                    <span className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
                      {srv.name}
                    </span>
                    <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>
                      {srv.transport}
                    </span>
                    <span
                      className="text-[10px] font-medium px-2 py-0.5 rounded-full ml-auto"
                      style={{ color: st.color, background: st.bg }}
                    >
                      {st.label}
                    </span>
                  </div>

                  {srv.error && (
                    <div className="flex items-center gap-1.5 mb-2 text-[10px] px-2 py-1.5 rounded-lg"
                      style={{ color: "var(--accent-red)", background: "rgba(247, 118, 142, 0.08)" }}
                    >
                      <AlertTriangle size={10} /> {srv.error}
                    </div>
                  )}

                  <div className="flex items-center gap-2 text-[10px] pt-1" style={{ color: "var(--text-dim)" }}>
                    <span>{srv.tools_count} tools</span>
                    <span style={{ opacity: 0.3 }}>·</span>
                    <span>{srv.scope}</span>
                    <div className="ml-auto flex gap-1.5">
                      {srv.status === "running" || srv.status === "error" ? (
                        <>
                          <button
                            onClick={() => mcpAction(srv.name, "reconnect")}
                            className="flex items-center gap-1 px-2.5 py-1 rounded-lg font-medium transition-all duration-200 btn-hover"
                            style={{ background: "var(--bg-hover)" }}
                          >
                            <RefreshCw size={10} /> Reconnect
                          </button>
                          <button
                            onClick={() => mcpAction(srv.name, "disable")}
                            className="flex items-center gap-1 px-2.5 py-1 rounded-lg font-medium transition-all duration-200 btn-hover"
                            style={{ background: "var(--bg-hover)", color: "var(--accent-red)" }}
                          >
                            <PowerOff size={10} /> Disable
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => mcpAction(srv.name, "enable")}
                          className="flex items-center gap-1 px-2.5 py-1 rounded-lg font-medium transition-all duration-200 btn-hover"
                          style={{ background: "var(--bg-hover)", color: "var(--accent-green)" }}
                        >
                          <Power size={10} /> Enable
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
