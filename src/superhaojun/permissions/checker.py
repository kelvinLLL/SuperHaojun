"""PermissionChecker — decides whether a tool execution is allowed.

Matching priority:
  1. Exact tool_name rule
  2. risk_level rule
  3. Default policy (based on risk_level: read→allow, write/dangerous→ask)
"""

from __future__ import annotations

from .rules import Decision, PermissionRule


class PermissionChecker:
    """Evaluates permission rules to decide allow / deny / ask for a tool."""

    def __init__(self, rules: list[PermissionRule] | None = None) -> None:
        self._tool_rules: dict[str, Decision] = {}
        self._risk_rules: dict[str, Decision] = {}
        if rules:
            for rule in rules:
                self.add_rule(rule)

    def add_rule(self, rule: PermissionRule) -> None:
        if rule.tool_name:
            self._tool_rules[rule.tool_name] = rule.decision
        elif rule.risk_level:
            self._risk_rules[rule.risk_level] = rule.decision

    def remove_tool_rule(self, tool_name: str) -> None:
        self._tool_rules.pop(tool_name, None)

    def check(self, tool_name: str, risk_level: str) -> Decision:
        """Return the decision for a given tool + risk_level combination."""
        # Priority 1: exact tool name match
        if tool_name in self._tool_rules:
            return self._tool_rules[tool_name]

        # Priority 2: risk level match
        if risk_level in self._risk_rules:
            return self._risk_rules[risk_level]

        # Priority 3: default policy
        return self._default_for_risk(risk_level)

    @staticmethod
    def _default_for_risk(risk_level: str) -> Decision:
        if risk_level == "read":
            return Decision.ALLOW
        return Decision.ASK

    def allow_always(self, tool_name: str) -> None:
        """Convenience: always allow a specific tool."""
        self._tool_rules[tool_name] = Decision.ALLOW

    def deny_always(self, tool_name: str) -> None:
        """Convenience: always deny a specific tool."""
        self._tool_rules[tool_name] = Decision.DENY
