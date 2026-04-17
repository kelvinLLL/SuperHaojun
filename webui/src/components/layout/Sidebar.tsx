import { useChatStore, usePanelStore } from "@/stores";
import { Activity, Binary, Braces, Command, Cpu, Wrench, Zap } from "lucide-react";

function formatChars(value: number | undefined) {
  return typeof value === "number" ? value.toLocaleString() : "0";
}

export function Sidebar() {
  const { sidebarOpen } = usePanelStore();
  const { tokenUsage, tools, toolCalls, isStreaming } = useChatStore();

  if (!sidebarOpen) return null;

  const contextMetrics = tokenUsage.context_metrics;
  const providerUsage = tokenUsage.provider_usage;
  const activeToolCalls = Object.values(toolCalls).filter((t) => !t.done);
  const enabledTools = tools.filter((tool) => tool.enabled !== false);

  return (
    <aside
      className="w-72 shrink-0 overflow-y-auto"
      style={{
        borderLeft: "1px solid var(--border-subtle)",
        background: "var(--bg-secondary)",
      }}
    >
      <section className="p-4 space-y-3" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
        <h3
          className="text-[11px] uppercase tracking-widest flex items-center gap-1.5 font-medium"
          style={{ color: "var(--text-dim)" }}
        >
          <Binary size={11} /> Prompt Context
        </h3>

        {contextMetrics ? (
          <>
            <div
              className="rounded-xl p-3 space-y-2"
              style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
            >
              <MetricRow label="System prompt" value={`${formatChars(contextMetrics.system_prompt_chars)} chars`} />
              <MetricRow label="Transcript" value={`${formatChars(contextMetrics.message_chars)} chars`} />
              <MetricRow label="Tool calls" value={`${formatChars(contextMetrics.tool_call_chars)} chars`} />
              <MetricRow label="Messages" value={`${tokenUsage.message_count} in context`} />
              <MetricRow label="Compactions" value={`${tokenUsage.compaction_count}`} />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <MiniCard title="Memory" value={`${formatChars(contextMetrics.memory_chars)} chars`} icon={Cpu} />
              <MiniCard title="Skills" value={`${formatChars(contextMetrics.extension_prompt_chars)} chars`} icon={Zap} />
              <MiniCard title="Session" value={`${formatChars(contextMetrics.session_summary_chars)} chars`} icon={Braces} />
              <MiniCard
                title="Custom"
                value={`${formatChars(contextMetrics.custom_instructions_chars)} chars`}
                icon={Command}
              />
            </div>

            <div
              className="rounded-xl p-3 space-y-2"
              style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
            >
              <div className="text-[10px] uppercase tracking-wider" style={{ color: "var(--text-dim)" }}>
                Prompt Sections
              </div>
              <div className="space-y-1.5">
                {contextMetrics.system_prompt_sections.map((section) => (
                  <MetricRow
                    key={section.name}
                    label={section.name}
                    value={`${formatChars(section.chars)} chars`}
                    accent={section.cacheable ? "var(--accent-cyan)" : "var(--accent-yellow)"}
                  />
                ))}
              </div>
            </div>
          </>
        ) : (
          <EmptyHint text="Prompt/context metrics appear after the agent assembles a request." />
        )}
      </section>

      <section className="p-4 space-y-3" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
        <h3
          className="text-[11px] uppercase tracking-widest flex items-center gap-1.5 font-medium"
          style={{ color: "var(--text-dim)" }}
        >
          <Cpu size={11} /> Provider Usage
        </h3>

        {providerUsage ? (
          <div
            className="rounded-xl p-3 space-y-2"
            style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
          >
            <MetricRow label="Prompt tokens" value={providerUsage.prompt_tokens.toLocaleString()} />
            <MetricRow label="Completion tokens" value={providerUsage.completion_tokens.toLocaleString()} />
            <MetricRow label="Total tokens" value={providerUsage.total_tokens.toLocaleString()} />
          </div>
        ) : (
          <EmptyHint text="Real provider token usage appears when the upstream model returns usage metadata." />
        )}
      </section>

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
            {enabledTools.length}/{tools.length}
          </span>
        </h3>
        <div className="space-y-1 max-h-44 overflow-y-auto">
          {tools.map((tool) => (
            <div
              key={tool.name}
              className="flex items-center justify-between gap-2 text-[11px] py-1.5 px-2.5 rounded-md"
              style={{
                color: tool.enabled === false ? "var(--text-dim)" : "var(--text-secondary)",
                background: tool.enabled === false ? "transparent" : "var(--bg-surface)",
              }}
              title={tool.description}
            >
              <span className="truncate">{tool.name}</span>
              <span
                className="text-[9px] px-1.5 py-0.5 rounded-full uppercase tracking-wider"
                style={{
                  background: tool.enabled === false ? "var(--bg-hover)" : "rgba(122, 162, 247, 0.12)",
                  color: tool.enabled === false ? "var(--text-dim)" : "var(--accent-blue)",
                }}
              >
                {tool.enabled === false ? "off" : "on"}
              </span>
            </div>
          ))}
        </div>
      </section>

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

function MetricRow({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 text-[11px]">
      <span className="capitalize" style={{ color: "var(--text-dim)" }}>
        {label}
      </span>
      <span
        className="font-mono"
        style={{ color: accent ?? "var(--text-secondary)" }}
      >
        {value}
      </span>
    </div>
  );
}

function MiniCard({
  title,
  value,
  icon: Icon,
}: {
  title: string;
  value: string;
  icon: typeof Cpu;
}) {
  return (
    <div
      className="rounded-xl p-3"
      style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center gap-2 mb-1.5" style={{ color: "var(--text-dim)" }}>
        <Icon size={11} />
        <span className="text-[10px] uppercase tracking-wider">{title}</span>
      </div>
      <div className="text-[12px] font-mono" style={{ color: "var(--text-secondary)" }}>
        {value}
      </div>
    </div>
  );
}

function EmptyHint({ text }: { text: string }) {
  return (
    <div
      className="rounded-xl p-3 text-[11px]"
      style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text-dim)" }}
    >
      {text}
    </div>
  );
}
