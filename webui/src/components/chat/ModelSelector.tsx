import { useState, useRef, useEffect } from "react";
import { ChevronDown, Check, Zap, Cpu } from "lucide-react";
import { usePanelStore } from "@/stores";

export function ModelSelector() {
  const [open, setOpen] = useState(false);
  const { models, config } = usePanelStore();
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const activeModel = models.find((m) => m.active);
  const displayName = activeModel?.name || config?.model_id || "No model";

  const handleSelect = async (key: string) => {
    setOpen(false);
    try {
      const res = await fetch(`/api/config/models/${encodeURIComponent(key)}/activate`, {
        method: "POST",
      });
      const data = await res.json();
      if (!data.ok) {
        console.error("Model switch failed:", data.error);
      }
    } catch (err) {
      console.error("Model switch error:", err);
    }
  };

  if (models.length <= 1) {
    return (
      <div className="flex items-center gap-1.5 px-2 py-1">
        <Cpu size={12} style={{ color: "var(--text-dim)" }} />
        <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
          {displayName}
        </span>
      </div>
    );
  }

  return (
    <div ref={dropdownRef} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-all duration-200"
        style={{
          background: open ? "var(--bg-elevated)" : "transparent",
          color: "var(--text-secondary)",
        }}
        onMouseEnter={(e) => {
          if (!open) e.currentTarget.style.background = "var(--bg-hover)";
        }}
        onMouseLeave={(e) => {
          if (!open) e.currentTarget.style.background = "transparent";
        }}
      >
        <Cpu size={12} style={{ color: "var(--accent-cyan)" }} />
        <span className="text-xs font-medium max-w-[180px] truncate">
          {displayName}
        </span>
        <ChevronDown
          size={12}
          style={{
            color: "var(--text-dim)",
            transform: open ? "rotate(180deg)" : "none",
            transition: "transform 0.2s",
          }}
        />
      </button>

      {open && (
        <div
          className="absolute top-full left-0 mt-1 min-w-[260px] rounded-xl overflow-hidden animate-slide-up"
          style={{
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            boxShadow: "var(--shadow-lg)",
            zIndex: 50,
          }}
        >
          <div
            className="px-3 py-2 text-[10px] uppercase tracking-widest font-medium"
            style={{ color: "var(--text-dim)", borderBottom: "1px solid var(--border-subtle)" }}
          >
            Models
          </div>
          {models.map((m) => (
            <button
              key={m.key}
              onClick={() => handleSelect(m.key)}
              className="w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors"
              style={{
                background: m.active ? "rgba(122, 162, 247, 0.08)" : "transparent",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = m.active
                  ? "rgba(122, 162, 247, 0.12)"
                  : "var(--bg-hover)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = m.active
                  ? "rgba(122, 162, 247, 0.08)"
                  : "transparent";
              }}
            >
              <div
                className="w-6 h-6 rounded-md flex items-center justify-center shrink-0"
                style={{
                  background: m.active
                    ? "rgba(122, 162, 247, 0.15)"
                    : "var(--bg-surface)",
                }}
              >
                {m.active ? (
                  <Check size={12} style={{ color: "var(--accent-blue)" }} />
                ) : (
                  <Zap size={12} style={{ color: "var(--text-dim)" }} />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div
                  className="text-xs font-medium truncate"
                  style={{ color: m.active ? "var(--accent-blue)" : "var(--text-primary)" }}
                >
                  {m.name}
                </div>
                <div className="text-[10px] truncate" style={{ color: "var(--text-dim)" }}>
                  {m.provider} · {m.model_id}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
