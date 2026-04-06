"""Tests for Feature 11: Hooks System."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from superhaojun.hooks.config import HookConfig, HookRule, HookTiming
from superhaojun.hooks.runner import HookResult, HookRunner


# ---------------------------------------------------------------------------
# HookRule
# ---------------------------------------------------------------------------
class TestHookRule:
    def test_exact_match(self) -> None:
        rule = HookRule(tool_pattern="bash", timing=HookTiming.PRE, command="echo hi")
        assert rule.matches("bash")
        assert not rule.matches("read_file")

    def test_glob_match(self) -> None:
        rule = HookRule(tool_pattern="write_*", timing=HookTiming.POST, command="echo ok")
        assert rule.matches("write_file")
        assert rule.matches("write_anything")
        assert not rule.matches("read_file")

    def test_star_matches_all(self) -> None:
        rule = HookRule(tool_pattern="*", timing=HookTiming.PRE, command="echo all")
        assert rule.matches("bash")
        assert rule.matches("read_file")

    def test_defaults(self) -> None:
        rule = HookRule(tool_pattern="bash", timing=HookTiming.PRE, command="echo")
        assert rule.timeout == 10
        assert rule.enabled is True


# ---------------------------------------------------------------------------
# HookConfig
# ---------------------------------------------------------------------------
class TestHookConfig:
    def test_add_and_get_rules(self) -> None:
        config = HookConfig()
        config.add_rule(HookRule(tool_pattern="bash", timing=HookTiming.PRE, command="echo pre"))
        config.add_rule(HookRule(tool_pattern="bash", timing=HookTiming.POST, command="echo post"))
        config.add_rule(HookRule(tool_pattern="read_file", timing=HookTiming.PRE, command="echo read"))
        assert len(config.get_rules("bash", HookTiming.PRE)) == 1
        assert len(config.get_rules("bash", HookTiming.POST)) == 1
        assert len(config.get_rules("read_file", HookTiming.PRE)) == 1
        assert len(config.get_rules("read_file", HookTiming.POST)) == 0

    def test_disabled_rule_skipped(self) -> None:
        config = HookConfig()
        config.add_rule(HookRule(tool_pattern="bash", timing=HookTiming.PRE, command="echo", enabled=False))
        assert config.get_rules("bash", HookTiming.PRE) == []

    def test_remove_rule(self) -> None:
        config = HookConfig()
        config.add_rule(HookRule(tool_pattern="bash", timing=HookTiming.PRE, command="echo"))
        assert config.remove_rule(0) is True
        assert config.rules == []
        assert config.remove_rule(99) is False

    def test_save_and_load(self, tmp_path: Path) -> None:
        config = HookConfig()
        config.add_rule(HookRule(tool_pattern="bash", timing=HookTiming.PRE, command="echo hi", timeout=5))
        config.add_rule(HookRule(tool_pattern="*", timing=HookTiming.POST, command="echo done"))

        path = tmp_path / "hooks.json"
        config.save(path)
        assert path.exists()

        loaded = HookConfig.load(path)
        assert len(loaded.rules) == 2
        assert loaded.rules[0].tool_pattern == "bash"
        assert loaded.rules[0].timing == HookTiming.PRE
        assert loaded.rules[0].timeout == 5
        assert loaded.rules[1].tool_pattern == "*"

    def test_load_missing_file(self, tmp_path: Path) -> None:
        config = HookConfig.load(tmp_path / "nonexistent.json")
        assert config.rules == []

    def test_load_corrupted_file(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("NOT JSON")
        config = HookConfig.load(path)
        assert config.rules == []

    def test_load_skips_malformed_rules(self, tmp_path: Path) -> None:
        data = {"hooks": [
            {"tool_pattern": "bash", "timing": "pre", "command": "echo ok"},
            {"bad": "rule"},  # Missing required fields
            {"tool_pattern": "bash", "timing": "invalid_timing", "command": "echo"},
        ]}
        path = tmp_path / "hooks.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        config = HookConfig.load(path)
        assert len(config.rules) == 1

    def test_glob_rules(self) -> None:
        config = HookConfig()
        config.add_rule(HookRule(tool_pattern="edit_*", timing=HookTiming.POST, command="ls"))
        assert len(config.get_rules("edit_file", HookTiming.POST)) == 1
        assert len(config.get_rules("write_file", HookTiming.POST)) == 0


# ---------------------------------------------------------------------------
# HookResult
# ---------------------------------------------------------------------------
class TestHookResult:
    def test_success(self) -> None:
        rule = HookRule(tool_pattern="bash", timing=HookTiming.PRE, command="echo")
        result = HookResult(rule=rule, exit_code=0, stdout="ok", stderr="")
        assert result.success is True

    def test_failure(self) -> None:
        rule = HookRule(tool_pattern="bash", timing=HookTiming.PRE, command="exit 1")
        result = HookResult(rule=rule, exit_code=1, stdout="", stderr="err")
        assert result.success is False

    def test_timeout(self) -> None:
        rule = HookRule(tool_pattern="bash", timing=HookTiming.PRE, command="sleep 100")
        result = HookResult(rule=rule, exit_code=-1, stdout="", stderr="", timed_out=True)
        assert result.success is False


# ---------------------------------------------------------------------------
# HookRunner
# ---------------------------------------------------------------------------
class TestHookRunner:
    @pytest.mark.asyncio
    async def test_pre_hook_success(self, tmp_path: Path) -> None:
        config = HookConfig()
        config.add_rule(HookRule(tool_pattern="bash", timing=HookTiming.PRE, command="echo pre-hook"))
        runner = HookRunner(config=config, working_dir=str(tmp_path))
        results = await runner.run_pre_hooks("bash", {"command": "ls"})
        assert len(results) == 1
        assert results[0].success
        assert results[0].stdout == "pre-hook"

    @pytest.mark.asyncio
    async def test_pre_hook_failure_blocks(self, tmp_path: Path) -> None:
        config = HookConfig()
        config.add_rule(HookRule(tool_pattern="bash", timing=HookTiming.PRE, command="exit 1"))
        runner = HookRunner(config=config, working_dir=str(tmp_path))
        results = await runner.run_pre_hooks("bash", {"command": "ls"})
        assert not runner.all_passed(results)

    @pytest.mark.asyncio
    async def test_post_hook_runs(self, tmp_path: Path) -> None:
        log_file = tmp_path / "hook.log"
        config = HookConfig()
        config.add_rule(HookRule(
            tool_pattern="write_file", timing=HookTiming.POST,
            command=f"echo 'written' > {log_file}",
        ))
        runner = HookRunner(config=config, working_dir=str(tmp_path))
        results = await runner.run_post_hooks("write_file", {"path": "test.py"}, result="ok")
        assert len(results) == 1
        assert results[0].success
        assert log_file.read_text().strip() == "written"

    @pytest.mark.asyncio
    async def test_no_matching_rules(self) -> None:
        config = HookConfig()
        config.add_rule(HookRule(tool_pattern="bash", timing=HookTiming.PRE, command="echo"))
        runner = HookRunner(config=config)
        results = await runner.run_pre_hooks("read_file", {})
        assert results == []

    @pytest.mark.asyncio
    async def test_variable_substitution(self, tmp_path: Path) -> None:
        config = HookConfig()
        config.add_rule(HookRule(
            tool_pattern="bash", timing=HookTiming.PRE,
            command="echo 'tool={tool_name} cwd={cwd}'",
        ))
        runner = HookRunner(config=config, working_dir=str(tmp_path))
        results = await runner.run_pre_hooks("bash", {"command": "ls"})
        assert results[0].success
        assert "tool=bash" in results[0].stdout
        assert str(tmp_path) in results[0].stdout

    @pytest.mark.asyncio
    async def test_timeout_hook(self, tmp_path: Path) -> None:
        config = HookConfig()
        config.add_rule(HookRule(
            tool_pattern="bash", timing=HookTiming.PRE,
            command="sleep 30", timeout=1,
        ))
        runner = HookRunner(config=config, working_dir=str(tmp_path))
        results = await runner.run_pre_hooks("bash", {})
        assert len(results) == 1
        assert results[0].timed_out
        assert not results[0].success

    @pytest.mark.asyncio
    async def test_multiple_hooks_same_tool(self, tmp_path: Path) -> None:
        config = HookConfig()
        config.add_rule(HookRule(tool_pattern="bash", timing=HookTiming.PRE, command="echo first"))
        config.add_rule(HookRule(tool_pattern="bash", timing=HookTiming.PRE, command="echo second"))
        runner = HookRunner(config=config, working_dir=str(tmp_path))
        results = await runner.run_pre_hooks("bash", {})
        assert len(results) == 2
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_all_passed_helper(self) -> None:
        rule = HookRule(tool_pattern="*", timing=HookTiming.PRE, command="echo")
        good = [HookResult(rule=rule, exit_code=0, stdout="", stderr="")]
        bad = [HookResult(rule=rule, exit_code=1, stdout="", stderr="")]
        assert HookRunner.all_passed(good)
        assert not HookRunner.all_passed(bad)
        assert HookRunner.all_passed([])  # No hooks = all passed
