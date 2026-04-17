import { useEffect, useState } from "react";
import { useChatStore, usePanelStore } from "@/stores";
import type { AppConfig, ModelProfile } from "@/types";
import {
  Check,
  Cpu,
  RefreshCw,
  Settings as SettingsIcon,
  Sparkles,
  Wrench,
  Zap,
} from "lucide-react";

export function SettingsView() {
  const { config, setConfig, models, setModels, extensions, setExtensions } = usePanelStore();
  const { tools, setTools } = useChatStore();
  const [switching, setSwitching] = useState<string | null>(null);
  const [toolBusy, setToolBusy] = useState<string | null>(null);
  const [extensionBusy, setExtensionBusy] = useState<string | null>(null);

  useEffect(() => {
    refreshConfig(setConfig, setModels);
    fetch("/api/extensions")
      .then((r) => r.json())
      .then(setExtensions)
      .catch(() => {});
    fetch("/api/tools")
      .then((r) => r.json())
      .then(setTools)
      .catch(() => {});
  }, [setConfig, setExtensions, setModels, setTools]);

  const handleSwitch = async (key: string) => {
    setSwitching(key);
    try {
      const res = await fetch(`/api/config/models/${encodeURIComponent(key)}/activate`, {
        method: "POST",
      });
      const data = await res.json();
      if (data.ok) {
        await refreshConfig(setConfig, setModels);
      }
    } catch (err) {
      console.error("Switch failed:", err);
    } finally {
      setSwitching(null);
    }
  };

  const handleToolToggle = async (name: string, enabled: boolean) => {
    setToolBusy(name);
    try {
      const res = await fetch("/api/tools/state", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, enabled }),
      });
      const data = await res.json();
      if (data.ok && Array.isArray(data.tools)) {
        setTools(data.tools);
      }
    } catch (err) {
      console.error("Tool toggle failed:", err);
    } finally {
      setToolBusy(null);
    }
  };

  const handleExtensionToggle = async (id: string, enabled: boolean) => {
    setExtensionBusy(id);
    try {
      const res = await fetch("/api/extensions/state", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, enabled }),
      });
      const data = await res.json();
      if (data.ok && Array.isArray(data.extensions)) {
        setExtensions(data.extensions);
      }
    } catch (err) {
      console.error("Extension toggle failed:", err);
    } finally {
      setExtensionBusy(null);
    }
  };

  return (
    <div className="h-full overflow-y-auto px-5 py-4 space-y-6">
      <section>
        <SectionHeader
          icon={Zap}
          title="Model Profiles"
          badge={`${models.length} available`}
          tint="rgba(122, 162, 247, 0.1)"
          color="var(--accent-blue)"
        />
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
                    {m.active && <Pill text="ACTIVE" color="var(--accent-blue)" bg="rgba(122, 162, 247, 0.15)" />}
                  </div>
                  <div className="text-[11px] mt-0.5" style={{ color: "var(--text-dim)" }}>
                    {m.provider} · {m.model_id}
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>
      </section>

      <section>
        <SectionHeader
          icon={Cpu}
          title="Active Configuration"
          tint="rgba(187, 154, 247, 0.1)"
          color="var(--accent-magenta)"
        />
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
            <LoadingHint />
          )}
        </div>
      </section>

      <section>
        <SectionHeader
          icon={Wrench}
          title="Tool Governance"
          badge={`${tools.filter((tool) => tool.enabled !== false).length}/${tools.length} enabled`}
          tint="rgba(224, 175, 104, 0.12)"
          color="var(--accent-yellow)"
        />
        <GovernanceCard>
          {tools.map((tool) => (
            <ToggleRow
              key={tool.name}
              title={tool.name}
              subtitle={`${tool.risk_level ?? "read"} tool`}
              enabled={tool.enabled !== false}
              busy={toolBusy === tool.name}
              onToggle={() => handleToolToggle(tool.name, tool.enabled === false)}
            />
          ))}
          {tools.length === 0 && <LoadingHint text="Loading tools..." />}
        </GovernanceCard>
      </section>

      <section>
        <SectionHeader
          icon={SettingsIcon}
          title="Skills & Extensions"
          badge={`${extensions.filter((entry) => entry.enabled).length}/${extensions.length} enabled`}
          tint="rgba(125, 207, 255, 0.1)"
          color="var(--accent-cyan)"
        />
        <GovernanceCard>
          {extensions.map((entry) => (
            <ToggleRow
              key={entry.id}
              title={entry.name}
              subtitle={`${entry.kind} · ${entry.scope}`}
              enabled={entry.enabled}
              busy={extensionBusy === entry.id}
              onToggle={() => handleExtensionToggle(entry.id, !entry.enabled)}
              detail={entry.source}
              badge={entry.prompt_enabled ? "prompt" : "metadata"}
            />
          ))}
          {extensions.length === 0 && <LoadingHint text="No repo-local skills or extensions discovered." />}
        </GovernanceCard>
      </section>

      <section>
        <SectionHeader
          icon={Sparkles}
          title="About"
          tint="rgba(125, 207, 255, 0.1)"
          color="var(--accent-cyan)"
        />
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

async function refreshConfig(
  setConfig: (config: AppConfig) => void,
  setModels: (models: ModelProfile[]) => void,
) {
  const [configRes, modelsRes] = await Promise.all([
    fetch("/api/config"),
    fetch("/api/config/models"),
  ]);
  setConfig(await configRes.json());
  setModels(await modelsRes.json());
}

function SectionHeader({
  icon: Icon,
  title,
  badge,
  tint,
  color,
}: {
  icon: typeof Cpu;
  title: string;
  badge?: string;
  tint: string;
  color: string;
}) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <div
        className="w-7 h-7 rounded-lg flex items-center justify-center"
        style={{ background: tint }}
      >
        <Icon size={14} style={{ color }} />
      </div>
      <h2 className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
        {title}
      </h2>
      {badge ? (
        <span
          className="ml-auto text-[10px] px-2 py-0.5 rounded-full"
          style={{ background: "var(--bg-elevated)", color: "var(--text-dim)" }}
        >
          {badge}
        </span>
      ) : null}
    </div>
  );
}

function GovernanceCard({ children }: { children: import("react").ReactNode }) {
  return (
    <div
      className="rounded-xl p-3 space-y-2"
      style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
    >
      {children}
    </div>
  );
}

function ToggleRow({
  title,
  subtitle,
  enabled,
  busy,
  onToggle,
  detail,
  badge,
}: {
  title: string;
  subtitle: string;
  enabled: boolean;
  busy: boolean;
  onToggle: () => void;
  detail?: string;
  badge?: string;
}) {
  return (
    <div
      className="rounded-xl p-3 flex items-start gap-3"
      style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-subtle)" }}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <div className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
            {title}
          </div>
          {badge ? <Pill text={badge} color="var(--accent-cyan)" bg="rgba(125, 207, 255, 0.12)" /> : null}
          <Pill
            text={enabled ? "ON" : "OFF"}
            color={enabled ? "var(--accent-green)" : "var(--text-dim)"}
            bg={enabled ? "rgba(158, 206, 106, 0.12)" : "var(--bg-hover)"}
          />
        </div>
        <div className="text-[11px] mt-0.5" style={{ color: "var(--text-dim)" }}>
          {subtitle}
        </div>
        {detail ? (
          <div className="text-[10px] mt-1 font-mono truncate" style={{ color: "var(--text-dim)" }}>
            {detail}
          </div>
        ) : null}
      </div>

      <button
        onClick={onToggle}
        disabled={busy}
        className="px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all duration-200"
        style={{
          background: enabled ? "rgba(247, 118, 142, 0.12)" : "rgba(158, 206, 106, 0.12)",
          color: enabled ? "var(--accent-red)" : "var(--accent-green)",
          border: "1px solid var(--border-subtle)",
          opacity: busy ? 0.6 : 1,
        }}
      >
        {busy ? "Working..." : enabled ? "Disable" : "Enable"}
      </button>
    </div>
  );
}

function Pill({ text, color, bg }: { text: string; color: string; bg: string }) {
  return (
    <span
      className="text-[9px] px-1.5 py-0.5 rounded-full font-medium uppercase tracking-wider"
      style={{ background: bg, color }}
    >
      {text}
    </span>
  );
}

function LoadingHint({ text = "Loading..." }: { text?: string }) {
  return (
    <div className="flex items-center gap-2 text-xs" style={{ color: "var(--text-dim)" }}>
      <div className="w-3 h-3 rounded-full animate-pulse" style={{ background: "var(--accent-blue)" }} />
      {text}
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
          background: "var(--bg-secondary)",
          color: "var(--text-secondary)",
          border: "1px solid var(--border-subtle)",
          wordBreak: "break-all",
        }}
      >
        {value}
      </div>
    </div>
  );
}
