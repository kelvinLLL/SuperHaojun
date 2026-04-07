"""Hooks package — lifecycle event hooks with multi-source registry."""

from .config import (
    AggregatedHookResult, BLOCKING_EVENTS, HookContext, HookEvent,
    HookRegistry, HookResult, HookRule, HookType,
)
from .runner import HookRunner

__all__ = [
    "AggregatedHookResult", "BLOCKING_EVENTS", "HookContext", "HookEvent",
    "HookRegistry", "HookResult", "HookRule", "HookRunner", "HookType",
]
