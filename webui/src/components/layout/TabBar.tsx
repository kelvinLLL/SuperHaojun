import { usePanelStore } from "@/stores";
import {
  MessageSquare, List, Wrench, Users, Settings,
  PanelRightClose, PanelRightOpen,
} from "lucide-react";

const TABS = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "messages", label: "Messages", icon: List },
  { id: "tools", label: "Tools & MCP", icon: Wrench },
  { id: "agents", label: "Agents", icon: Users },
  { id: "settings", label: "Settings", icon: Settings },
] as const;

export function TabBar() {
  const { activeTab, setActiveTab, sidebarOpen, toggleSidebar } = usePanelStore();

  return (
    <header
      className="flex items-center justify-between px-4 h-12 shrink-0 glass"
      style={{ borderBottom: "1px solid var(--border-subtle)" }}
    >
      <div className="flex items-center gap-1">
        {/* Logo */}
        <div className="flex items-center gap-2 mr-6">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center text-sm font-bold"
            style={{
              background: "linear-gradient(135deg, var(--accent-blue), var(--accent-cyan))",
              color: "#fff",
              boxShadow: "var(--shadow-glow-blue)",
            }}
          >
            S
          </div>
          <span
            className="text-sm font-semibold tracking-tight"
            style={{ color: "var(--text-primary)" }}
          >
            SuperHaojun
          </span>
        </div>

        {/* Tabs */}
        <nav className="flex items-center gap-0.5">
          {TABS.map(({ id, label, icon: Icon }) => {
            const active = activeTab === id;
            return (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className="relative flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200"
                style={{
                  background: active ? "var(--bg-elevated)" : "transparent",
                  color: active ? "var(--text-primary)" : "var(--text-dim)",
                  boxShadow: active ? "var(--shadow-sm)" : "none",
                }}
              >
                <Icon size={14} strokeWidth={active ? 2.2 : 1.5} />
                <span className="hidden sm:inline">{label}</span>
                {active && (
                  <div
                    className="absolute bottom-0 left-1/2 -translate-x-1/2 w-5 h-0.5 rounded-full"
                    style={{ background: "var(--accent-blue)" }}
                  />
                )}
              </button>
            );
          })}
        </nav>
      </div>

      <button
        onClick={toggleSidebar}
        className="p-1.5 rounded-lg transition-all duration-200"
        style={{
          color: "var(--text-dim)",
          background: sidebarOpen ? "var(--bg-elevated)" : "transparent",
        }}
        title={sidebarOpen ? "Close sidebar" : "Open sidebar"}
      >
        {sidebarOpen ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
      </button>
    </header>
  );
}
