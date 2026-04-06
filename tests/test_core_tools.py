"""Tests for core tools: WriteFile, EditFile, Bash, Glob, Grep, ListDir."""

from __future__ import annotations

import pytest

from superhaojun.tools.write_file import WriteFileTool
from superhaojun.tools.edit_file import EditFileTool
from superhaojun.tools.bash import BashTool
from superhaojun.tools.glob_tool import GlobTool
from superhaojun.tools.grep import GrepTool
from superhaojun.tools.list_dir import ListDirTool
from superhaojun.tools import register_builtin_tools, ToolRegistry


class TestRegisterBuiltin:
    def test_register_all(self) -> None:
        reg = ToolRegistry()
        register_builtin_tools(reg)
        assert len(reg) == 7
        assert reg.get("read_file") is not None
        assert reg.get("write_file") is not None
        assert reg.get("edit_file") is not None
        assert reg.get("bash") is not None
        assert reg.get("glob") is not None
        assert reg.get("grep") is not None
        assert reg.get("list_dir") is not None


class TestWriteFile:
    def test_properties(self) -> None:
        t = WriteFileTool()
        assert t.name == "write_file"
        assert t.is_concurrent_safe is False
        assert t.risk_level == "write"

    async def test_write_new_file(self, tmp_path) -> None:
        tool = WriteFileTool()
        dest = tmp_path / "new.txt"
        result = await tool.execute(path=str(dest), content="hello\nworld\n")
        assert "Successfully wrote" in result
        assert dest.read_text() == "hello\nworld\n"

    async def test_write_creates_directories(self, tmp_path) -> None:
        tool = WriteFileTool()
        dest = tmp_path / "sub" / "dir" / "file.txt"
        result = await tool.execute(path=str(dest), content="test")
        assert "Successfully" in result
        assert dest.read_text() == "test"

    async def test_overwrite_existing(self, tmp_path) -> None:
        tool = WriteFileTool()
        dest = tmp_path / "existing.txt"
        dest.write_text("old")
        await tool.execute(path=str(dest), content="new")
        assert dest.read_text() == "new"

    async def test_empty_path(self) -> None:
        tool = WriteFileTool()
        result = await tool.execute(path="", content="x")
        assert "Error" in result


class TestEditFile:
    def test_properties(self) -> None:
        t = EditFileTool()
        assert t.name == "edit_file"
        assert t.is_concurrent_safe is False
        assert t.risk_level == "write"

    async def test_replace_string(self, tmp_path) -> None:
        tool = EditFileTool()
        f = tmp_path / "code.py"
        f.write_text("def foo():\n    return 1\n")
        result = await tool.execute(
            path=str(f), old_string="return 1", new_string="return 42",
        )
        assert "Successfully edited" in result
        assert "return 42" in f.read_text()

    async def test_string_not_found(self, tmp_path) -> None:
        tool = EditFileTool()
        f = tmp_path / "a.txt"
        f.write_text("hello")
        result = await tool.execute(
            path=str(f), old_string="nonexistent", new_string="x",
        )
        assert "not found" in result

    async def test_ambiguous_match(self, tmp_path) -> None:
        tool = EditFileTool()
        f = tmp_path / "dup.txt"
        f.write_text("abc\nabc\n")
        result = await tool.execute(
            path=str(f), old_string="abc", new_string="xyz",
        )
        assert "found 2 times" in result

    async def test_missing_file(self) -> None:
        tool = EditFileTool()
        result = await tool.execute(
            path="/nonexistent/file.txt", old_string="a", new_string="b",
        )
        assert "file not found" in result


class TestBash:
    def test_properties(self) -> None:
        t = BashTool()
        assert t.name == "bash"
        assert t.is_concurrent_safe is False
        assert t.risk_level == "dangerous"

    async def test_simple_command(self) -> None:
        tool = BashTool()
        result = await tool.execute(command="echo hello")
        assert "hello" in result

    async def test_exit_code_nonzero(self) -> None:
        tool = BashTool()
        result = await tool.execute(command="exit 1")
        assert "Exit code: 1" in result

    async def test_empty_command(self) -> None:
        tool = BashTool()
        result = await tool.execute(command="")
        assert "Error" in result

    async def test_stderr(self) -> None:
        tool = BashTool()
        result = await tool.execute(command="echo error >&2")
        assert "STDERR" in result
        assert "error" in result


class TestGlob:
    def test_properties(self) -> None:
        t = GlobTool()
        assert t.name == "glob"
        assert t.risk_level == "read"

    async def test_find_files(self, tmp_path) -> None:
        (tmp_path / "a.py").write_text("x")
        (tmp_path / "b.py").write_text("x")
        (tmp_path / "c.txt").write_text("x")
        tool = GlobTool()
        result = await tool.execute(pattern="*.py", path=str(tmp_path))
        assert "a.py" in result
        assert "b.py" in result
        assert "c.txt" not in result

    async def test_no_matches(self, tmp_path) -> None:
        tool = GlobTool()
        result = await tool.execute(pattern="*.xyz", path=str(tmp_path))
        assert "No files matching" in result

    async def test_recursive(self, tmp_path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.py").write_text("x")
        tool = GlobTool()
        result = await tool.execute(pattern="**/*.py", path=str(tmp_path))
        assert "deep.py" in result


class TestGrep:
    def test_properties(self) -> None:
        t = GrepTool()
        assert t.name == "grep"
        assert t.risk_level == "read"

    async def test_find_in_file(self, tmp_path) -> None:
        f = tmp_path / "code.py"
        f.write_text("def foo():\n    return 42\n")
        tool = GrepTool()
        result = await tool.execute(pattern="return 42", path=str(f))
        assert "return 42" in result
        assert ":2:" in result

    async def test_regex_pattern(self, tmp_path) -> None:
        f = tmp_path / "data.txt"
        f.write_text("foo123\nbar456\nbaz\n")
        tool = GrepTool()
        result = await tool.execute(pattern=r"\d+", path=str(f))
        assert "foo123" in result
        assert "bar456" in result
        assert "baz" not in result

    async def test_no_matches(self, tmp_path) -> None:
        f = tmp_path / "empty.txt"
        f.write_text("nothing here\n")
        tool = GrepTool()
        result = await tool.execute(pattern="zzzzz", path=str(f))
        assert "No matches" in result

    async def test_search_directory(self, tmp_path) -> None:
        (tmp_path / "a.py").write_text("needle\n")
        (tmp_path / "b.py").write_text("haystack\n")
        tool = GrepTool()
        result = await tool.execute(pattern="needle", path=str(tmp_path), glob="*.py")
        assert "needle" in result
        assert "b.py" not in result


class TestListDir:
    def test_properties(self) -> None:
        t = ListDirTool()
        assert t.name == "list_dir"
        assert t.risk_level == "read"

    async def test_list_directory(self, tmp_path) -> None:
        (tmp_path / "file.txt").write_text("x")
        (tmp_path / "subdir").mkdir()
        tool = ListDirTool()
        result = await tool.execute(path=str(tmp_path))
        assert "subdir/" in result
        assert "file.txt" in result

    async def test_dirs_first(self, tmp_path) -> None:
        (tmp_path / "zebra.txt").write_text("x")
        (tmp_path / "alpha").mkdir()
        tool = ListDirTool()
        result = await tool.execute(path=str(tmp_path))
        lines = result.strip().split("\n")
        assert lines[0] == "alpha/"
        assert lines[1] == "zebra.txt"

    async def test_nonexistent_path(self) -> None:
        tool = ListDirTool()
        result = await tool.execute(path="/nonexistent/dir")
        assert "Error: path not found" in result

    async def test_empty_directory(self, tmp_path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        tool = ListDirTool()
        result = await tool.execute(path=str(empty))
        assert "empty directory" in result
