import { useState, useEffect } from "react";
import { usePanelStore } from "@/stores";
import type { AppConfig } from "@/types";
import { Settings as SettingsIcon, Cpu, Database } from "lucide-react";

export function SettingsView() {
  const { config, setConfig } = usePanelStore();

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then(setConfig)
      .catch(() => {});
  }, []);

  return (
    <div className="h-full overflow-y-auto p-4">
      <h2
        className="text-xs font-bold uppercase tracking-wider mb-4 flex items-center gap-2"
        style={{ color: "var(--accent-magenta)" }}
      >
        <SettingsIcon size={14} /> Configuration
      </h2>

      {/* Model Config */}
      <section className="mb-6">
        <h3
          className="text-[11px] uppercase tracking-wider mb-2 flex items-center gap-1.5"
          style={{ color: "var(--text-dim)" }}
        >
          <Cpu size={12} /> Model
        </h3>
        <div
          className="rounded-lg p-4 space-y-3"
          style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
        >
          {config ? (
            <>
              <Field label="Provider" value={config.provider} />
              <Field label="Model ID" value={config.model_id} />
              <Field label="Base URL" value={config.base_url} />
            </>
          ) : (
            <p className="text-xs" style={{ color: "var(--text-dim)" }}>Loading...</p>
          )}
        </div>
      </section>

      {/* Info */}
      <section>
        <h3
          className="text-[11px] uppercase tracking-wider mb-2 flex items-center gap-1.5"
          style={{ color: "var(--text-dim)" }}
        >
          <Database size={12} /> About
        </h3>
        <div
          className="rounded-lg p-4 space-y-2 text-xs"
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            color: "var(--text-secondary)",
          }}
        >
          <p><strong style={{ color: "var(--accent-cyan)" }}>SuperHaojun</strong> — AI-powered coding assistant</p>
          <p>FastAPI backend + React frontend</p>
          <p>WebSocket real-time communication</p>
        </div>
      </section>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider" style={{ color: "var(--text-dim)" }}>
        {label}
      </div>
      <div className="text-xs mt-0.5" style={{ color: "var(--text-primary)" }}>
        {value}
      </div>
    </div>
  );
}
