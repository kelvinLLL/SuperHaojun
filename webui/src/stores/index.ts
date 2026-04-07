import { create } from "zustand";
import type {
  ChatMessageData,
  ToolInfo,
  TokenUsage,
  MCPServerStatus,
  HookRule,
  HookLogEntry,
  DiagnosticEntry,
  SubAgentHistoryEntry,
  AppConfig,
} from "@/types";

/* ── Chat Store ── */

interface ToolCallState {
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, any>;
  result?: string;
  done: boolean;
}

interface PermissionRequestState {
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, any>;
  risk_level: string;
}

interface ChatState {
  messages: ChatMessageData[];
  streamingText: string;
  isStreaming: boolean;
  toolCalls: Record<string, ToolCallState>;
  permissionRequest: PermissionRequestState | null;
  tools: ToolInfo[];
  tokenUsage: TokenUsage;

  addUserMessage: (text: string) => void;
  appendDelta: (text: string) => void;
  startStreaming: () => void;
  endStreaming: () => void;
  startToolCall: (tc: Omit<ToolCallState, "done">) => void;
  endToolCall: (id: string, result: string) => void;
  setPermission: (req: PermissionRequestState | null) => void;
  setTools: (tools: ToolInfo[]) => void;
  setTokenUsage: (usage: TokenUsage) => void;
  setMessages: (msgs: ChatMessageData[]) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  streamingText: "",
  isStreaming: false,
  toolCalls: {},
  permissionRequest: null,
  tools: [],
  tokenUsage: { message_count: 0, estimated_tokens: 0, max_tokens: 128000, compaction_count: 0 },

  addUserMessage: (text) =>
    set((s) => ({
      messages: [
        ...s.messages,
        { id: crypto.randomUUID(), role: "user", content: text, timestamp: Date.now() },
      ],
    })),

  appendDelta: (text) =>
    set((s) => ({ streamingText: s.streamingText + text })),

  startStreaming: () =>
    set({ streamingText: "", isStreaming: true, toolCalls: {} }),

  endStreaming: () =>
    set((s) => {
      const msgs = s.streamingText
        ? [
            ...s.messages,
            {
              id: crypto.randomUUID(),
              role: "assistant" as const,
              content: s.streamingText,
              timestamp: Date.now(),
            },
          ]
        : s.messages;
      return { messages: msgs, streamingText: "", isStreaming: false };
    }),

  startToolCall: (tc) =>
    set((s) => ({
      toolCalls: { ...s.toolCalls, [tc.tool_call_id]: { ...tc, done: false } },
    })),

  endToolCall: (id, result) =>
    set((s) => ({
      toolCalls: {
        ...s.toolCalls,
        [id]: s.toolCalls[id] ? { ...s.toolCalls[id], result, done: true } : { tool_call_id: id, tool_name: "unknown", arguments: {}, result, done: true },
      },
    })),

  setPermission: (req) => set({ permissionRequest: req }),
  setTools: (tools) => set({ tools }),
  setTokenUsage: (usage) => set({ tokenUsage: usage }),
  setMessages: (msgs) => set({ messages: msgs }),
}));

/* ── Side Panels Store ── */

interface PanelState {
  activeTab: string;
  sidebarOpen: boolean;
  setActiveTab: (tab: string) => void;
  toggleSidebar: () => void;

  // MCP
  mcpServers: MCPServerStatus[];
  setMCPServers: (servers: MCPServerStatus[]) => void;

  // Hooks
  hooks: HookRule[];
  hookLog: HookLogEntry[];
  setHooks: (hooks: HookRule[]) => void;
  setHookLog: (log: HookLogEntry[]) => void;

  // Diagnostics
  diagnostics: DiagnosticEntry[];
  setDiagnostics: (diags: DiagnosticEntry[]) => void;

  // Agents
  agentHistory: SubAgentHistoryEntry[];
  setAgentHistory: (history: SubAgentHistoryEntry[]) => void;

  // Config
  config: AppConfig | null;
  setConfig: (config: AppConfig) => void;
}

export const usePanelStore = create<PanelState>((set) => ({
  activeTab: "chat",
  sidebarOpen: true,
  setActiveTab: (tab) => set({ activeTab: tab }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),

  mcpServers: [],
  setMCPServers: (servers) => set({ mcpServers: servers }),

  hooks: [],
  hookLog: [],
  setHooks: (hooks) => set({ hooks }),
  setHookLog: (log) => set({ hookLog: log }),

  diagnostics: [],
  setDiagnostics: (diags) => set({ diagnostics: diags }),

  agentHistory: [],
  setAgentHistory: (history) => set({ agentHistory: history }),

  config: null,
  setConfig: (config) => set({ config }),
}));
