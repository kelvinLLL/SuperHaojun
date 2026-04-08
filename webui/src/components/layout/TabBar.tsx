import { usePanelStore } from "@/stores";
import {
  MessageSquare, List, Wrench, Users, Settings,
  PanelRightClose, PanelRightOpen,
} from "lucide-react";
import { ModelSelector } from "../chat/ModelSelector";

const TABS = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "messages", label: "Messages", icon: List },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "agents", label: "Agents", icon: Users },
  { id: "settings", label: "Settings", icon: Settings },
] as const;

export function TabBar() {
  const { activeTab, setActiveTab, sidebarOpen, toggleSidebar } = usePanelStore();

  return (
    <header
      className="flex items-center justify-between px-3 h-11 shrink-0"
      style={{
        background: "var(--bg-secondary)",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      <div className="flex items-center gap-1">
        {/* Logo */}
        <button
          onClick={() => setActiveTab("chat")}
          className="flex items-center gap-2 mr-2 px-1 py-0.5 rounded-lg transition-opacity hover:opacity-80"
        >
          <div
            className="w-6 h-6 rounded-md flex items-center justify-center text-xs font-bold"
            style={{
              background: "linear-gradient(135deg, var(--accent-blue), var(--accent-cyan))",
              color: "#fff",
            }}
          >
            S
          </div>
          <span
            className="text-xs font-semibold tracking-tight hidden lg:inline"
            style={{ color: "var(--text-secondary)" }}
          >
            SuperHaojun
          </span>
        </button>

        {/* Model Selector */}
        <ModelSelector />

        {/* Separator */}
        <div className="w-px h-4 mx-1.5" style={{ background: "var(--border-subtle)" }} />

        {/* Tabs */}
        <nav className="flex items-center gap-0.5">
          {TABS.map(({ id, label, icon: Icon }) => {
            const active = activeTab === id;
            return (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-all duration-150"
                style={{
                  background: active ? "var(--bg-hover)" : "transparent",
                  color: active ? "var(--text-primary)" : "var(--text-dim)",
                }}
                onMouseEnter={(e) => {
                  if (!active) e.currentTarget.style.color = "var(--text-secondary)";
                }}
                onMouseLeave={(e) => {
                  if (!active) e.currentTarget.style.color = "var(--text-dim)";
                }}
              >
                <Icon size={13} strokeWidth={active ? 2 : 1.5} />
                <span className="hidden sm:inline">{label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      <button
        onClick={toggleSidebar}
        className="p-1 rounded-md transition-all duration-150"
        style={{
          color: sidebarOpen ? "var(--text-secondary)" : "var(--text-dim)",
          background: sidebarOpen ? "var(--bg-hover)" : "transparent",
        }}
        title={sidebarOpen ? "Close sidebar" : "Open sidebar"}
      >
        {sidebarOpen ? <PanelRightClose size={15} /> : <PanelRightOpen size={15} />}
      </button>
    </header>
  );
}
