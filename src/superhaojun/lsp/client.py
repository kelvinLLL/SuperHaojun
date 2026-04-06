"""LSP Client — JSON-RPC 2.0 communication with Language Servers.

Implements the client side of the Language Server Protocol:
- initialize/initialized handshake
- textDocument/didOpen, didChange, didClose
- textDocument/diagnostic, hover, definition, references
- shutdown/exit lifecycle

Uses bare asyncio subprocess for stdio transport.
Reference: Claude Code's services/lsp/ passive integration approach.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Diagnostic:
    """A single diagnostic (error/warning) from the language server."""
    file_path: str
    line: int
    character: int
    severity: int  # 1=Error, 2=Warning, 3=Info, 4=Hint
    message: str
    source: str = ""

    @property
    def severity_str(self) -> str:
        return {1: "error", 2: "warning", 3: "info", 4: "hint"}.get(self.severity, "unknown")


@dataclass(frozen=True)
class HoverInfo:
    """Hover information for a position in a file."""
    contents: str
    line: int
    character: int


@dataclass(frozen=True)
class Location:
    """A code location (file + position)."""
    uri: str
    line: int
    character: int

    @property
    def file_path(self) -> str:
        """Convert file:// URI to local path."""
        if self.uri.startswith("file://"):
            return self.uri[7:]
        return self.uri


@dataclass
class LSPClient:
    """Client for a single Language Server.

    Lifecycle:
        client = LSPClient(command="pyright-langserver", args=["--stdio"])
        await client.start(workspace_root="/path/to/project")
        await client.did_open("/path/to/file.py", "python", content)
        diags = await client.get_diagnostics("/path/to/file.py")
        await client.stop()
    """
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    _process: asyncio.subprocess.Process | None = field(default=None, repr=False)
    _request_id: int = field(default=0, repr=False)
    _pending: dict[int, asyncio.Future] = field(default_factory=dict, repr=False)
    _reader_task: asyncio.Task | None = field(default=None, repr=False)
    _initialized: bool = field(default=False, repr=False)
    _diagnostics: dict[str, list[Diagnostic]] = field(default_factory=dict, repr=False)
    _workspace_root: str = field(default=".", repr=False)

    async def start(self, workspace_root: str = ".") -> None:
        """Spawn the language server and perform initialization."""
        self._workspace_root = workspace_root
        env = {**os.environ, **self.env}
        self._process = await asyncio.create_subprocess_exec(
            self.command, *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        await self._initialize(workspace_root)

    async def stop(self) -> None:
        """Gracefully shut down the language server."""
        if self._initialized:
            try:
                await self._send_request("shutdown", None)
                await self._send_notification("exit", None)
            except Exception:
                pass
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                self._process.kill()
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        self._initialized = False
        self._pending.clear()

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None and self._initialized

    # --- Document lifecycle ---

    async def did_open(self, file_path: str, language_id: str, text: str) -> None:
        """Notify the server that a document was opened."""
        await self._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": self._path_to_uri(file_path),
                "languageId": language_id,
                "version": 1,
                "text": text,
            }
        })

    async def did_change(self, file_path: str, text: str, version: int = 2) -> None:
        """Notify the server of a full document change."""
        await self._send_notification("textDocument/didChange", {
            "textDocument": {
                "uri": self._path_to_uri(file_path),
                "version": version,
            },
            "contentChanges": [{"text": text}],
        })

    async def did_close(self, file_path: str) -> None:
        """Notify the server that a document was closed."""
        await self._send_notification("textDocument/didClose", {
            "textDocument": {"uri": self._path_to_uri(file_path)},
        })

    # --- Intelligence queries ---

    async def get_diagnostics(self, file_path: str) -> list[Diagnostic]:
        """Get cached diagnostics for a file (published by the server)."""
        uri = self._path_to_uri(file_path)
        return list(self._diagnostics.get(uri, []))

    async def hover(self, file_path: str, line: int, character: int) -> HoverInfo | None:
        """Get hover information at a position."""
        result = await self._send_request("textDocument/hover", {
            "textDocument": {"uri": self._path_to_uri(file_path)},
            "position": {"line": line, "character": character},
        })
        if not result:
            return None
        contents = result.get("contents", "")
        if isinstance(contents, dict):
            contents = contents.get("value", str(contents))
        elif isinstance(contents, list):
            contents = "\n".join(
                c.get("value", str(c)) if isinstance(c, dict) else str(c)
                for c in contents
            )
        return HoverInfo(contents=str(contents), line=line, character=character)

    async def definition(self, file_path: str, line: int, character: int) -> list[Location]:
        """Get go-to-definition locations."""
        result = await self._send_request("textDocument/definition", {
            "textDocument": {"uri": self._path_to_uri(file_path)},
            "position": {"line": line, "character": character},
        })
        return self._parse_locations(result)

    async def references(self, file_path: str, line: int, character: int) -> list[Location]:
        """Get all references to the symbol at position."""
        result = await self._send_request("textDocument/references", {
            "textDocument": {"uri": self._path_to_uri(file_path)},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": True},
        })
        return self._parse_locations(result)

    # --- Internal ---

    async def _initialize(self, workspace_root: str) -> None:
        result = await self._send_request("initialize", {
            "processId": os.getpid(),
            "rootUri": self._path_to_uri(workspace_root),
            "capabilities": {
                "textDocument": {
                    "hover": {"contentFormat": ["markdown", "plaintext"]},
                    "publishDiagnostics": {"relatedInformation": True},
                    "definition": {"linkSupport": True},
                    "references": {},
                },
            },
        })
        await self._send_notification("initialized", {})
        self._initialized = True
        logger.info("LSP server initialized: %s", self.command)

    async def _send_request(self, method: str, params: Any) -> Any:
        self._request_id += 1
        req_id = self._request_id
        message = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            message["params"] = params
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[req_id] = future
        self._write(message)
        try:
            return await asyncio.wait_for(future, timeout=30)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"LSP request '{method}' timed out")

    async def _send_notification(self, method: str, params: Any) -> None:
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self._write(message)

    def _write(self, message: dict[str, Any]) -> None:
        """Write an LSP message with Content-Length header."""
        if not self._process or not self._process.stdin:
            raise RuntimeError("LSP server not running")
        body = json.dumps(message, ensure_ascii=False)
        header = f"Content-Length: {len(body.encode('utf-8'))}\r\n\r\n"
        self._process.stdin.write(header.encode("utf-8") + body.encode("utf-8"))

    async def _read_loop(self) -> None:
        """Read LSP messages (Content-Length framed) from stdout."""
        if not self._process or not self._process.stdout:
            return
        reader = self._process.stdout
        try:
            while True:
                # Read headers
                content_length = 0
                while True:
                    line = await reader.readline()
                    if not line:
                        return
                    header = line.decode("utf-8", errors="replace").strip()
                    if not header:
                        break
                    if header.lower().startswith("content-length:"):
                        content_length = int(header.split(":")[1].strip())

                if content_length == 0:
                    continue

                body = await reader.readexactly(content_length)
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    continue

                self._handle_message(data)
        except (asyncio.CancelledError, asyncio.IncompleteReadError):
            pass
        except Exception as exc:
            logger.warning("LSP read loop error: %s", exc)

    def _handle_message(self, data: dict[str, Any]) -> None:
        """Handle an incoming LSP message."""
        req_id = data.get("id")
        if req_id is not None and req_id in self._pending:
            future = self._pending.pop(req_id)
            if "error" in data:
                future.set_exception(RuntimeError(f"LSP error: {data['error']}"))
            else:
                future.set_result(data.get("result"))
        elif data.get("method") == "textDocument/publishDiagnostics":
            self._handle_diagnostics(data.get("params", {}))

    def _handle_diagnostics(self, params: dict[str, Any]) -> None:
        """Cache published diagnostics from the server."""
        uri = params.get("uri", "")
        raw_diags = params.get("diagnostics", [])
        file_path = uri[7:] if uri.startswith("file://") else uri
        self._diagnostics[uri] = [
            Diagnostic(
                file_path=file_path,
                line=d.get("range", {}).get("start", {}).get("line", 0),
                character=d.get("range", {}).get("start", {}).get("character", 0),
                severity=d.get("severity", 1),
                message=d.get("message", ""),
                source=d.get("source", ""),
            )
            for d in raw_diags
            if isinstance(d, dict)
        ]

    @staticmethod
    def _path_to_uri(path: str) -> str:
        """Convert a local path to a file:// URI."""
        abs_path = str(Path(path).resolve())
        return f"file://{abs_path}"

    @staticmethod
    def _parse_locations(result: Any) -> list[Location]:
        if result is None:
            return []
        if isinstance(result, dict):
            result = [result]
        if not isinstance(result, list):
            return []
        locations = []
        for item in result:
            if not isinstance(item, dict):
                continue
            uri = item.get("uri", "")
            rng = item.get("range", {}).get("start", {})
            locations.append(Location(
                uri=uri,
                line=rng.get("line", 0),
                character=rng.get("character", 0),
            ))
        return locations
