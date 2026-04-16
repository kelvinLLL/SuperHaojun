"""Built-in slash commands."""

from __future__ import annotations

from .base import Command, CommandContext


def _refresh_memory_prompt_entry(context: CommandContext) -> None:
    """Refresh prompt memory entry after memory mutations."""
    memory_store = getattr(context, "memory_store", None)
    agent = getattr(context, "agent", None)
    prompt_builder = getattr(agent, "prompt_builder", None)
    if memory_store is None or prompt_builder is None:
        return
    prompt_builder.set_memory_entry(memory_store.build_prompt_entry())


def _invalidate_prompt_builder(context: CommandContext) -> None:
    agent = getattr(context, "agent", None)
    prompt_builder = getattr(agent, "prompt_builder", None)
    if prompt_builder is not None:
        prompt_builder.invalidate()


class HelpCommand(Command):
    @property
    def name(self) -> str:
        return "help"

    @property
    def description(self) -> str:
        return "Show available commands"

    async def execute(self, args: str, context: CommandContext) -> str | None:
        from .registry import CommandRegistry
        # access registry through context.agent — we'll pass it via the context
        registry: CommandRegistry | None = getattr(context, "command_registry", None)
        if registry is None:
            return "No commands registered."
        lines = ["Available commands:"]
        for cmd in sorted(registry.all(), key=lambda c: c.name):
            lines.append(f"  /{cmd.name:12s} {cmd.description}")
        return "\n".join(lines)


class ClearCommand(Command):
    @property
    def name(self) -> str:
        return "clear"

    @property
    def description(self) -> str:
        return "Clear conversation history"

    async def execute(self, args: str, context: CommandContext) -> str | None:
        from ..agent import Agent
        agent: Agent = context.agent  # type: ignore[assignment]
        agent.reset()
        return "Conversation cleared."


class QuitCommand(Command):
    @property
    def name(self) -> str:
        return "quit"

    @property
    def description(self) -> str:
        return "Exit the agent"

    async def execute(self, args: str, context: CommandContext) -> str | None:
        context.should_exit = True
        return "Bye!"


class ExitCommand(Command):
    @property
    def name(self) -> str:
        return "exit"

    @property
    def description(self) -> str:
        return "Exit the agent"

    async def execute(self, args: str, context: CommandContext) -> str | None:
        context.should_exit = True
        return "Bye!"


class MessagesCommand(Command):
    @property
    def name(self) -> str:
        return "messages"

    @property
    def description(self) -> str:
        return "Show number of messages in context"

    async def execute(self, args: str, context: CommandContext) -> str | None:
        from ..agent import Agent
        agent: Agent = context.agent  # type: ignore[assignment]
        return f"Messages in context: {len(agent.messages)}"


class ModelCommand(Command):
    @property
    def name(self) -> str:
        return "model"

    @property
    def description(self) -> str:
        return "Show/switch model (list | <key>)"

    async def execute(self, args: str, context: CommandContext) -> str | None:
        from ..agent import Agent
        from ..config import ModelRegistry

        agent: Agent = context.agent  # type: ignore[assignment]
        registry: ModelRegistry | None = getattr(context, "model_registry", None)
        sub = args.strip()

        # /model  → show current
        if not sub:
            cfg = agent.config
            return f"Model: {cfg.model_id} @ {cfg.base_url} (reasoning={cfg.is_reasoning})"

        # /model list  → show all profiles
        if sub == "list":
            if registry is None:
                return "No model registry configured."
            profiles = registry.list_profiles()
            lines = ["Available models:"]
            for p in profiles:
                marker = " ← active" if p["active"] else ""
                lines.append(f"  {p['key']:20s} {p['name']}{marker}")
            return "\n".join(lines)

        # /model <key>  → switch
        if registry is None:
            return "No model registry configured."
        try:
            new_config = registry.switch(sub)
            agent.switch_model(new_config)
            return f"Switched to: {new_config.model_id}"
        except ValueError as exc:
            return str(exc)


class ToolsCommand(Command):
    @property
    def name(self) -> str:
        return "tools"

    @property
    def description(self) -> str:
        return "List registered tools"

    async def execute(self, args: str, context: CommandContext) -> str | None:
        from ..agent import Agent
        agent: Agent = context.agent  # type: ignore[assignment]
        if len(agent.registry) == 0:
            return "No tools registered."
        lines = ["Registered tools:"]
        for tool_def in agent.registry.to_openai_tools():
            fn = tool_def["function"]
            lines.append(f"  {fn['name']:14s} {fn['description'][:60]}")
        return "\n".join(lines)


class CompactCommand(Command):
    @property
    def name(self) -> str:
        return "compact"

    @property
    def description(self) -> str:
        return "Compact conversation context"

    async def execute(self, args: str, context: CommandContext) -> str | None:
        from ..agent import Agent
        agent: Agent = context.agent  # type: ignore[assignment]
        if not agent.compactor:
            return "No compactor configured."
        result = await agent.compactor.compact(agent.messages)
        if result.removed_count == 0:
            return "Nothing to compact."
        preserved = agent.messages[len(agent.messages) - result.preserved_count:]
        agent.messages.clear()
        agent.messages.extend(result.to_messages())
        agent.messages.extend(preserved)
        if agent.prompt_builder:
            agent.prompt_builder.invalidate()
        return (
            f"Compacted: {result.removed_count} messages removed, "
            f"{result.preserved_count} preserved. "
            f"Tokens: {result.pre_tokens} → {result.post_tokens}"
        )


class SessionCommand(Command):
    """Session management: /session save|load|list|delete [name]."""

    @property
    def name(self) -> str:
        return "session"

    @property
    def description(self) -> str:
        return "Manage sessions (save/load/list/delete)"

    async def execute(self, args: str, context: CommandContext) -> str | None:
        from ..agent import Agent
        from ..session.manager import SessionManager

        agent: Agent = context.agent  # type: ignore[assignment]
        session_mgr: SessionManager | None = getattr(context, "session_manager", None)
        if session_mgr is None:
            return "No session manager configured."

        parts = args.strip().split(None, 1)
        sub = parts[0] if parts else ""
        name = parts[1].strip() if len(parts) > 1 else ""

        if sub == "save":
            if not name:
                return "Usage: /session save <name>"
            info = session_mgr.save(name, agent.messages)
            return f"Session '{name}' saved ({info.message_count} messages)."

        if sub == "load":
            if not name:
                return "Usage: /session load <name>"
            messages = session_mgr.load(name)
            if not messages:
                return f"Session '{name}' not found or empty."
            agent.messages.clear()
            agent.messages.extend(messages)
            return f"Session '{name}' loaded ({len(messages)} messages)."

        if sub == "list":
            sessions = session_mgr.list_sessions()
            if not sessions:
                return "No saved sessions."
            lines = ["Saved sessions:"]
            for s in sessions:
                lines.append(f"  {s.name:20s} {s.message_count} messages")
            return "\n".join(lines)

        if sub == "delete":
            if not name:
                return "Usage: /session delete <name>"
            if session_mgr.delete(name):
                return f"Session '{name}' deleted."
            return f"Session '{name}' not found."

        return "Usage: /session <save|load|list|delete> [name]"


class MemoryCommand(Command):
    """Memory management: /memory add|list|search|delete [args]."""

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return "Manage persistent memory (add/list/search/delete)"

    async def execute(self, args: str, context: CommandContext) -> str | None:
        from ..memory.store import MemoryCategory, MemoryStore

        memory_store: MemoryStore | None = getattr(context, "memory_store", None)
        if memory_store is None:
            return "No memory store configured."

        parts = args.strip().split(None, 1)
        sub = parts[0] if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""

        if sub == "add":
            # /memory add <category> <content>
            add_parts = rest.split(None, 1)
            if len(add_parts) < 2:
                return "Usage: /memory add <user|feedback|project|reference> <content>"
            cat_str, content = add_parts
            try:
                cat = MemoryCategory(cat_str)
            except ValueError:
                return f"Unknown category: {cat_str}. Use: user, feedback, project, reference."
            entry = memory_store.add(cat, content)
            _refresh_memory_prompt_entry(context)
            return f"Memory added [{cat.value}]: {content[:80]}"

        if sub == "list":
            cat = None
            if rest:
                try:
                    cat = MemoryCategory(rest)
                except ValueError:
                    return f"Unknown category: {rest}."
            entries = memory_store.list_entries(cat)
            if not entries:
                return "No memories stored."
            lines = ["Memories:"]
            for e in entries:
                lines.append(f"  [{e.category.value}] {e.content[:60]} (id: {e.entry_id[:8]})")
            return "\n".join(lines)

        if sub == "search":
            if not rest:
                return "Usage: /memory search <query>"
            results = memory_store.search(rest)
            if not results:
                return f"No memories matching '{rest}'."
            lines = [f"Found {len(results)} match(es):"]
            for e in results:
                lines.append(f"  [{e.category.value}] {e.content[:60]}")
            return "\n".join(lines)

        if sub == "delete":
            if not rest:
                return "Usage: /memory delete <entry_id>"
            if memory_store.delete(rest):
                _refresh_memory_prompt_entry(context)
                return "Memory deleted."
            return "Memory entry not found."

        return "Usage: /memory <add|list|search|delete> [args]"


class ExtensionsCommand(Command):
    @property
    def name(self) -> str:
        return "extensions"

    @property
    def description(self) -> str:
        return "List or toggle repo-local extensions"

    async def execute(self, args: str, context: CommandContext) -> str | None:
        extension_runtime = getattr(context, "extension_runtime", None)
        if extension_runtime is None:
            return "No extension runtime configured."

        parts = args.strip().split(None, 1)
        sub = parts[0] if parts else "list"
        value = parts[1] if len(parts) > 1 else ""

        if sub in ("", "list"):
            entries = extension_runtime.list_extensions()
            if not entries:
                return "No repo-local extensions loaded."
            lines = ["Loaded extensions:"]
            for entry in entries:
                status = "enabled" if entry["enabled"] else "disabled"
                lines.append(
                    f"  {entry['id']}  [{status}]  {entry['kind']}  {entry['source']}"
                )
            return "\n".join(lines)

        if sub == "enable":
            if not value:
                return "Usage: /extensions enable <id>"
            if extension_runtime.enable(value):
                _invalidate_prompt_builder(context)
                return f"Extension enabled: {value}"
            return f"Extension not found: {value}"

        if sub == "disable":
            if not value:
                return "Usage: /extensions disable <id>"
            if extension_runtime.disable(value):
                _invalidate_prompt_builder(context)
                return f"Extension disabled: {value}"
            return f"Extension not found: {value}"

        return "Usage: /extensions [list|enable|disable] [id]"
