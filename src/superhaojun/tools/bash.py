"""Bash tool — execute shell commands."""

from __future__ import annotations

import asyncio
from typing import Any

from .base import Tool

MAX_OUTPUT_SIZE = 100_000  # 100KB limit


class BashTool(Tool):
    """Execute a shell command and return stdout + stderr."""

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command. Returns stdout and stderr. "
            "Use for running scripts, installing packages, git operations, etc."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30)",
                },
            },
            "required": ["command"],
        }

    @property
    def is_concurrent_safe(self) -> bool:
        return False

    @property
    def risk_level(self) -> str:
        return "dangerous"

    async def execute(self, **kwargs: Any) -> str:
        command = kwargs.get("command", "")
        timeout = kwargs.get("timeout", 30)

        if not command:
            return "Error: command parameter is required"

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            return f"Error: command timed out after {timeout}s"
        except Exception as exc:
            return f"Error executing command: {exc}"

        output_parts: list[str] = []
        if stdout:
            decoded = stdout.decode("utf-8", errors="replace")
            if len(decoded) > MAX_OUTPUT_SIZE:
                decoded = decoded[:MAX_OUTPUT_SIZE] + "\n... (output truncated)"
            output_parts.append(decoded)
        if stderr:
            decoded = stderr.decode("utf-8", errors="replace")
            if len(decoded) > MAX_OUTPUT_SIZE:
                decoded = decoded[:MAX_OUTPUT_SIZE] + "\n... (stderr truncated)"
            output_parts.append(f"STDERR:\n{decoded}")

        result = "\n".join(output_parts) if output_parts else "(no output)"

        if proc.returncode != 0:
            result = f"Exit code: {proc.returncode}\n{result}"

        return result
