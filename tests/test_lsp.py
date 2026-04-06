"""Tests for Feature 13: LSP Integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from superhaojun.lsp.client import Diagnostic, HoverInfo, LSPClient, Location
from superhaojun.lsp.service import LSPServerConfig, LSPService


# ---------------------------------------------------------------------------
# Diagnostic
# ---------------------------------------------------------------------------
class TestDiagnostic:
    def test_severity_str(self) -> None:
        d = Diagnostic(file_path="f.py", line=1, character=0, severity=1, message="err")
        assert d.severity_str == "error"
        d2 = Diagnostic(file_path="f.py", line=1, character=0, severity=2, message="warn")
        assert d2.severity_str == "warning"
        d3 = Diagnostic(file_path="f.py", line=1, character=0, severity=3, message="info")
        assert d3.severity_str == "info"
        d4 = Diagnostic(file_path="f.py", line=1, character=0, severity=4, message="hint")
        assert d4.severity_str == "hint"
        d5 = Diagnostic(file_path="f.py", line=1, character=0, severity=99, message="?")
        assert d5.severity_str == "unknown"


class TestHoverInfo:
    def test_fields(self) -> None:
        h = HoverInfo(contents="int", line=5, character=10)
        assert h.contents == "int"
        assert h.line == 5


class TestLocation:
    def test_file_path(self) -> None:
        loc = Location(uri="file:///tmp/test.py", line=0, character=0)
        assert loc.file_path == "/tmp/test.py"

    def test_non_file_uri(self) -> None:
        loc = Location(uri="untitled:test.py", line=0, character=0)
        assert loc.file_path == "untitled:test.py"


# ---------------------------------------------------------------------------
# LSPClient — unit tests (no real process)
# ---------------------------------------------------------------------------
class TestLSPClient:
    def test_not_running_initially(self) -> None:
        client = LSPClient(command="pyright-langserver", args=["--stdio"])
        assert not client.is_running

    def test_path_to_uri(self) -> None:
        uri = LSPClient._path_to_uri("/tmp/test.py")
        assert uri.startswith("file://")
        assert "test.py" in uri

    def test_parse_locations_none(self) -> None:
        assert LSPClient._parse_locations(None) == []

    def test_parse_locations_single(self) -> None:
        result = {"uri": "file:///a.py", "range": {"start": {"line": 5, "character": 3}}}
        locs = LSPClient._parse_locations(result)
        assert len(locs) == 1
        assert locs[0].line == 5

    def test_parse_locations_list(self) -> None:
        result = [
            {"uri": "file:///a.py", "range": {"start": {"line": 1, "character": 0}}},
            {"uri": "file:///b.py", "range": {"start": {"line": 10, "character": 5}}},
        ]
        locs = LSPClient._parse_locations(result)
        assert len(locs) == 2

    def test_parse_locations_invalid(self) -> None:
        assert LSPClient._parse_locations("not a list") == []

    def test_handle_diagnostics(self) -> None:
        client = LSPClient(command="test")
        params = {
            "uri": "file:///tmp/test.py",
            "diagnostics": [
                {
                    "range": {"start": {"line": 5, "character": 0}, "end": {"line": 5, "character": 10}},
                    "severity": 1,
                    "message": "undefined name 'x'",
                    "source": "pyright",
                },
                {
                    "range": {"start": {"line": 10, "character": 0}, "end": {"line": 10, "character": 5}},
                    "severity": 2,
                    "message": "unused import",
                    "source": "pyright",
                },
            ],
        }
        client._handle_diagnostics(params)
        uri = "file:///tmp/test.py"
        assert uri in client._diagnostics
        assert len(client._diagnostics[uri]) == 2
        assert client._diagnostics[uri][0].severity == 1
        assert client._diagnostics[uri][0].message == "undefined name 'x'"

    def test_handle_message_response(self) -> None:
        """Test that _handle_message resolves pending futures."""
        import asyncio
        loop = asyncio.new_event_loop()
        client = LSPClient(command="test")
        future = loop.create_future()
        client._pending[42] = future
        client._handle_message({"id": 42, "result": {"key": "value"}})
        assert future.done()
        assert future.result() == {"key": "value"}
        loop.close()

    def test_handle_message_error(self) -> None:
        import asyncio
        loop = asyncio.new_event_loop()
        client = LSPClient(command="test")
        future = loop.create_future()
        client._pending[1] = future
        client._handle_message({"id": 1, "error": {"code": -1, "message": "bad"}})
        assert future.done()
        with pytest.raises(RuntimeError, match="LSP error"):
            future.result()
        loop.close()


# ---------------------------------------------------------------------------
# LSPServerConfig
# ---------------------------------------------------------------------------
class TestLSPServerConfig:
    def test_defaults(self) -> None:
        cfg = LSPServerConfig(language_id="python", command="pyright")
        assert cfg.language_id == "python"
        assert cfg.args == []
        assert cfg.file_patterns == []


# ---------------------------------------------------------------------------
# LSPService
# ---------------------------------------------------------------------------
class TestLSPService:
    def test_add_server(self) -> None:
        service = LSPService()
        service.add_server(LSPServerConfig("python", "pyright", ["--stdio"]))
        assert "python" in service._servers

    def test_detect_language(self) -> None:
        service = LSPService()
        assert service._detect_language("test.py") == "python"
        assert service._detect_language("test.ts") == "typescript"
        assert service._detect_language("test.tsx") == "typescriptreact"
        assert service._detect_language("test.rs") == "rust"
        assert service._detect_language("test.unknown") == "plaintext"

    def test_to_prompt_context_empty(self) -> None:
        service = LSPService()
        assert service.to_prompt_context() == ""

    def test_to_prompt_context_with_clients(self) -> None:
        service = LSPService()
        # Manually inject a fake client with diagnostics
        client = LSPClient(command="test")
        client._initialized = True
        client._process = None  # Will make is_running False
        client._diagnostics = {
            "file:///test.py": [
                Diagnostic("test.py", 1, 0, 1, "undefined 'x'"),
                Diagnostic("test.py", 5, 0, 2, "unused import"),
            ]
        }
        service._clients["python"] = client
        text = service.to_prompt_context()
        assert "LSP Context" in text
        assert "python" in text
        assert "2 diagnostics" in text
        assert "ERROR" in text  # Should show the error diagnostic

    def test_get_client(self) -> None:
        service = LSPService()
        assert service.get_client("python") is None
        client = LSPClient(command="test")
        service._clients["python"] = client
        assert service.get_client("python") is client

    @pytest.mark.asyncio
    async def test_get_diagnostics_no_client(self) -> None:
        service = LSPService()
        diags = await service.get_diagnostics("test.py")
        assert diags == []

    @pytest.mark.asyncio
    async def test_hover_no_client(self) -> None:
        service = LSPService()
        result = await service.hover("test.py", 0, 0)
        assert result is None

    @pytest.mark.asyncio
    async def test_definition_no_client(self) -> None:
        service = LSPService()
        result = await service.definition("test.py", 0, 0)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_all_diagnostics(self) -> None:
        service = LSPService()
        client = LSPClient(command="test")
        client._diagnostics = {
            "file:///a.py": [Diagnostic("a.py", 1, 0, 1, "err1")],
            "file:///b.py": [Diagnostic("b.py", 2, 0, 2, "warn1")],
        }
        service._clients["python"] = client
        all_diags = await service.get_all_diagnostics()
        assert len(all_diags) == 2

    @pytest.mark.asyncio
    async def test_stop_all_empty(self) -> None:
        service = LSPService()
        await service.stop_all()  # Should not raise
