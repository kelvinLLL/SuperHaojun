import { useState, useRef, useEffect, useCallback } from "react";
import { ArrowUp } from "lucide-react";
import { usePanelStore } from "@/stores";
import { SlashMenu } from "./SlashMenu";
import type { CommandInfo } from "@/types";

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [text, setText] = useState("");
  const [showSlash, setShowSlash] = useState(false);
  const [slashFilter, setSlashFilter] = useState("");
  const [slashIndex, setSlashIndex] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const commands = usePanelStore((s) => s.commands);

  const filteredCommands = commands.filter((c) =>
    c.name.startsWith(slashFilter.toLowerCase()),
  );

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
    setShowSlash(false);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleSlashSelect = useCallback((cmd: CommandInfo) => {
    setText(`/${cmd.name} `);
    setShowSlash(false);
    textareaRef.current?.focus();
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (showSlash && filteredCommands.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSlashIndex((i) => Math.min(i + 1, filteredCommands.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSlashIndex((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Tab" || e.key === "Enter") {
        e.preventDefault();
        handleSlashSelect(filteredCommands[slashIndex]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setShowSlash(false);
        return;
      }
    }

    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setText(val);

    // Slash detection: show menu when input starts with / and no space yet (i.e. typing a command name)
    if (val.startsWith("/") && !val.includes(" ") && val.length > 0) {
      setShowSlash(true);
      setSlashFilter(val.slice(1));
      setSlashIndex(0);
    } else {
      setShowSlash(false);
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
    <div className="shrink-0 px-6 pb-5 pt-2">
      <div className="max-w-3xl mx-auto relative">
        {/* Slash command autocomplete */}
        {showSlash && (
          <SlashMenu
            commands={commands}
            filter={slashFilter}
            selectedIndex={slashIndex}
            onSelect={handleSlashSelect}
          />
        )}

        <div
          className="flex items-end gap-2 rounded-2xl px-4 py-3 transition-all duration-200"
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            boxShadow: "0 2px 12px rgba(0,0,0,0.25)",
          }}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = "rgba(122,162,247,0.4)";
            e.currentTarget.style.boxShadow = "0 0 0 3px rgba(122,162,247,0.08), 0 2px 12px rgba(0,0,0,0.25)";
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = "var(--border)";
            e.currentTarget.style.boxShadow = "0 2px 12px rgba(0,0,0,0.25)";
          }}
        >
          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={disabled ? "Thinking..." : "Ask anything... (/ for commands)"}
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
            className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 transition-all duration-200"
            style={{
              background: canSend
                ? "var(--accent-blue)"
                : "var(--bg-hover)",
              color: canSend ? "#fff" : "var(--text-dim)",
              opacity: canSend ? 1 : 0.4,
              cursor: canSend ? "pointer" : "default",
            }}
          >
            <ArrowUp size={14} strokeWidth={2.5} />
          </button>
        </div>
        <p
          className="text-[10px] text-center mt-1.5 select-none"
          style={{ color: "var(--text-dim)", opacity: 0.6 }}
        >
          ⌘+Enter to send
        </p>
      </div>
    </div>
  );
}
