import { useState, useEffect } from "react";
import { usePanelStore } from "@/stores";
import type { AppConfig } from "@/types";
import { Settings as SettingsIcon, Cpu, Database, Sparkles } from "lucide-react";

export function SettingsView() {
  const { config, setConfig } = usePanelStore();

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then(setConfig)
      .catch(() => {});
  }, []);

  return (
    <div className="h-full overflow-y-auto px-5 py-4 space-y-6">
      {/* Model Config */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(187, 154, 247, 0.1)" }}
          >
            <Cpu size={14} style={{ color: "var(--accent-magenta)" }} />
          </div>
          <h2 className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
            Model Configuration
          </h2>
        </div>
        <div
          className="rounded-xl p-4 space-y-4"
          style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
        >
          {config ? (
            <>
              <Field label="Provider" value={config.provider} />
              <Field label="Model ID" value={config.model_id} />
              <Field label="Base URL" value={config.base_url} />
            </>
          ) : (
            <div className="flex items-center gap-2 text-xs" style={{ color: "var(--text-dim)" }}>
              <div className="w-3 h-3 rounded-full animate-pulse" style={{ background: "var(--accent-blue)" }} />
              Loading...
            </div>
          )}
        </div>
      </section>

      {/* About */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(125, 207, 255, 0.1)" }}
          >
            <Sparkles size={14} style={{ color: "var(--accent-cyan)" }} />
          </div>
          <h2 className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
            About
          </h2>
        </div>
        <div
          className="rounded-xl p-4 space-y-3 text-xs"
          style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
        >
          <div className="flex items-center gap-2">
            <span
              className="text-sm font-bold bg-clip-text text-transparent"
              style={{ backgroundImage: "linear-gradient(135deg, var(--accent-cyan), var(--accent-blue))" }}
            >
              SuperHaojun
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: "var(--bg-hover)", color: "var(--text-dim)" }}>
              v0.1
            </span>
          </div>
          <p style={{ color: "var(--text-secondary)" }}>AI-powered coding assistant</p>
          <div className="flex gap-4 pt-1" style={{ color: "var(--text-dim)" }}>
            <span>FastAPI</span>
            <span>React</span>
            <span>WebSocket</span>
          </div>
        </div>
      </section>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider font-medium mb-1" style={{ color: "var(--text-dim)" }}>
        {label}
      </div>
      <div
        className="text-xs font-mono px-3 py-2 rounded-lg"
        style={{
          color: "var(--text-primary)",
          background: "var(--bg-secondary)",
        }}
      >
        {value}
      </div>
    </div>
  );
}
