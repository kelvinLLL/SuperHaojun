import { usePanelStore } from "@/stores";
import { useWebSocket } from "@/hooks/useWebSocket";
import { TabBar } from "@/components/layout/TabBar";
import { Sidebar } from "@/components/layout/Sidebar";
import { ChatView } from "@/components/chat/ChatView";
import { MessagesView } from "@/components/messages/MessagesView";
import { ToolsView } from "@/components/tools/ToolsView";
import { AgentsView } from "@/components/agents/AgentsView";
import { SettingsView } from "@/components/settings/SettingsView";

function App() {
  const { activeTab, sidebarOpen } = usePanelStore();
  const { sendMessage, respondPermission } = useWebSocket();

  return (
    <div className="h-full flex flex-col" style={{ background: "var(--bg-primary)" }}>
      <TabBar />
      <div className="flex flex-1 overflow-hidden">
        <main className="flex-1 overflow-hidden">
          {activeTab === "chat" && (
            <ChatView onSend={sendMessage} onPermission={respondPermission} />
          )}
          {activeTab === "messages" && <MessagesView />}
          {activeTab === "tools" && <ToolsView />}
          {activeTab === "agents" && <AgentsView />}
          {activeTab === "settings" && <SettingsView />}
        </main>
        {activeTab === "chat" && <Sidebar />}
      </div>
    </div>
  );
}

export default App;
