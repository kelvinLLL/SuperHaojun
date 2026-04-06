"""Permissions package — PermissionChecker, rules, and decisions."""

from .checker import PermissionChecker
from .rules import Decision, PermissionRule

__all__ = ["Decision", "PermissionChecker", "PermissionRule"]
