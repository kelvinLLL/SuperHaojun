"""Tests for Feature 12: MCP Integration."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from superhaojun.mcp.adapter import MCPToolAdapter
from superhaojun.mcp.client import MCPClient, MCPToolInfo
from superhaojun.mcp.config import MCPServerConfig, load_mcp_configs


# ---------------------------------------------------------------------------
# MCPServerConfig
# ---------------------------------------------------------------------------
class TestMCPServerConfig:
    def test_defaults(self) -> None:
        cfg = MCPServerConfig(name="test")
        assert cfg.transport == "stdio"
        assert cfg.command == ""
        assert cfg.args == []
        assert cfg.env == {}
        assert cfg.enabled is True

    def test_full_config(self) -> None:
        cfg = MCPServerConfig(
            name="fs", transport="stdio",
            command="npx", args=["-y", "mcp-fs"],
            env={"FOO": "bar"}, enabled=True,
        )
        assert cfg.name == "fs"
        assert cfg.command == "npx"
        assert cfg.args == ["-y", "mcp-fs"]


class TestLoadMCPConfigs:
    def test_load_valid(self, tmp_path: Path) -> None:
        data = {
            "servers": [
                {"name": "fs", "command": "npx", "args": ["-y", "mcp-fs"]},
                {"name": "web", "transport": "sse", "url": "http://localhost:3001"},
            ]
        }
        path = tmp_path / "mcp.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        configs = load_mcp_configs(path)
        assert len(configs) == 2
        assert configs[0].name == "fs"
        assert configs[1].transport == "sse"

    def test_load_missing_file(self, tmp_path: Path) -> None:
        configs = load_mcp_configs(tmp_path / "nonexistent.json")
        assert configs == []

    def test_load_corrupted(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("NOT JSON")
        assert load_mcp_configs(path) == []

    def test_skip_invalid_entries(self, tmp_path: Path) -> None:
        data = {
            "servers": [
                {"name": "good", "command": "echo"},
                "not a dict",
                {"no_name": True},
            ]
        }
        path = tmp_path / "mcp.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        configs = load_mcp_configs(path)
        assert len(configs) == 1

    def test_disabled_server(self, tmp_path: Path) -> None:
        data = {"servers": [{"name": "off", "enabled": False}]}
        path = tmp_path / "mcp.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        configs = load_mcp_configs(path)
        assert len(configs) == 1
        assert configs[0].enabled is False


# ---------------------------------------------------------------------------
# MCPToolInfo
# ---------------------------------------------------------------------------
class TestMCPToolInfo:
    def test_fields(self) -> None:
        info = MCPToolInfo(name="read", description="Read a file", input_schema={"type": "object"})
        assert info.name == "read"
        assert info.description == "Read a file"


# ---------------------------------------------------------------------------
# MCPClient — unit tests (no real subprocess)
# ---------------------------------------------------------------------------
class TestMCPClient:
    def test_not_running_initially(self) -> None:
        cfg = MCPServerConfig(name="test", command="echo")
        client = MCPClient(config=cfg)
        assert not client.is_running

    @pytest.mark.asyncio
    async def test_start_no_command_raises(self) -> None:
        cfg = MCPServerConfig(name="test", command="")
        client = MCPClient(config=cfg)
        with pytest.raises(ValueError, match="no command"):
            await client.start()

    @pytest.mark.asyncio
    async def test_unsupported_transport(self) -> None:
        cfg = MCPServerConfig(name="test", transport="sse", command="echo")
        client = MCPClient(config=cfg)
        with pytest.raises(NotImplementedError, match="sse"):
            await client.start()

    @pytest.mark.asyncio
    async def test_list_tools_mock(self) -> None:
        """Mock the _send_request to test list_tools parsing."""
        cfg = MCPServerConfig(name="test", command="echo")
        client = MCPClient(config=cfg)
        client._initialized = True

        mock_response = {
            "tools": [
                {"name": "read", "description": "Read file", "inputSchema": {"type": "object"}},
                {"name": "write", "description": "Write file"},
            ]
        }
        client._send_request = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]
        tools = await client.list_tools()
        assert len(tools) == 2
        assert tools[0].name == "read"
        assert tools[1].input_schema == {}

    @pytest.mark.asyncio
    async def test_call_tool_mock(self) -> None:
        cfg = MCPServerConfig(name="test", command="echo")
        client = MCPClient(config=cfg)
        client._initialized = True
        client._send_request = AsyncMock(return_value={  # type: ignore[method-assign]
            "content": [{"type": "text", "text": "hello world"}],
        })
        result = await client.call_tool("greet", {"name": "user"})
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_call_tool_multi_content(self) -> None:
        cfg = MCPServerConfig(name="test", command="echo")
        client = MCPClient(config=cfg)
        client._initialized = True
        client._send_request = AsyncMock(return_value={  # type: ignore[method-assign]
            "content": [
                {"type": "text", "text": "line1"},
                {"type": "text", "text": "line2"},
            ],
        })
        result = await client.call_tool("multi", {})
        assert result == "line1\nline2"

    @pytest.mark.asyncio
    async def test_call_tool_no_text_content(self) -> None:
        cfg = MCPServerConfig(name="test", command="echo")
        client = MCPClient(config=cfg)
        client._initialized = True
        client._send_request = AsyncMock(return_value={  # type: ignore[method-assign]
            "content": [{"type": "image", "data": "base64..."}],
        })
        result = await client.call_tool("img", {})
        # Falls back to JSON dump
        assert "image" in result


# ---------------------------------------------------------------------------
# MCPToolAdapter
# ---------------------------------------------------------------------------
class TestMCPToolAdapter:
    def _make_adapter(self) -> MCPToolAdapter:
        cfg = MCPServerConfig(name="myserver", command="echo")
        client = MCPClient(config=cfg)
        return MCPToolAdapter(
            client=client,
            tool_name="read_file",
            description="Read a file from disk",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            server_name="myserver",
        )

    def test_name_prefixed(self) -> None:
        adapter = self._make_adapter()
        assert adapter.name == "mcp__myserver__read_file"

    def test_description_prefixed(self) -> None:
        adapter = self._make_adapter()
        assert adapter.description.startswith("[MCP:myserver]")

    def test_parameters(self) -> None:
        adapter = self._make_adapter()
        assert "path" in adapter.parameters["properties"]

    def test_empty_schema(self) -> None:
        cfg = MCPServerConfig(name="s", command="echo")
        client = MCPClient(config=cfg)
        adapter = MCPToolAdapter(client=client, tool_name="t", description="d", input_schema={}, server_name="s")
        assert adapter.parameters == {"type": "object", "properties": {}}

    def test_risk_level(self) -> None:
        adapter = self._make_adapter()
        assert adapter.risk_level == "write"

    def test_concurrent_safe(self) -> None:
        adapter = self._make_adapter()
        assert adapter.is_concurrent_safe is True

    def test_to_openai_tool_format(self) -> None:
        adapter = self._make_adapter()
        tool_def = adapter.to_openai_tool()
        assert tool_def["type"] == "function"
        assert tool_def["function"]["name"] == "mcp__myserver__read_file"

    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        cfg = MCPServerConfig(name="s", command="echo")
        client = MCPClient(config=cfg)
        client.call_tool = AsyncMock(return_value="file content")  # type: ignore[method-assign]
        adapter = MCPToolAdapter(client=client, tool_name="read", description="d", input_schema={}, server_name="s")
        result = await adapter.execute(path="/tmp/test.txt")
        assert result == "file content"

    @pytest.mark.asyncio
    async def test_execute_error(self) -> None:
        cfg = MCPServerConfig(name="s", command="echo")
        client = MCPClient(config=cfg)
        client.call_tool = AsyncMock(side_effect=RuntimeError("connection lost"))  # type: ignore[method-assign]
        adapter = MCPToolAdapter(client=client, tool_name="read", description="d", input_schema={}, server_name="s")
        result = await adapter.execute(path="/tmp/test.txt")
        assert "MCP tool error" in result
        assert "connection lost" in result
