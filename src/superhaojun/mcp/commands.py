"""MCP slash command — /mcp list|enable|disable|reconnect|tools."""

from __future__ import annotations

from .config import MCPServerApproval
from ..commands.base import Command, CommandContext


class MCPCommand(Command):
    @property
    def name(self) -> str:
        return "mcp"

    @property
    def description(self) -> str:
        return (
            "Manage MCP servers: /mcp list|set-approval|approve|deny|enable|disable|"
            "reconnect|tools <name>"
        )

    async def execute(self, args: str, context: CommandContext) -> str | None:
        manager = getattr(context, "mcp_manager", None)
        if manager is None:
            return "MCP not configured."

        parts = args.strip().split(None, 1)
        subcmd = parts[0] if parts else "list"
        target = parts[1].strip() if len(parts) > 1 else ""

        if subcmd == "list":
            statuses = manager.get_status()
            if not statuses:
                return "No MCP servers configured."
            lines = ["MCP Servers:"]
            for s in statuses:
                lines.append(
                    f"  {s['name']:20s} {s['status']:10s} "
                    f"transport={s['transport']}  tools={s['tools_count']}  "
                    f"scope={s['scope']}  approval={s['approval']}"
                    + (f"  error={s['error']}" if s['error'] else "")
                )
            return "\n".join(lines)

        if subcmd == "approve":
            if not target:
                return "Usage: /mcp approve <server-name>"
            ok = await manager.approve(target)
            return f"Approved '{target}'." if ok else f"Server '{target}' not found."

        if subcmd == "deny":
            if not target:
                return "Usage: /mcp deny <server-name>"
            ok = await manager.deny(target)
            return f"Denied '{target}'." if ok else f"Server '{target}' not found."

        if subcmd == "set-approval":
            if not target:
                return "Usage: /mcp set-approval <server-name> <approved|pending|denied>"
            target_parts = target.split(None, 1)
            if len(target_parts) < 2:
                return "Usage: /mcp set-approval <server-name> <approved|pending|denied>"
            server_name, approval_name = target_parts
            try:
                approval = MCPServerApproval(approval_name.lower())
            except ValueError:
                return (
                    f"Invalid approval '{approval_name}'. "
                    "Use: approved, pending, denied."
                )
            ok = await manager.set_approval(server_name, approval)
            return (
                f"Set approval for '{server_name}' to {approval.value}."
                if ok
                else f"Server '{server_name}' not found."
            )

        if subcmd == "enable":
            if not target:
                return "Usage: /mcp enable <server-name>"
            ok = await manager.enable(target)
            if ok:
                return f"Enabled '{target}'."
            statuses = {s["name"]: s for s in manager.get_status()}
            status = statuses.get(target)
            if status and status["approval"] != "approved":
                return (
                    f"Cannot enable '{target}': approval={status['approval']}. "
                    "Use /mcp approve first."
                )
            return f"Failed to enable '{target}'."

        if subcmd == "disable":
            if not target:
                return "Usage: /mcp disable <server-name>"
            ok = await manager.disable(target)
            return f"Disabled '{target}'." if ok else f"Server '{target}' not found."

        if subcmd == "reconnect":
            if not target:
                return "Usage: /mcp reconnect <server-name>"
            ok = await manager.reconnect(target)
            return f"Reconnected '{target}'." if ok else f"Failed to reconnect '{target}'."

        if subcmd == "tools":
            if target:
                tools = manager.get_server_tools(target)
                if not tools:
                    return f"No tools for server '{target}' (not running or not found)."
                lines = [f"Tools from '{target}':"]
                for t in tools:
                    lines.append(f"  {t.name:30s} {t.description[:60]}")
                return "\n".join(lines)
            else:
                tools = manager.list_all_tools()
                if not tools:
                    return "No MCP tools available."
                lines = ["All MCP tools:"]
                for t in tools:
                    lines.append(f"  {t.name:30s} {t.description[:60]}")
                return "\n".join(lines)

        return (
            "Unknown subcommand: "
            f"{subcmd}. Use: list, set-approval, approve, deny, enable, disable, reconnect, tools"
        )
