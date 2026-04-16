"""ManagedLSPClient — crash-resilient wrapper with restart state machine.

v2 addition: Wraps LSPClient with automatic restart on crash.
State machine: stopped → starting → running → crashed → starting (up to max_restarts).
Exponential backoff: 1s, 2s, 4s between restarts.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .client import Diagnostic, HoverInfo, LSPClient, Location

logger = logging.getLogger(__name__)


class LSPState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    CRASHED = "crashed"


@dataclass
class ManagedLSPClient:
    """Crash-resilient LSP client with automatic restart.

    Wraps LSPClient, monitors health, and restarts on failure.
    Max 3 restarts with exponential backoff.
    """
    command: str
    args: list[str] = field(default_factory=list)
    max_restarts: int = 3
    _client: LSPClient | None = field(default=None, repr=False)
    _state: LSPState = field(default=LSPState.STOPPED)
    _restart_count: int = field(default=0, repr=False)
    _workspace_root: str = field(default=".", repr=False)

    @property
    def state(self) -> LSPState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == LSPState.RUNNING and self._client is not None and self._client.is_running

    async def start(self, workspace_root: str = ".") -> None:
        """Start the LSP server."""
        self._workspace_root = workspace_root
        self._state = LSPState.STARTING
        self._client = LSPClient(command=self.command, args=self.args)
        try:
            await self._client.start(workspace_root)
            self._state = LSPState.RUNNING
            self._restart_count = 0
            logger.info("ManagedLSP started: %s", self.command)
        except Exception as exc:
            self._state = LSPState.CRASHED
            logger.warning("ManagedLSP failed to start: %s", exc)
            await self._try_restart()

    async def stop(self) -> None:
        """Stop the LSP server."""
        if self._client:
            try:
                await self._client.stop()
            except Exception:
                pass
            self._client = None
        self._state = LSPState.STOPPED
        self._restart_count = 0

    async def did_open(self, file_path: str, language_id: str, content: str) -> None:
        await self._with_recovery(lambda c: c.did_open(file_path, language_id, content))

    async def did_change(self, file_path: str, content: str) -> None:
        await self._with_recovery(lambda c: c.did_change(file_path, content))

    async def did_close(self, file_path: str) -> None:
        await self._with_recovery(lambda c: c.did_close(file_path))

    async def get_diagnostics(self, file_path: str) -> list[Diagnostic]:
        result = await self._with_recovery(lambda c: c.get_diagnostics(file_path))
        return result if result else []

    def diagnostics_by_file(self) -> dict[str, list[Diagnostic]]:
        if self._client is None:
            return {}
        return self._client.diagnostics_by_file()

    async def hover(self, file_path: str, line: int, character: int) -> HoverInfo | None:
        return await self._with_recovery(lambda c: c.hover(file_path, line, character))

    async def definition(self, file_path: str, line: int, character: int) -> list[Location]:
        result = await self._with_recovery(lambda c: c.definition(file_path, line, character))
        return result if result else []

    async def _with_recovery(self, fn: Any) -> Any:
        """Execute an LSP operation with crash recovery."""
        if self._state != LSPState.RUNNING or self._client is None:
            return None
        try:
            return await fn(self._client)
        except Exception as exc:
            logger.warning("LSP operation failed: %s", exc)
            self._state = LSPState.CRASHED
            await self._try_restart()
            return None

    async def _try_restart(self) -> None:
        """Attempt to restart with exponential backoff."""
        if self._restart_count >= self.max_restarts:
            logger.error("ManagedLSP exhausted %d restart attempts", self.max_restarts)
            self._state = LSPState.CRASHED
            return

        backoff = 2 ** self._restart_count  # 1, 2, 4 seconds
        self._restart_count += 1
        logger.info("ManagedLSP restarting in %ds (attempt %d/%d)",
                     backoff, self._restart_count, self.max_restarts)

        await asyncio.sleep(backoff)

        if self._client:
            try:
                await self._client.stop()
            except Exception:
                pass

        self._state = LSPState.STARTING
        self._client = LSPClient(command=self.command, args=self.args)
        try:
            await self._client.start(self._workspace_root)
            self._state = LSPState.RUNNING
            logger.info("ManagedLSP restarted successfully")
        except Exception as exc:
            self._state = LSPState.CRASHED
            logger.warning("ManagedLSP restart failed: %s", exc)
