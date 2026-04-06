"""Tools package — Tool ABC, ToolRegistry, and built-in tools."""

from .base import Tool
from .bash import BashTool
from .edit_file import EditFileTool
from .glob_tool import GlobTool
from .grep import GrepTool
from .list_dir import ListDirTool
from .read_file import ReadFileTool
from .registry import ToolRegistry
from .write_file import WriteFileTool

__all__ = [
    "Tool",
    "ToolRegistry",
    "BashTool",
    "EditFileTool",
    "GlobTool",
    "GrepTool",
    "ListDirTool",
    "ReadFileTool",
    "WriteFileTool",
]


def register_builtin_tools(registry: ToolRegistry) -> None:
    """Register all built-in tools into a registry."""
    for tool_cls in (ReadFileTool, WriteFileTool, EditFileTool, BashTool, GlobTool, GrepTool, ListDirTool):
        registry.register(tool_cls())
