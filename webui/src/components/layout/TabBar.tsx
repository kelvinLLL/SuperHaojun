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
      className="flex items-center justify-between border-b px-4 h-11 shrink-0"
      style={{ borderColor: "var(--border)", background: "var(--bg-secondary)" }}
    >
      <div className="flex items-center gap-1">
        <span
          className="font-bold mr-4 text-sm tracking-wide"
          style={{ color: "var(--accent-cyan)" }}
        >
          ⚡ SuperHaojun
        </span>
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs transition-colors"
            style={{
              background: activeTab === id ? "var(--bg-active)" : "transparent",
              color: activeTab === id ? "var(--text-primary)" : "var(--text-dim)",
            }}
          >
            <Icon size={14} />
            {label}
          </button>
        ))}
      </div>
      <button
        onClick={toggleSidebar}
        className="p-1 rounded transition-colors"
        style={{ color: "var(--text-dim)" }}
        title={sidebarOpen ? "Close sidebar" : "Open sidebar"}
      >
        {sidebarOpen ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
      </button>
    </header>
  );
}
