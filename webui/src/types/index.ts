/* ── TypeScript types for the WebUI ── */

export interface ChatMessageData {
  id: string;
  role: "user" | "assistant" | "tool" | "system";
  content: string | null;
  tool_calls?: ToolCallData[];
  tool_call_id?: string;
  name?: string;
  timestamp: number;
}

export interface ToolCallData {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
}

export interface ToolInfo {
  name: string;
  description: string;
}

export interface MCPServerStatus {
  name: string;
  status: "stopped" | "starting" | "running" | "error" | "disabled";
  transport: string;
  tools_count: string;
  error: string;
  scope: string;
}

export interface HookRule {
  event: string;
  tool_pattern: string;
  hook_type: string;
  command: string;
  priority: number;
  enabled: boolean;
}

export interface HookLogEntry {
  event: string;
  tool_name: string;
  exit_code: number;
  duration_ms: number;
  blocking: boolean;
  timestamp: number;
}

export interface DiagnosticEntry {
  file: string;
  line: number;
  character: number;
  message: string;
  severity: number;
  provider: string;
}

export interface SubAgentHistoryEntry {
  task_id: string;
  task: string;
  output: string;
  tool_calls_made: number;
  turns_used: number;
  tokens_used: number;
  success: boolean;
  error: string;
  timestamp: number;
}

export interface TokenUsage {
  message_count: number;
  estimated_tokens: number;
  max_tokens: number;
  compaction_count: number;
}

export interface AppConfig {
  model_id: string;
  base_url: string;
  provider: string;
}

/* WebSocket message types from server */
export type WSMessage =
  | { type: "init"; tools: ToolInfo[]; messages: any[]; token_usage: TokenUsage }
  | { type: "text_delta"; text: string; id: string }
  | { type: "tool_call_start"; tool_call_id: string; tool_name: string; arguments: Record<string, any>; id: string }
  | { type: "tool_call_end"; tool_call_id: string; tool_name: string; result: string; id: string }
  | { type: "permission_request"; tool_call_id: string; tool_name: string; arguments: Record<string, any>; risk_level: string; id: string }
  | { type: "turn_start"; id: string }
  | { type: "turn_end"; finish_reason: string; id: string }
  | { type: "agent_start"; id: string }
  | { type: "agent_end"; id: string }
  | { type: "error"; message: string }
  | { type: "pong" };
