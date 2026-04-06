"""Prompt package — dynamic system prompt assembly with Section Registry."""

from .builder import SystemPromptBuilder
from .context import GitInfo, PromptContext, gather_git_info, gather_git_info_sync
from .sections import PromptSection

__all__ = [
    "GitInfo",
    "PromptContext",
    "PromptSection",
    "SystemPromptBuilder",
    "gather_git_info",
    "gather_git_info_sync",
]
