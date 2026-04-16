"""LSP Service — high-level API coordinating LSP clients for the agent.

Manages multiple language server connections and provides aggregated
code intelligence to inject into the prompt context.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .client import Diagnostic, HoverInfo, Location
from .diagnostics import DiagnosticRegistry
from .managed import ManagedLSPClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LSPServerConfig:
    """Configuration for a language server."""
    language_id: str
    command: str
    args: list[str] = field(default_factory=list)
    file_patterns: list[str] = field(default_factory=list)  # e.g. ["*.py", "*.pyi"]


@dataclass
class LSPService:
    """Manages LSP clients and provides aggregated code intelligence.

    Usage:
        service = LSPService()
        service.add_server(LSPServerConfig("python", "pyright-langserver", ["--stdio"], ["*.py"]))
        await service.start_all("/path/to/workspace")
        diagnostics = await service.get_all_diagnostics()
        context_text = service.to_prompt_context()
        await service.stop_all()
    """
    _servers: dict[str, LSPServerConfig] = field(default_factory=dict)
    _clients: dict[str, ManagedLSPClient] = field(default_factory=dict)
    _diagnostics: DiagnosticRegistry = field(default_factory=DiagnosticRegistry)
    _workspace_root: str = "."

    def add_server(self, config: LSPServerConfig) -> None:
        """Register a language server configuration."""
        self._servers[config.language_id] = config

    async def start_all(self, workspace_root: str = ".") -> None:
        """Start all configured language servers."""
        self._workspace_root = workspace_root
        for lang_id, config in self._servers.items():
            try:
                client = ManagedLSPClient(command=config.command, args=config.args)
                await client.start(workspace_root)
                self._clients[lang_id] = client
                logger.info("LSP server started: %s (%s)", lang_id, config.command)
            except Exception as exc:
                logger.warning("Failed to start LSP server %s: %s", lang_id, exc)

    async def stop_all(self) -> None:
        """Stop all running language servers."""
        for lang_id, client in list(self._clients.items()):
            try:
                await client.stop()
            except Exception as exc:
                logger.warning("Error stopping LSP server %s: %s", lang_id, exc)
        self._clients.clear()
        self._diagnostics.clear_all()

    def get_client(self, language_id: str) -> ManagedLSPClient | None:
        """Get the LSP client for a language."""
        return self._clients.get(language_id)

    async def open_file(self, file_path: str, content: str | None = None) -> None:
        """Open a file in the appropriate language server."""
        lang_id = self._detect_language(file_path)
        client = self._clients.get(lang_id)
        if not client:
            return
        if content is None:
            try:
                content = Path(file_path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                return
        await client.did_open(file_path, lang_id, content)

    async def get_diagnostics(self, file_path: str) -> list[Diagnostic]:
        """Get diagnostics for a specific file."""
        lang_id = self._detect_language(file_path)
        client = self._clients.get(lang_id)
        if not client:
            return []
        diags = await client.get_diagnostics(file_path)
        self._diagnostics.update_file(file_path, lang_id, diags)
        return diags

    async def get_all_diagnostics(self) -> list[Diagnostic]:
        """Get all cached diagnostics from all servers."""
        self._refresh_diagnostics()
        return [
            Diagnostic(
                file_path=d.file_path,
                line=d.line,
                character=d.character,
                severity=d.severity,
                message=d.message,
                source=d.provider,
            )
            for d in self._diagnostics.get_all()
        ]

    async def hover(self, file_path: str, line: int, character: int) -> HoverInfo | None:
        """Get hover info at a position."""
        lang_id = self._detect_language(file_path)
        client = self._clients.get(lang_id)
        if not client:
            return None
        return await client.hover(file_path, line, character)

    async def definition(self, file_path: str, line: int, character: int) -> list[Location]:
        """Get definition locations."""
        lang_id = self._detect_language(file_path)
        client = self._clients.get(lang_id)
        if not client:
            return []
        return await client.definition(file_path, line, character)

    def to_prompt_context(self) -> str:
        """Produce a text summary of LSP state for prompt injection.

        Includes active servers and diagnostic counts.
        """
        if not self._clients:
            return ""
        self._refresh_diagnostics()
        lines = ["## LSP Context"]
        for lang_id, client in self._clients.items():
            status = "running" if client.is_running else "stopped"
            lines.append(f"- {lang_id}: {status}")
        diag_ctx = self._diagnostics.to_prompt_context()
        if diag_ctx:
            lines.append("")
            lines.extend(diag_ctx.splitlines())
        return "\n".join(lines)

    def _refresh_diagnostics(self) -> None:
        """Rebuild the diagnostic registry from managed client snapshots."""
        self._diagnostics.clear_all()
        for lang_id, client in self._clients.items():
            for file_path, diags in client.diagnostics_by_file().items():
                self._diagnostics.update_file(file_path, lang_id, diags)

    def _detect_language(self, file_path: str) -> str:
        """Detect language ID from file extension."""
        ext = Path(file_path).suffix.lower()
        ext_map = {
            ".py": "python", ".pyi": "python",
            ".js": "javascript", ".jsx": "javascriptreact",
            ".ts": "typescript", ".tsx": "typescriptreact",
            ".rs": "rust", ".go": "go",
            ".java": "java", ".c": "c", ".cpp": "cpp",
            ".rb": "ruby", ".sh": "shellscript",
        }
        return ext_map.get(ext, "plaintext")
