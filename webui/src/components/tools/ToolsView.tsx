import { useState, useEffect } from "react";
import { usePanelStore } from "@/stores";
import type { MCPServerStatus } from "@/types";
import {
  Wrench, Server, RefreshCw, Power, PowerOff, AlertTriangle,
} from "lucide-react";

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

  const STATUS_STYLE: Record<string, { color: string; label: string }> = {
    running: { color: "var(--accent-green)", label: "Running" },
    error: { color: "var(--accent-red)", label: "Error" },
    stopped: { color: "var(--text-dim)", label: "Stopped" },
    starting: { color: "var(--accent-yellow)", label: "Starting" },
    disabled: { color: "var(--text-dim)", label: "Disabled" },
  };

  return (
    <div className="h-full overflow-y-auto">
      {/* Built-in Tools */}
      <section className="p-4">
        <h2
          className="text-xs font-bold uppercase tracking-wider mb-3 flex items-center gap-2"
          style={{ color: "var(--accent-blue)" }}
        >
          <Wrench size={14} /> Built-in Tools ({tools.length})
        </h2>
        <div className="grid gap-2">
          {tools.map((t) => (
            <div
              key={t.name}
              className="flex items-center gap-3 px-3 py-2 rounded"
              style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
            >
              <Wrench size={12} style={{ color: "var(--accent-teal)" }} />
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium" style={{ color: "var(--text-primary)" }}>
                  {t.name}
                </div>
                <div
                  className="text-[10px] truncate"
                  style={{ color: "var(--text-dim)" }}
                >
                  {t.description}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* MCP Servers */}
      <section className="p-4 border-t" style={{ borderColor: "var(--border)" }}>
        <h2
          className="text-xs font-bold uppercase tracking-wider mb-3 flex items-center gap-2"
          style={{ color: "var(--accent-magenta)" }}
        >
          <Server size={14} /> MCP Servers ({mcpServers.length})
        </h2>
        {mcpServers.length === 0 ? (
          <p className="text-xs" style={{ color: "var(--text-dim)" }}>
            No MCP servers configured. Add servers in <code>.haojun/mcp.json</code>
          </p>
        ) : (
          <div className="space-y-2">
            {mcpServers.map((srv) => {
              const style = STATUS_STYLE[srv.status] || STATUS_STYLE.stopped;
              return (
                <div
                  key={srv.name}
                  className="rounded-lg p-3"
                  style={{
                    background: "var(--bg-surface)",
                    border: `1px solid ${srv.status === "error" ? "var(--accent-red)" : "var(--border)"}`,
                  }}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span
                      className="status-dot"
                      style={{ background: style.color }}
                    />
                    <span className="text-xs font-medium" style={{ color: "var(--text-primary)" }}>
                      {srv.name}
                    </span>
                    <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>
                      {srv.transport} · {srv.scope}
                    </span>
                    <span className="text-[10px] ml-auto" style={{ color: style.color }}>
                      {style.label}
                    </span>
                  </div>

                  {srv.error && (
                    <div className="flex items-center gap-1 mb-2 text-[10px]" style={{ color: "var(--accent-red)" }}>
                      <AlertTriangle size={10} /> {srv.error}
                    </div>
                  )}

                  <div className="flex items-center gap-1 text-[10px]" style={{ color: "var(--text-dim)" }}>
                    <span>{srv.tools_count} tools</span>
                    <span className="ml-auto flex gap-1">
                      {srv.status === "running" || srv.status === "error" ? (
                        <>
                          <button
                            onClick={() => mcpAction(srv.name, "reconnect")}
                            className="flex items-center gap-0.5 px-2 py-0.5 rounded"
                            style={{ background: "var(--bg-hover)" }}
                          >
                            <RefreshCw size={10} /> Reconnect
                          </button>
                          <button
                            onClick={() => mcpAction(srv.name, "disable")}
                            className="flex items-center gap-0.5 px-2 py-0.5 rounded"
                            style={{ background: "var(--bg-hover)", color: "var(--accent-red)" }}
                          >
                            <PowerOff size={10} /> Disable
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => mcpAction(srv.name, "enable")}
                          className="flex items-center gap-0.5 px-2 py-0.5 rounded"
                          style={{ background: "var(--bg-hover)", color: "var(--accent-green)" }}
                        >
                          <Power size={10} /> Enable
                        </button>
                      )}
                    </span>
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
