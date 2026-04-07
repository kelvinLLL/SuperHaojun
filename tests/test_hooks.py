"""Tests for hooks v2 — HookEvent, HookRegistry, HookRunner, AggregatedHookResult."""

from __future__ import annotations

import json
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from superhaojun.hooks.config import (
    AggregatedHookResult, BLOCKING_EVENTS, HookContext, HookEvent,
    HookRegistry, HookResult, HookRule, HookType,
)
from superhaojun.hooks.runner import HookRunner


# ── HookEvent ──


class TestHookEvent:
    def test_all_15_events(self):
        assert len(HookEvent) == 14

    def test_values(self):
        assert HookEvent.SESSION_START == "session_start"
        assert HookEvent.PRE_TOOL_USE == "pre_tool_use"
        assert HookEvent.POST_TOOL_USE == "post_tool_use"
        assert HookEvent.STOP == "stop"
        assert HookEvent.FILE_CHANGED == "file_changed"
        assert HookEvent.USER_PROMPT_SUBMIT == "user_prompt_submit"

    def test_blocking_events(self):
        assert HookEvent.PRE_TOOL_USE in BLOCKING_EVENTS
        assert HookEvent.USER_PROMPT_SUBMIT in BLOCKING_EVENTS
        assert HookEvent.STOP in BLOCKING_EVENTS
        assert HookEvent.POST_TOOL_USE not in BLOCKING_EVENTS


# ── HookType ──


class TestHookType:
    def test_command_and_function(self):
        assert HookType.COMMAND == "command"
        assert HookType.FUNCTION == "function"


# ── HookRule ──


class TestHookRule:
    def test_defaults(self):
        rule = HookRule(tool_pattern="*", event=HookEvent.PRE_TOOL_USE, command="echo hi")
        assert rule.hook_type == HookType.COMMAND
        assert rule.timeout == 10
        assert rule.enabled is True
        assert rule.priority == 100

    def test_matches_wildcard(self):
        rule = HookRule(tool_pattern="*", event=HookEvent.PRE_TOOL_USE)
        assert rule.matches("write_file") is True
        assert rule.matches("") is True

    def test_matches_glob(self):
        rule = HookRule(tool_pattern="write_*", event=HookEvent.PRE_TOOL_USE)
        assert rule.matches("write_file") is True
        assert rule.matches("read_file") is False

    def test_matches_exact(self):
        rule = HookRule(tool_pattern="bash", event=HookEvent.PRE_TOOL_USE)
        assert rule.matches("bash") is True
        assert rule.matches("write_file") is False

    def test_frozen(self):
        rule = HookRule(tool_pattern="*", event=HookEvent.PRE_TOOL_USE)
        with pytest.raises(AttributeError):
            rule.command = "changed"  # type: ignore[misc]


# ── HookContext ──


class TestHookContext:
    def test_defaults(self):
        ctx = HookContext(event=HookEvent.PRE_TOOL_USE)
        assert ctx.tool_name == ""
        assert ctx.arguments == {}
        assert ctx.result == ""
        assert ctx.cwd == "."

    def test_full(self):
        ctx = HookContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="write_file",
            arguments={"path": "test.py"},
            result="ok",
            cwd="/tmp",
        )
        assert ctx.tool_name == "write_file"
        assert ctx.arguments["path"] == "test.py"


# ── HookResult ──


class TestHookResult:
    def _make_rule(self) -> HookRule:
        return HookRule(tool_pattern="*", event=HookEvent.PRE_TOOL_USE, command="echo hi")

    def test_success(self):
        r = HookResult(rule=self._make_rule(), exit_code=0, stdout="ok", stderr="")
        assert r.success is True
        assert r.blocking is False

    def test_blocking(self):
        r = HookResult(rule=self._make_rule(), exit_code=2, stdout="", stderr="blocked")
        assert r.success is False
        assert r.blocking is True

    def test_non_blocking_error(self):
        r = HookResult(rule=self._make_rule(), exit_code=1, stdout="", stderr="err")
        assert r.success is False
        assert r.blocking is False

    def test_timeout(self):
        r = HookResult(rule=self._make_rule(), exit_code=0, stdout="", stderr="", timed_out=True)
        assert r.success is False

    def test_structured_fields(self):
        r = HookResult(
            rule=self._make_rule(), exit_code=0, stdout="", stderr="",
            additional_context="extra info",
            updated_input={"path": "new.py"},
        )
        assert r.additional_context == "extra info"
        assert r.updated_input == {"path": "new.py"}


# ── AggregatedHookResult ──


class TestAggregatedHookResult:
    def _rule(self) -> HookRule:
        return HookRule(tool_pattern="*", event=HookEvent.PRE_TOOL_USE, command="echo")

    def test_empty(self):
        agg = AggregatedHookResult(results=[])
        assert agg.all_passed is True
        assert agg.should_block is False
        assert agg.blocking_errors == []
        assert agg.additional_contexts == []
        assert agg.updated_input is None

    def test_all_passed(self):
        agg = AggregatedHookResult(results=[
            HookResult(rule=self._rule(), exit_code=0, stdout="", stderr=""),
            HookResult(rule=self._rule(), exit_code=0, stdout="", stderr=""),
        ])
        assert agg.all_passed is True
        assert agg.should_block is False

    def test_blocking(self):
        agg = AggregatedHookResult(results=[
            HookResult(rule=self._rule(), exit_code=0, stdout="", stderr=""),
            HookResult(rule=self._rule(), exit_code=2, stdout="", stderr="no!"),
        ])
        assert agg.should_block is True
        assert agg.blocking_errors == ["no!"]

    def test_additional_contexts(self):
        agg = AggregatedHookResult(results=[
            HookResult(rule=self._rule(), exit_code=0, stdout="", stderr="", additional_context="ctx1"),
            HookResult(rule=self._rule(), exit_code=0, stdout="", stderr="", additional_context=""),
            HookResult(rule=self._rule(), exit_code=0, stdout="", stderr="", additional_context="ctx2"),
        ])
        assert agg.additional_contexts == ["ctx1", "ctx2"]

    def test_updated_input_last_wins(self):
        agg = AggregatedHookResult(results=[
            HookResult(rule=self._rule(), exit_code=0, stdout="", stderr="", updated_input={"a": 1}),
            HookResult(rule=self._rule(), exit_code=0, stdout="", stderr="", updated_input={"b": 2}),
        ])
        assert agg.updated_input == {"b": 2}


# ── HookRegistry ──


class TestHookRegistry:
    def test_empty(self):
        reg = HookRegistry()
        assert reg.list_hooks() == []
        assert reg.match(HookEvent.PRE_TOOL_USE) == []

    def test_add_and_match(self):
        reg = HookRegistry()
        rule = HookRule(tool_pattern="bash", event=HookEvent.PRE_TOOL_USE, command="echo check")
        reg.add_rule(rule)
        assert len(reg.list_hooks()) == 1
        assert reg.match(HookEvent.PRE_TOOL_USE, "bash") == [rule]
        assert reg.match(HookEvent.PRE_TOOL_USE, "read_file") == []
        assert reg.match(HookEvent.POST_TOOL_USE, "bash") == []

    def test_priority_sorting(self):
        reg = HookRegistry()
        low = HookRule(tool_pattern="*", event=HookEvent.PRE_TOOL_USE, command="a", priority=200)
        high = HookRule(tool_pattern="*", event=HookEvent.PRE_TOOL_USE, command="b", priority=50)
        reg.add_rule(low)
        reg.add_rule(high)
        matched = reg.match(HookEvent.PRE_TOOL_USE, "bash")
        assert matched == [high, low]

    def test_disabled_rule_excluded(self):
        reg = HookRegistry()
        rule = HookRule(tool_pattern="*", event=HookEvent.PRE_TOOL_USE, command="x", enabled=False)
        reg.add_rule(rule)
        assert reg.match(HookEvent.PRE_TOOL_USE, "bash") == []

    def test_remove_rule(self):
        reg = HookRegistry()
        rule = HookRule(tool_pattern="*", event=HookEvent.PRE_TOOL_USE, command="x")
        reg.add_rule(rule)
        assert reg.remove_rule(0) is True
        assert reg.list_hooks() == []
        assert reg.remove_rule(99) is False

    def test_clear_runtime(self):
        reg = HookRegistry()
        reg.add_rule(HookRule(tool_pattern="*", event=HookEvent.PRE_TOOL_USE, command="x"))
        reg.clear_runtime()
        assert reg.list_hooks() == []

    def test_save_and_load(self, tmp_path):
        reg = HookRegistry()
        reg._config_rules.append(HookRule(
            tool_pattern="bash", event=HookEvent.PRE_TOOL_USE,
            command="echo hi", timeout=5, priority=50,
        ))
        path = tmp_path / "hooks.json"
        reg.save(path)

        loaded = HookRegistry.load(path)
        assert len(loaded.list_hooks()) == 1
        rule = loaded.list_hooks()[0]
        assert rule.tool_pattern == "bash"
        assert rule.event == HookEvent.PRE_TOOL_USE
        assert rule.command == "echo hi"
        assert rule.timeout == 5
        assert rule.priority == 50

    def test_load_missing_file(self, tmp_path):
        reg = HookRegistry.load(tmp_path / "nope.json")
        assert reg.list_hooks() == []

    def test_load_backward_compat_timing(self, tmp_path):
        path = tmp_path / "hooks.json"
        path.write_text(json.dumps({
            "hooks": [
                {"tool_pattern": "*", "timing": "pre", "command": "echo old"},
                {"tool_pattern": "*", "timing": "post", "command": "echo old2"},
            ]
        }))
        reg = HookRegistry.load(path)
        assert len(reg.list_hooks()) == 2
        assert reg.list_hooks()[0].event == HookEvent.PRE_TOOL_USE
        assert reg.list_hooks()[1].event == HookEvent.POST_TOOL_USE

    def test_load_invalid_json(self, tmp_path):
        path = tmp_path / "hooks.json"
        path.write_text("not json")
        reg = HookRegistry.load(path)
        assert reg.list_hooks() == []


# ── HookRunner ──


class TestHookRunner:
    def _registry_with_rule(self, **kwargs) -> HookRegistry:
        reg = HookRegistry()
        defaults = {"tool_pattern": "*", "event": HookEvent.PRE_TOOL_USE, "command": "echo ok"}
        defaults.update(kwargs)
        reg.add_rule(HookRule(**defaults))
        return reg

    async def test_run_hooks_empty(self):
        runner = HookRunner(registry=HookRegistry())
        agg = await runner.run_hooks(HookEvent.PRE_TOOL_USE, "bash")
        assert agg.results == []
        assert agg.all_passed is True

    async def test_run_command_hook_success(self):
        reg = self._registry_with_rule(command="echo ok")
        runner = HookRunner(registry=reg)
        agg = await runner.run_hooks(HookEvent.PRE_TOOL_USE, "bash")
        assert len(agg.results) == 1
        assert agg.results[0].success is True
        assert "ok" in agg.results[0].stdout

    async def test_run_command_hook_exit_2_blocking(self):
        reg = self._registry_with_rule(command="exit 2")
        runner = HookRunner(registry=reg)
        agg = await runner.run_hooks(HookEvent.PRE_TOOL_USE, "bash")
        assert agg.should_block is True
        assert agg.results[0].blocking is True

    async def test_run_command_hook_exit_1_non_blocking(self):
        reg = self._registry_with_rule(command="exit 1")
        runner = HookRunner(registry=reg)
        agg = await runner.run_hooks(HookEvent.PRE_TOOL_USE, "bash")
        assert agg.should_block is False
        assert agg.results[0].success is False

    async def test_run_command_hook_timeout(self):
        reg = self._registry_with_rule(command="sleep 10", timeout=1)
        runner = HookRunner(registry=reg)
        agg = await runner.run_hooks(HookEvent.PRE_TOOL_USE, "bash")
        assert agg.results[0].timed_out is True
        assert agg.results[0].success is False

    async def test_run_command_hook_variable_substitution(self):
        reg = self._registry_with_rule(command='echo "$TOOL_NAME $EVENT"')
        runner = HookRunner(registry=reg)
        agg = await runner.run_hooks(HookEvent.PRE_TOOL_USE, "write_file", {"path": "x"})
        stdout = agg.results[0].stdout
        assert "write_file" in stdout
        assert "pre_tool_use" in stdout

    async def test_run_command_hook_stdout_json_parsing(self):
        json_output = json.dumps({"additional_context": "lint ok", "updated_input": {"path": "new.py"}})
        reg = self._registry_with_rule(command=f"echo '{json_output}'")
        runner = HookRunner(registry=reg)
        agg = await runner.run_hooks(HookEvent.PRE_TOOL_USE, "bash")
        assert agg.results[0].additional_context == "lint ok"
        assert agg.results[0].updated_input == {"path": "new.py"}

    async def test_run_function_hook_success(self):
        async def my_hook(ctx: HookContext) -> dict:
            return {"exit_code": 0, "stdout": "func ok", "additional_context": "from func"}

        reg = HookRegistry()
        reg.add_rule(HookRule(
            tool_pattern="*", event=HookEvent.PRE_TOOL_USE,
            hook_type=HookType.FUNCTION, callback=my_hook,
        ))
        runner = HookRunner(registry=reg)
        agg = await runner.run_hooks(HookEvent.PRE_TOOL_USE, "bash")
        assert len(agg.results) == 1
        assert agg.results[0].success is True
        assert agg.results[0].additional_context == "from func"

    async def test_run_function_hook_blocking(self):
        async def block_hook(ctx):
            return {"exit_code": 2, "stderr": "blocked by func"}

        reg = HookRegistry()
        reg.add_rule(HookRule(
            tool_pattern="*", event=HookEvent.PRE_TOOL_USE,
            hook_type=HookType.FUNCTION, callback=block_hook,
        ))
        runner = HookRunner(registry=reg)
        agg = await runner.run_hooks(HookEvent.PRE_TOOL_USE, "bash")
        assert agg.should_block is True

    async def test_run_function_hook_exception(self):
        async def bad_hook(ctx):
            raise RuntimeError("boom")

        reg = HookRegistry()
        reg.add_rule(HookRule(
            tool_pattern="*", event=HookEvent.PRE_TOOL_USE,
            hook_type=HookType.FUNCTION, callback=bad_hook,
        ))
        runner = HookRunner(registry=reg)
        agg = await runner.run_hooks(HookEvent.PRE_TOOL_USE, "bash")
        assert agg.results[0].success is False
        assert "boom" in agg.results[0].stderr

    async def test_run_function_hook_no_callback(self):
        reg = HookRegistry()
        reg.add_rule(HookRule(
            tool_pattern="*", event=HookEvent.PRE_TOOL_USE,
            hook_type=HookType.FUNCTION,
        ))
        runner = HookRunner(registry=reg)
        agg = await runner.run_hooks(HookEvent.PRE_TOOL_USE, "bash")
        assert agg.results[0].success is False

    async def test_run_function_hook_timeout(self):
        async def slow_hook(ctx):
            await asyncio.sleep(10)

        reg = HookRegistry()
        reg.add_rule(HookRule(
            tool_pattern="*", event=HookEvent.PRE_TOOL_USE,
            hook_type=HookType.FUNCTION, callback=slow_hook, timeout=1,
        ))
        runner = HookRunner(registry=reg)
        agg = await runner.run_hooks(HookEvent.PRE_TOOL_USE, "bash")
        assert agg.results[0].timed_out is True

    async def test_multiple_hooks_run_all(self):
        reg = HookRegistry()
        reg.add_rule(HookRule(tool_pattern="*", event=HookEvent.PRE_TOOL_USE, command="echo first", priority=1))
        reg.add_rule(HookRule(tool_pattern="*", event=HookEvent.PRE_TOOL_USE, command="echo second", priority=2))
        runner = HookRunner(registry=reg)
        agg = await runner.run_hooks(HookEvent.PRE_TOOL_USE, "bash")
        assert len(agg.results) == 2
        assert agg.all_passed is True

    async def test_mixed_hook_types(self):
        async def func_hook(ctx):
            return {"exit_code": 0, "stdout": "func"}

        reg = HookRegistry()
        reg.add_rule(HookRule(
            tool_pattern="*", event=HookEvent.PRE_TOOL_USE,
            command="echo cmd", priority=1,
        ))
        reg.add_rule(HookRule(
            tool_pattern="*", event=HookEvent.PRE_TOOL_USE,
            hook_type=HookType.FUNCTION, callback=func_hook, priority=2,
        ))
        runner = HookRunner(registry=reg)
        agg = await runner.run_hooks(HookEvent.PRE_TOOL_USE, "bash")
        assert len(agg.results) == 2
        assert agg.all_passed is True

    async def test_run_hooks_different_events(self):
        reg = HookRegistry()
        reg.add_rule(HookRule(tool_pattern="*", event=HookEvent.PRE_TOOL_USE, command="echo pre"))
        reg.add_rule(HookRule(tool_pattern="*", event=HookEvent.POST_TOOL_USE, command="echo post"))
        runner = HookRunner(registry=reg)
        pre = await runner.run_hooks(HookEvent.PRE_TOOL_USE, "bash")
        post = await runner.run_hooks(HookEvent.POST_TOOL_USE, "bash")
        assert len(pre.results) == 1
        assert len(post.results) == 1

    async def test_parse_stdout_json_non_json(self):
        """Non-JSON stdout should not crash."""
        reg = self._registry_with_rule(command="echo 'not json'")
        runner = HookRunner(registry=reg)
        agg = await runner.run_hooks(HookEvent.PRE_TOOL_USE, "bash")
        assert agg.results[0].additional_context == ""
        assert agg.results[0].updated_input is None

    async def test_session_lifecycle_events(self):
        reg = HookRegistry()
        reg.add_rule(HookRule(tool_pattern="*", event=HookEvent.SESSION_START, command="echo start"))
        reg.add_rule(HookRule(tool_pattern="*", event=HookEvent.SESSION_END, command="echo end"))
        runner = HookRunner(registry=reg)
        start = await runner.run_hooks(HookEvent.SESSION_START)
        end = await runner.run_hooks(HookEvent.SESSION_END)
        assert start.all_passed
        assert end.all_passed

    async def test_file_changed_event(self):
        reg = HookRegistry()
        reg.add_rule(HookRule(tool_pattern="*", event=HookEvent.FILE_CHANGED, command="echo changed"))
        runner = HookRunner(registry=reg)
        agg = await runner.run_hooks(HookEvent.FILE_CHANGED, extra={"file": "test.py"})
        assert agg.all_passed
