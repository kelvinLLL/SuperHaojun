"""Tests for tools: base, registry, and read_file."""

from __future__ import annotations

import pytest
from typing import Any

from superhaojun.tools.base import Tool
from superhaojun.tools.registry import ToolRegistry
from superhaojun.tools.read_file import ReadFileTool


class TestToolABC:
    def test_cannot_instantiate_abc(self) -> None:
        with pytest.raises(TypeError):
            Tool()  # type: ignore[abstract]

    def test_concrete_subclass(self) -> None:
        tool = ReadFileTool()
        assert tool.name == "read_file"
        assert tool.is_concurrent_safe is True
        assert tool.risk_level == "read"


class TestToOpenAITool:
    def test_schema_format(self) -> None:
        tool = ReadFileTool()
        schema = tool.to_openai_tool()
        assert schema["type"] == "function"
        fn = schema["function"]
        assert fn["name"] == "read_file"
        assert "description" in fn
        assert fn["parameters"]["type"] == "object"
        assert "path" in fn["parameters"]["properties"]
        assert fn["parameters"]["required"] == ["path"]


class TestToolRegistry:
    def test_register_and_get(self) -> None:
        reg = ToolRegistry()
        tool = ReadFileTool()
        reg.register(tool)
        assert len(reg) == 1
        assert reg.get("read_file") is tool

    def test_get_missing(self) -> None:
        reg = ToolRegistry()
        assert reg.get("nonexistent") is None

    def test_to_openai_tools(self) -> None:
        reg = ToolRegistry()
        reg.register(ReadFileTool())
        tools = reg.to_openai_tools()
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "read_file"

    def test_empty_registry(self) -> None:
        reg = ToolRegistry()
        assert len(reg) == 0
        assert reg.to_openai_tools() == []

    def test_register_overwrites(self) -> None:
        reg = ToolRegistry()
        reg.register(ReadFileTool())
        reg.register(ReadFileTool())
        assert len(reg) == 1


class TestReadFileTool:
    async def test_read_existing_file(self, tmp_path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("line1\nline2\nline3\n")
        tool = ReadFileTool()
        result = await tool.execute(path=str(f))
        assert "   1 | line1" in result
        assert "   2 | line2" in result
        assert "   3 | line3" in result

    async def test_read_missing_file(self) -> None:
        tool = ReadFileTool()
        result = await tool.execute(path="/nonexistent/path/file.txt")
        assert result.startswith("Error: file not found:")

    async def test_read_empty_path(self) -> None:
        tool = ReadFileTool()
        result = await tool.execute(path="")
        assert "Error" in result

    async def test_read_no_path_kwarg(self) -> None:
        tool = ReadFileTool()
        result = await tool.execute()
        assert "Error" in result
