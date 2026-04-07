"""Tests for MCP v2 — config, MCPManager, MCPCommand."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from superhaojun.mcp.config import MCPServerConfig, MCPServerStatus, load_mcp_configs
from superhaojun.mcp.client import MCPClient, MCPToolInfo
from superhaojun.mcp.adapter import MCPToolAdapter
from superhaojun.mcp.manager import MCPManager, MCPServerState
from superhaojun.mcp.commands import MCPCommand
from superhaojun.commands.base import CommandContext


# ── MCPServerConfig ──


class TestMCPServerConfig:
    def test_defaults(self):
        cfg = MCPServerConfig(name="test")
        assert cfg.transport == "stdio"
        assert cfg.enabled is True
        assert cfg.scope == "project"

    def test_sse_transport(self):
        cfg = MCPServerConfig(name="web", transport="sse", url="http://localhost:3001/sse")
        assert cfg.url == "http://localhost:3001/sse"

    def test_frozen(self):
        cfg = MCPServerConfig(name="test")
        with pytest.raises(AttributeError):
            cfg.name = "changed"  # type: ignore[misc]


# ── Multi-scope config loading ──


class TestLoadMCPConfigs:
    def test_load_project_only(self, tmp_path):
        p = tmp_path / "mcp.json"
        p.write_text(json.dumps({"servers": [{"name": "fs", "command": "npx"}]}))
        configs = load_mcp_configs(project_path=p)
        assert len(configs) == 1
        assert configs[0].name == "fs"
        assert configs[0].scope == "project"

    def test_load_user_only(self, tmp_path):
        u = tmp_path / "user_mcp.json"
        u.write_text(json.dumps({"servers": [{"name": "global", "command": "mcp-server"}]}))
        configs = load_mcp_configs(user_path=u)
        assert len(configs) == 1
        assert configs[0].scope == "user"

    def test_project_overrides_user(self, tmp_path):
        u = tmp_path / "user.json"
        u.write_text(json.dumps({"servers": [
            {"name": "fs", "command": "old-cmd"},
            {"name": "user-only", "command": "cmd2"},
        ]}))
        p = tmp_path / "project.json"
        p.write_text(json.dumps({"servers": [
            {"name": "fs", "command": "new-cmd"},
        ]}))
        configs = load_mcp_configs(project_path=p, user_path=u)
        by_name = {c.name: c for c in configs}
        assert by_name["fs"].command == "new-cmd"
        assert by_name["fs"].scope == "project"
        assert "user-only" in by_name

    def test_load_missing_file(self, tmp_path):
        configs = load_mcp_configs(project_path=tmp_path / "nope.json")
        assert configs == []

    def test_load_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json")
        configs = load_mcp_configs(project_path=p)
        assert configs == []

    def test_load_no_paths(self):
        configs = load_mcp_configs()
        assert configs == []


# ── MCPServerStatus ──


class TestMCPServerStatus:
    def test_values(self):
        assert MCPServerStatus.STOPPED == "stopped"
        assert MCPServerStatus.RUNNING == "running"
        assert MCPServerStatus.ERROR == "error"
        assert MCPServerStatus.DISABLED == "disabled"


# ── MCPManager ──


class TestMCPManager:
    def _make_config(self, name="test", enabled=True):
        return MCPServerConfig(name=name, command="echo", enabled=enabled)

    def test_load_configs(self):
        mgr = MCPManager()
        mgr.load_configs([self._make_config("a"), self._make_config("b")])
        status = mgr.get_status()
        assert len(status) == 2

    def test_load_disabled(self):
        mgr = MCPManager()
        mgr.load_configs([self._make_config("a", enabled=False)])
        status = mgr.get_status()
        assert status[0]["status"] == "disabled"

    async def test_start_all(self):
        mgr = MCPManager()
        mgr.load_configs([self._make_config("a")])
        with patch.object(MCPClient, "start", new_callable=AsyncMock) as mock_start, \
             patch.object(MCPClient, "list_tools", new_callable=AsyncMock, return_value=[]):
            await mgr.start_all()
            mock_start.assert_called_once()
        status = mgr.get_status()
        assert status[0]["status"] == "running"

    async def test_stop_all(self):
        mgr = MCPManager()
        mgr.load_configs([self._make_config("a")])
        with patch.object(MCPClient, "start", new_callable=AsyncMock), \
             patch.object(MCPClient, "list_tools", new_callable=AsyncMock, return_value=[]):
            await mgr.start_all()
        with patch.object(MCPClient, "stop", new_callable=AsyncMock):
            await mgr.stop_all()
        status = mgr.get_status()
        assert status[0]["status"] == "stopped"

    async def test_enable(self):
        mgr = MCPManager()
        mgr.load_configs([self._make_config("a", enabled=False)])
        with patch.object(MCPClient, "start", new_callable=AsyncMock), \
             patch.object(MCPClient, "list_tools", new_callable=AsyncMock, return_value=[]):
            ok = await mgr.enable("a")
        assert ok is True

    async def test_enable_nonexistent(self):
        mgr = MCPManager()
        ok = await mgr.enable("nope")
        assert ok is False

    async def test_disable(self):
        mgr = MCPManager()
        mgr.load_configs([self._make_config("a")])
        with patch.object(MCPClient, "start", new_callable=AsyncMock), \
             patch.object(MCPClient, "list_tools", new_callable=AsyncMock, return_value=[]):
            await mgr.start_all()
        with patch.object(MCPClient, "stop", new_callable=AsyncMock):
            ok = await mgr.disable("a")
        assert ok is True
        assert mgr.get_status()[0]["status"] == "disabled"

    async def test_reconnect(self):
        mgr = MCPManager()
        mgr.load_configs([self._make_config("a")])
        with patch.object(MCPClient, "start", new_callable=AsyncMock), \
             patch.object(MCPClient, "list_tools", new_callable=AsyncMock, return_value=[]), \
             patch.object(MCPClient, "stop", new_callable=AsyncMock):
            await mgr.start_all()
            ok = await mgr.reconnect("a")
        assert ok is True
        assert mgr.get_status()[0]["status"] == "running"

    async def test_start_error(self):
        mgr = MCPManager()
        mgr.load_configs([self._make_config("a")])
        with patch.object(MCPClient, "start", new_callable=AsyncMock, side_effect=RuntimeError("fail")), \
             patch.object(MCPClient, "stop", new_callable=AsyncMock):
            await mgr.start_all()
        status = mgr.get_status()
        assert status[0]["status"] == "error"
        assert "fail" in status[0]["error"]

    def test_get_server_tools(self):
        mgr = MCPManager()
        mgr.load_configs([self._make_config("a")])
        assert mgr.get_server_tools("a") == []
        assert mgr.get_server_tools("nope") == []

    async def test_tool_registration(self):
        mock_registry = MagicMock()
        mock_registry.register = MagicMock()
        mock_registry.unregister = MagicMock()

        mgr = MCPManager()
        mgr.set_tool_registry(mock_registry)
        mgr.load_configs([self._make_config("a")])

        tool_info = MCPToolInfo(name="read", description="Read file", input_schema={"type": "object"})
        with patch.object(MCPClient, "start", new_callable=AsyncMock), \
             patch.object(MCPClient, "list_tools", new_callable=AsyncMock, return_value=[tool_info]):
            await mgr.start_all()
        mock_registry.register.assert_called_once()

        with patch.object(MCPClient, "stop", new_callable=AsyncMock):
            await mgr.stop_all()
        mock_registry.unregister.assert_called_once_with("mcp__a__read")

    def test_list_all_tools_empty(self):
        mgr = MCPManager()
        assert mgr.list_all_tools() == []


# ── MCPToolAdapter (unchanged, but verify) ──


class TestMCPToolAdapter:
    def test_name_format(self):
        client = MagicMock()
        adapter = MCPToolAdapter(
            client=client, tool_name="read_file", description="Read a file",
            input_schema={"type": "object"}, server_name="filesystem",
        )
        assert adapter.name == "mcp__filesystem__read_file"
        assert adapter.risk_level == "write"

    async def test_execute(self):
        client = MagicMock()
        client.call_tool = AsyncMock(return_value="content here")
        adapter = MCPToolAdapter(
            client=client, tool_name="read_file", description="Read",
            input_schema={}, server_name="fs",
        )
        result = await adapter.execute(path="/tmp/test.txt")
        client.call_tool.assert_called_once_with("read_file", {"path": "/tmp/test.txt"})
        assert result == "content here"

    async def test_execute_error(self):
        client = MagicMock()
        client.call_tool = AsyncMock(side_effect=RuntimeError("conn lost"))
        adapter = MCPToolAdapter(
            client=client, tool_name="read_file", description="Read",
            input_schema={}, server_name="fs",
        )
        result = await adapter.execute(path="/tmp/test.txt")
        assert "MCP tool error" in result


# ── MCPCommand ──


class TestMCPCommand:
    def _make_context(self, manager=None):
        ctx = CommandContext(agent=MagicMock())
        ctx.mcp_manager = manager  # type: ignore[attr-defined]
        return ctx

    async def test_no_manager(self):
        cmd = MCPCommand()
        ctx = CommandContext(agent=MagicMock())
        result = await cmd.execute("list", ctx)
        assert result == "MCP not configured."

    async def test_list_empty(self):
        mgr = MCPManager()
        cmd = MCPCommand()
        result = await cmd.execute("list", self._make_context(mgr))
        assert "No MCP servers" in result

    async def test_list_with_servers(self):
        mgr = MCPManager()
        mgr.load_configs([MCPServerConfig(name="fs", command="echo")])
        cmd = MCPCommand()
        result = await cmd.execute("list", self._make_context(mgr))
        assert "fs" in result

    async def test_enable(self):
        mgr = MCPManager()
        mgr.load_configs([MCPServerConfig(name="fs", command="echo")])
        with patch.object(MCPClient, "start", new_callable=AsyncMock), \
             patch.object(MCPClient, "list_tools", new_callable=AsyncMock, return_value=[]):
            cmd = MCPCommand()
            result = await cmd.execute("enable fs", self._make_context(mgr))
        assert "Enabled" in result

    async def test_disable(self):
        mgr = MCPManager()
        mgr.load_configs([MCPServerConfig(name="fs", command="echo")])
        cmd = MCPCommand()
        result = await cmd.execute("disable fs", self._make_context(mgr))
        assert "Disabled" in result

    async def test_reconnect_nonexistent(self):
        mgr = MCPManager()
        cmd = MCPCommand()
        result = await cmd.execute("reconnect nope", self._make_context(mgr))
        assert "Failed" in result

    async def test_tools_all(self):
        mgr = MCPManager()
        cmd = MCPCommand()
        result = await cmd.execute("tools", self._make_context(mgr))
        assert "No MCP tools" in result

    async def test_unknown_subcmd(self):
        mgr = MCPManager()
        cmd = MCPCommand()
        result = await cmd.execute("badcmd", self._make_context(mgr))
        assert "Unknown subcommand" in result

    def test_name_and_description(self):
        cmd = MCPCommand()
        assert cmd.name == "mcp"
        assert "MCP" in cmd.description
