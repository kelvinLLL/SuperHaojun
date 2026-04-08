import { useState, useRef, useEffect } from "react";
import { ArrowUp } from "lucide-react";

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSend();
    }
  };

  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
    }
  }, [text]);

  const canSend = text.trim() && !disabled;

  return (
    <div className="shrink-0 px-6 pb-4 pt-2">
      <div className="max-w-3xl mx-auto">
        <div
          className="flex items-end gap-3 rounded-2xl px-4 py-3 transition-all duration-200"
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            boxShadow: "var(--shadow-lg)",
          }}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = "var(--accent-blue)";
            e.currentTarget.style.boxShadow = "var(--shadow-glow-blue)";
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = "var(--border)";
            e.currentTarget.style.boxShadow = "var(--shadow-lg)";
          }}
        >
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={disabled ? "Generating..." : "Message SuperHaojun..."}
            disabled={disabled}
            rows={1}
            className="flex-1 bg-transparent resize-none outline-none text-sm leading-relaxed"
            style={{
              color: "var(--text-primary)",
              caretColor: "var(--accent-cyan)",
              minHeight: "24px",
              maxHeight: "200px",
            }}
          />
          <button
            onClick={handleSend}
            disabled={!canSend}
            className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0 transition-all duration-200"
            style={{
              background: canSend
                ? "linear-gradient(135deg, var(--accent-blue), var(--accent-cyan))"
                : "var(--bg-hover)",
              color: canSend ? "#fff" : "var(--text-dim)",
              boxShadow: canSend ? "var(--shadow-glow-blue)" : "none",
              cursor: canSend ? "pointer" : "default",
              opacity: canSend ? 1 : 0.5,
            }}
          >
            <ArrowUp size={16} strokeWidth={2.5} />
          </button>
        </div>
        <p
          className="text-[10px] text-center mt-2"
          style={{ color: "var(--text-dim)" }}
        >
          ⌘+Enter to send
        </p>
      </div>
    </div>
  );
}
