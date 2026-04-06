"""TUI package — Rich Terminal User Interface.

Provides a styled terminal interface with:
- Markdown rendering and syntax highlighting (via rich)
- Styled input prompt (via prompt_toolkit)
- Progress spinners for tool execution
- Pluggable render handlers for the MessageBus

Reference: Claude Code's ink-based terminal UI.
"""

from .app import TUIApp
from .renderer import TUIRenderer

__all__ = ["TUIApp", "TUIRenderer"]
