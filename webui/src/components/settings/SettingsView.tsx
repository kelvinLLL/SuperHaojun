import { useState, useEffect } from "react";
import { usePanelStore } from "@/stores";
import type { AppConfig, ModelProfile } from "@/types";
import { Settings as SettingsIcon, Cpu, Database, Sparkles, Check, Zap, RefreshCw } from "lucide-react";

export function SettingsView() {
  const { config, setConfig, models, setModels } = usePanelStore();
  const [switching, setSwitching] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then(setConfig)
      .catch(() => {});
    fetch("/api/config/models")
      .then((r) => r.json())
      .then(setModels)
      .catch(() => {});
  }, []);

  const handleSwitch = async (key: string) => {
    setSwitching(key);
    try {
      const res = await fetch(`/api/config/models/${encodeURIComponent(key)}/activate`, {
        method: "POST",
      });
      const data = await res.json();
      if (data.ok) {
        // Refresh models list and config
        const [modelsRes, configRes] = await Promise.all([
          fetch("/api/config/models"),
          fetch("/api/config"),
        ]);
        setModels(await modelsRes.json());
        setConfig(await configRes.json());
      }
    } catch (err) {
      console.error("Switch failed:", err);
    } finally {
      setSwitching(null);
    }
  };

  return (
    <div className="h-full overflow-y-auto px-5 py-4 space-y-6">
      {/* Model Profiles */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(122, 162, 247, 0.1)" }}
          >
            <Zap size={14} style={{ color: "var(--accent-blue)" }} />
          </div>
          <h2 className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
            Model Profiles
          </h2>
          <span
            className="ml-auto text-[10px] px-2 py-0.5 rounded-full"
            style={{ background: "var(--bg-elevated)", color: "var(--text-dim)" }}
          >
            {models.length} available
          </span>
        </div>
        <div className="space-y-2">
          {models.map((m) => (
            <button
              key={m.key}
              onClick={() => !m.active && handleSwitch(m.key)}
              className="w-full text-left rounded-xl p-4 transition-all duration-200"
              style={{
                background: m.active ? "rgba(122, 162, 247, 0.06)" : "var(--bg-surface)",
                border: m.active
                  ? "1px solid rgba(122, 162, 247, 0.3)"
                  : "1px solid var(--border-subtle)",
                cursor: m.active ? "default" : "pointer",
                opacity: switching && switching !== m.key ? 0.5 : 1,
              }}
              onMouseEnter={(e) => {
                if (!m.active) e.currentTarget.style.borderColor = "var(--border)";
              }}
              onMouseLeave={(e) => {
                if (!m.active)
                  e.currentTarget.style.borderColor = "var(--border-subtle)";
              }}
            >
              <div className="flex items-center gap-3">
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
                  style={{
                    background: m.active
                      ? "linear-gradient(135deg, var(--accent-blue), var(--accent-cyan))"
                      : "var(--bg-elevated)",
                  }}
                >
                  {switching === m.key ? (
                    <RefreshCw size={14} className="animate-spin" style={{ color: "var(--accent-cyan)" }} />
                  ) : m.active ? (
                    <Check size={14} color="#fff" />
                  ) : (
                    <Cpu size={14} style={{ color: "var(--text-dim)" }} />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span
                      className="text-xs font-semibold"
                      style={{ color: m.active ? "var(--accent-blue)" : "var(--text-primary)" }}
                    >
                      {m.name}
                    </span>
                    {m.active && (
                      <span
                        className="text-[9px] px-1.5 py-0.5 rounded-full font-medium"
                        style={{
                          background: "rgba(122, 162, 247, 0.15)",
                          color: "var(--accent-blue)",
                        }}
                      >
                        ACTIVE
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] mt-0.5" style={{ color: "var(--text-dim)" }}>
                    {m.provider} · {m.model_id}
                  </div>
                </div>
              </div>
            </button>
          ))}
          {models.length === 0 && (
            <div className="flex items-center gap-2 text-xs p-4" style={{ color: "var(--text-dim)" }}>
              <div className="w-3 h-3 rounded-full animate-pulse" style={{ background: "var(--accent-blue)" }} />
              Loading models...
            </div>
          )}
        </div>
      </section>

      {/* Current Config */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(187, 154, 247, 0.1)" }}
          >
            <Cpu size={14} style={{ color: "var(--accent-magenta)" }} />
          </div>
          <h2 className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
            Active Configuration
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
