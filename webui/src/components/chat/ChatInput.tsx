import { useState, useRef, useEffect } from "react";
import { Send } from "lucide-react";

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
    // Reset textarea height
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

  // Auto-grow textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
    }
  }, [text]);

  return (
    <div
      className="border-t px-4 py-3"
      style={{ borderColor: "var(--border)", background: "var(--bg-secondary)" }}
    >
      <div
        className="flex items-end gap-2 rounded-lg p-2"
        style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border)",
        }}
      >
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? "Agent is working..." : "Type a message... (⌘+Enter to send)"}
          disabled={disabled}
          rows={1}
          className="flex-1 bg-transparent resize-none outline-none text-sm"
          style={{
            color: "var(--text-primary)",
            caretColor: "var(--accent-cyan)",
            minHeight: "24px",
            maxHeight: "200px",
          }}
        />
        <button
          onClick={handleSend}
          disabled={disabled || !text.trim()}
          className="p-1.5 rounded transition-colors shrink-0"
          style={{
            background: text.trim() && !disabled ? "var(--accent-blue)" : "var(--bg-hover)",
            color: text.trim() && !disabled ? "#fff" : "var(--text-dim)",
          }}
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  );
}
