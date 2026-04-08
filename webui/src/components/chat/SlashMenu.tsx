import { useEffect, useRef } from "react";
import { Command } from "lucide-react";
import type { CommandInfo } from "@/types";

interface SlashMenuProps {
  commands: CommandInfo[];
  filter: string;
  selectedIndex: number;
  onSelect: (cmd: CommandInfo) => void;
}

export function SlashMenu({ commands, filter, selectedIndex, onSelect }: SlashMenuProps) {
  const listRef = useRef<HTMLDivElement>(null);

  const filtered = commands.filter((c) =>
    c.name.startsWith(filter.toLowerCase()),
  );

  useEffect(() => {
    const active = listRef.current?.children[selectedIndex] as HTMLElement | undefined;
    active?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  if (filtered.length === 0) return null;

  return (
    <div
      ref={listRef}
      className="absolute bottom-full left-0 right-0 mb-2 max-h-64 overflow-y-auto rounded-xl animate-slide-up"
      style={{
        background: "var(--bg-elevated)",
        border: "1px solid var(--border)",
        boxShadow: "var(--shadow-lg)",
        zIndex: 50,
      }}
    >
      <div className="px-3 py-2 text-[10px] uppercase tracking-widest font-medium"
        style={{ color: "var(--text-dim)", borderBottom: "1px solid var(--border-subtle)" }}>
        Commands
      </div>
      {filtered.map((cmd, i) => (
        <button
          key={cmd.name}
          onClick={() => onSelect(cmd)}
          className="w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors"
          style={{
            background: i === selectedIndex ? "var(--bg-hover)" : "transparent",
            color: "var(--text-primary)",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "var(--bg-hover)";
          }}
          onMouseLeave={(e) => {
            if (i !== selectedIndex) e.currentTarget.style.background = "transparent";
          }}
        >
          <div
            className="w-6 h-6 rounded-md flex items-center justify-center shrink-0"
            style={{ background: "rgba(122, 162, 247, 0.1)" }}
          >
            <Command size={12} style={{ color: "var(--accent-blue)" }} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-xs font-medium">
              <span style={{ color: "var(--accent-blue)" }}>/</span>
              {cmd.name}
            </div>
            <div className="text-[11px] truncate" style={{ color: "var(--text-dim)" }}>
              {cmd.description}
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}
