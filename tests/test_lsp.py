"""Tests for LSP v2 — DiagnosticRegistry, ManagedLSPClient, LSPService."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from superhaojun.lsp.client import Diagnostic, HoverInfo, LSPClient, Location
from superhaojun.lsp.diagnostics import DiagnosticRegistry, DiagnosticSource
from superhaojun.lsp.managed import LSPState, ManagedLSPClient
from superhaojun.lsp.service import LSPService, LSPServerConfig


# ── DiagnosticSource ──


class TestDiagnosticSource:
    def test_dedup_key(self):
        d = DiagnosticSource(provider="lsp:py", file_path="a.py", line=10, character=0, message="err")
        assert d.dedup_key == ("a.py", 10, "err")

    def test_frozen(self):
        d = DiagnosticSource(provider="lsp:py", file_path="a.py", line=0, character=0, message="x")
        with pytest.raises(AttributeError):
            d.provider = "changed"  # type: ignore[misc]


# ── DiagnosticRegistry ──


class TestDiagnosticRegistry:
    def _diag(self, line=0, msg="error", severity=1):
        return Diagnostic(file_path="a.py", line=line, character=0, severity=severity, message=msg, source="test")

    def test_empty(self):
        reg = DiagnosticRegistry()
        assert reg.get_all() == []
        assert reg.total_count == 0

    def test_update_file(self):
        reg = DiagnosticRegistry()
        reg.update_file("a.py", "lsp:py", [self._diag(0, "e1"), self._diag(1, "e2")])
        assert len(reg.get_file("a.py")) == 2
        assert reg.total_count == 2

    def test_deduplication(self):
        reg = DiagnosticRegistry()
        reg.update_file("a.py", "lsp:py", [self._diag(0, "same")])
        reg.update_file("a.py", "hook:lint", [self._diag(0, "same")])  # duplicate
        assert len(reg.get_file("a.py")) == 1

    def test_different_lines_no_dedup(self):
        reg = DiagnosticRegistry()
        reg.update_file("a.py", "lsp:py", [self._diag(0, "e1")])
        reg.inject("a.py", "hook:lint", line=5, message="e2")
        assert len(reg.get_file("a.py")) == 2

    def test_inject(self):
        reg = DiagnosticRegistry()
        reg.inject("b.py", "hook:lint", line=10, message="lint error")
        diags = reg.get_file("b.py")
        assert len(diags) == 1
        assert diags[0].provider == "hook:lint"

    def test_get_errors(self):
        reg = DiagnosticRegistry()
        reg.update_file("a.py", "lsp", [
            self._diag(0, "error", severity=1),
            self._diag(1, "warning", severity=2),
        ])
        errors = reg.get_errors("a.py")
        assert len(errors) == 1
        assert errors[0].message == "error"

    def test_get_errors_all_files(self):
        reg = DiagnosticRegistry()
        reg.update_file("a.py", "lsp", [self._diag(0, "e1")])
        reg.update_file("b.py", "lsp", [self._diag(0, "e2")])
        errors = reg.get_errors()
        assert len(errors) == 2

    def test_clear_file(self):
        reg = DiagnosticRegistry()
        reg.update_file("a.py", "lsp", [self._diag(0, "e1")])
        reg.clear_file("a.py")
        assert reg.get_file("a.py") == []
        assert reg.total_count == 0

    def test_clear_all(self):
        reg = DiagnosticRegistry()
        reg.update_file("a.py", "lsp", [self._diag()])
        reg.update_file("b.py", "lsp", [self._diag(0, "e2")])  # different msg to avoid dedup
        reg.clear_all()
        assert reg.get_all() == []

    def test_replace_provider(self):
        """Updating same file+provider replaces old diagnostics."""
        reg = DiagnosticRegistry()
        reg.update_file("a.py", "lsp:py", [self._diag(0, "old")])
        reg.update_file("a.py", "lsp:py", [self._diag(0, "new")])
        diags = reg.get_file("a.py")
        assert len(diags) == 1
        assert diags[0].message == "new"

    def test_to_prompt_context_empty(self):
        reg = DiagnosticRegistry()
        assert reg.to_prompt_context() == ""

    def test_to_prompt_context_with_errors(self):
        reg = DiagnosticRegistry()
        reg.update_file("a.py", "lsp", [self._diag(0, "syntax error")])
        ctx = reg.to_prompt_context()
        assert "ERROR" in ctx
        assert "syntax error" in ctx

    def test_to_prompt_context_max_errors(self):
        reg = DiagnosticRegistry()
        for i in range(15):
            reg.inject("a.py", "lsp", line=i, message=f"error {i}")
        ctx = reg.to_prompt_context(max_errors=5)
        assert "... and 10 more errors" in ctx


# ── ManagedLSPClient ──


class TestManagedLSPClient:
    def test_initial_state(self):
        m = ManagedLSPClient(command="pyright", args=["--stdio"])
        assert m.state == LSPState.STOPPED
        assert m.is_running is False

    async def test_start_success(self):
        m = ManagedLSPClient(command="pyright")
        with patch.object(LSPClient, "start", new_callable=AsyncMock):
            await m.start("/workspace")
        assert m.state == LSPState.RUNNING

    async def test_start_failure_triggers_restart(self):
        m = ManagedLSPClient(command="pyright", max_restarts=1)
        call_count = 0
        async def mock_start(ws):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RuntimeError("crash")
        with patch.object(LSPClient, "start", side_effect=mock_start), \
             patch.object(LSPClient, "stop", new_callable=AsyncMock), \
             patch("superhaojun.lsp.managed.asyncio.sleep", new_callable=AsyncMock):
            await m.start("/workspace")
        assert m.state == LSPState.CRASHED
        assert call_count == 2  # initial + 1 restart

    async def test_stop(self):
        m = ManagedLSPClient(command="pyright")
        with patch.object(LSPClient, "start", new_callable=AsyncMock):
            await m.start("/workspace")
        with patch.object(LSPClient, "stop", new_callable=AsyncMock):
            await m.stop()
        assert m.state == LSPState.STOPPED

    async def test_did_open(self):
        m = ManagedLSPClient(command="pyright")
        with patch.object(LSPClient, "start", new_callable=AsyncMock):
            await m.start("/workspace")
            m._state = LSPState.RUNNING
        with patch.object(LSPClient, "did_open", new_callable=AsyncMock) as mock_open:
            await m.did_open("a.py", "python", "x = 1")
            mock_open.assert_called_once_with("a.py", "python", "x = 1")

    async def test_did_change(self):
        m = ManagedLSPClient(command="pyright")
        with patch.object(LSPClient, "start", new_callable=AsyncMock):
            await m.start("/workspace")
            m._state = LSPState.RUNNING
        with patch.object(LSPClient, "did_change", new_callable=AsyncMock) as mock_change:
            await m.did_change("a.py", "x = 2")
            mock_change.assert_called_once()

    async def test_operation_on_stopped_returns_none(self):
        m = ManagedLSPClient(command="pyright")
        result = await m.get_diagnostics("a.py")
        assert result == []

    async def test_crash_recovery_on_operation(self):
        m = ManagedLSPClient(command="pyright", max_restarts=1)
        with patch.object(LSPClient, "start", new_callable=AsyncMock):
            await m.start("/workspace")
            m._state = LSPState.RUNNING

        # Simulate crash during get_diagnostics
        with patch.object(LSPClient, "get_diagnostics", new_callable=AsyncMock, side_effect=RuntimeError("dead")), \
             patch.object(LSPClient, "start", new_callable=AsyncMock), \
             patch.object(LSPClient, "stop", new_callable=AsyncMock), \
             patch("superhaojun.lsp.managed.asyncio.sleep", new_callable=AsyncMock):
            result = await m.get_diagnostics("a.py")
        assert result == []

    async def test_max_restarts_exhausted(self):
        m = ManagedLSPClient(command="pyright", max_restarts=0)
        with patch.object(LSPClient, "start", new_callable=AsyncMock, side_effect=RuntimeError("crash")):
            await m.start("/workspace")
        assert m.state == LSPState.CRASHED


# ── LSPServerConfig ──


class TestLSPServerConfig:
    def test_creation(self):
        cfg = LSPServerConfig(language_id="python", command="pyright", args=["--stdio"])
        assert cfg.language_id == "python"

    def test_frozen(self):
        cfg = LSPServerConfig(language_id="python", command="pyright")
        with pytest.raises(AttributeError):
            cfg.command = "other"  # type: ignore[misc]


# ── LSPService ──


class TestLSPService:
    def test_add_server(self):
        svc = LSPService()
        svc.add_server(LSPServerConfig("python", "pyright", ["--stdio"], ["*.py"]))
        assert "python" in svc._servers

    async def test_start_stop_all(self):
        svc = LSPService()
        svc.add_server(LSPServerConfig("python", "pyright", ["--stdio"]))
        with patch.object(LSPClient, "start", new_callable=AsyncMock):
            await svc.start_all("/workspace")
        assert "python" in svc._clients
        with patch.object(LSPClient, "stop", new_callable=AsyncMock):
            await svc.stop_all()
        assert len(svc._clients) == 0

    def test_detect_language(self):
        svc = LSPService()
        assert svc._detect_language("test.py") == "python"
        assert svc._detect_language("test.ts") == "typescript"
        assert svc._detect_language("test.unknown") == "plaintext"

    async def test_get_diagnostics_no_client(self):
        svc = LSPService()
        diags = await svc.get_diagnostics("test.py")
        assert diags == []

    def test_to_prompt_context_empty(self):
        svc = LSPService()
        assert svc.to_prompt_context() == ""

    async def test_hover_no_client(self):
        svc = LSPService()
        result = await svc.hover("test.py", 0, 0)
        assert result is None

    async def test_definition_no_client(self):
        svc = LSPService()
        result = await svc.definition("test.py", 0, 0)
        assert result == []
