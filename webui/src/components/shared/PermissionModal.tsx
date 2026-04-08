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

const RISK_CONFIG: Record<string, { color: string; bg: string }> = {
  read: { color: "var(--accent-green)", bg: "rgba(158, 206, 106, 0.1)" },
  write: { color: "var(--accent-yellow)", bg: "rgba(224, 175, 104, 0.1)" },
  dangerous: { color: "var(--accent-red)", bg: "rgba(247, 118, 142, 0.1)" },
};

export function PermissionModal({ request, onRespond }: PermissionModalProps) {
  const risk = RISK_CONFIG[request.risk_level] || RISK_CONFIG.write;
  const RiskIcon = request.risk_level === "dangerous" ? ShieldAlert :
                   request.risk_level === "write" ? Shield : ShieldCheck;

  return (
    <div className="fixed inset-0 flex items-center justify-center z-50 animate-fade-in">
      <div
        className="absolute inset-0"
        style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(8px)" }}
        onClick={() => onRespond(request.tool_call_id, false)}
      />

      <div
        className="relative rounded-2xl p-6 max-w-md w-full mx-4 animate-slide-up"
        style={{
          background: "var(--bg-elevated)",
          border: "1px solid var(--border)",
          boxShadow: "var(--shadow-lg)",
        }}
      >
        <div className="flex items-start gap-3 mb-5">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: risk.bg }}
          >
            <RiskIcon size={20} style={{ color: risk.color }} />
          </div>
          <div className="flex-1">
            <h3 className="font-semibold text-sm mb-0.5" style={{ color: "var(--text-primary)" }}>
              Permission Required
            </h3>
            <div className="flex items-center gap-2">
              <span
                className="text-[10px] font-medium px-2 py-0.5 rounded-full uppercase tracking-wider"
                style={{ background: risk.bg, color: risk.color }}
              >
                {request.risk_level}
              </span>
            </div>
          </div>
          <button
            onClick={() => onRespond(request.tool_call_id, false)}
            className="p-1.5 rounded-lg transition-colors"
            style={{ color: "var(--text-dim)" }}
          >
            <X size={16} />
          </button>
        </div>

        <div className="mb-5">
          <div className="text-xs mb-2" style={{ color: "var(--text-dim)" }}>
            Tool: <span className="font-medium" style={{ color: "var(--accent-cyan)" }}>{request.tool_name}</span>
          </div>
          <pre
            className="text-[12px] p-3 rounded-xl overflow-auto max-h-40 font-mono"
            style={{
              background: "var(--bg-secondary)",
              color: "var(--text-secondary)",
              border: "none",
              margin: 0,
            }}
          >
            {JSON.stringify(request.arguments, null, 2)}
          </pre>
        </div>

        <div className="flex gap-3">
          <button
            onClick={() => onRespond(request.tool_call_id, false)}
            className="flex-1 py-2.5 rounded-xl text-xs font-semibold transition-all duration-200 btn-hover"
            style={{
              background: "transparent",
              color: "var(--text-secondary)",
              border: "1px solid var(--border)",
            }}
          >
            Deny
          </button>
          <button
            onClick={() => onRespond(request.tool_call_id, true)}
            className="flex-1 py-2.5 rounded-xl text-xs font-semibold transition-all duration-200 btn-hover"
            style={{
              background: "linear-gradient(135deg, var(--accent-green), var(--accent-teal))",
              color: "#fff",
              border: "none",
              boxShadow: "0 0 12px rgba(158, 206, 106, 0.2)",
            }}
          >
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}
