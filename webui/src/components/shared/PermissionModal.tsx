import { Shield, ShieldAlert, ShieldCheck, X } from "lucide-react";

interface PermissionModalProps {
  request: {
    tool_call_id: string;
    tool_name: string;
    arguments: Record<string, any>;
    risk_level: string;
  };
  onRespond: (toolCallId: string, granted: boolean) => void;
}

const RISK_COLORS: Record<string, string> = {
  read: "var(--accent-green)",
  write: "var(--accent-yellow)",
  dangerous: "var(--accent-red)",
};

export function PermissionModal({ request, onRespond }: PermissionModalProps) {
  const riskColor = RISK_COLORS[request.risk_level] || "var(--accent-yellow)";
  const RiskIcon = request.risk_level === "dangerous" ? ShieldAlert :
                   request.risk_level === "write" ? Shield : ShieldCheck;

  return (
    <div className="fixed inset-0 flex items-center justify-center z-50">
      {/* Backdrop */}
      <div
        className="absolute inset-0"
        style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}
        onClick={() => onRespond(request.tool_call_id, false)}
      />

      {/* Modal */}
      <div
        className="relative rounded-lg p-6 max-w-md w-full mx-4 animate-slide-in"
        style={{
          background: "var(--bg-surface)",
          border: `1px solid ${riskColor}`,
          boxShadow: `0 0 30px ${riskColor}20`,
        }}
      >
        <div className="flex items-center gap-3 mb-4">
          <RiskIcon size={24} style={{ color: riskColor }} />
          <div>
            <h3 className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>
              Permission Request
            </h3>
            <p className="text-[11px]" style={{ color: "var(--text-dim)" }}>
              Risk level: <span style={{ color: riskColor }}>{request.risk_level}</span>
            </p>
          </div>
          <button
            onClick={() => onRespond(request.tool_call_id, false)}
            className="ml-auto p-1 rounded"
            style={{ color: "var(--text-dim)" }}
          >
            <X size={16} />
          </button>
        </div>

        <div className="mb-4">
          <div
            className="text-xs font-medium mb-1"
            style={{ color: "var(--text-secondary)" }}
          >
            Tool: <span style={{ color: "var(--accent-cyan)" }}>{request.tool_name}</span>
          </div>
          <pre
            className="text-[11px] p-3 rounded overflow-auto max-h-40"
            style={{
              background: "var(--bg-primary)",
              color: "var(--text-secondary)",
            }}
          >
            {JSON.stringify(request.arguments, null, 2)}
          </pre>
        </div>

        <div className="flex gap-3">
          <button
            onClick={() => onRespond(request.tool_call_id, false)}
            className="flex-1 py-2 rounded text-xs font-medium transition-colors"
            style={{
              background: "var(--bg-hover)",
              color: "var(--accent-red)",
              border: "1px solid var(--accent-red)",
            }}
          >
            Deny
          </button>
          <button
            onClick={() => onRespond(request.tool_call_id, true)}
            className="flex-1 py-2 rounded text-xs font-medium transition-colors"
            style={{
              background: "var(--accent-green)",
              color: "var(--bg-primary)",
            }}
          >
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}
