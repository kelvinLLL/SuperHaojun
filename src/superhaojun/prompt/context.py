"""PromptContext and GitInfo — shared state for prompt section builders."""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class GitInfo:
    """Collected git repository information."""
    branch: str = ""
    status: str = ""
    log: str = ""
    diff_stat: str = ""
    remote: str = ""

    @property
    def available(self) -> bool:
        return bool(self.branch)


@dataclass
class PromptContext:
    """Build-time context shared across all PromptSection instances."""

    working_dir: str = ""
    tool_summaries: list[dict[str, str]] = field(default_factory=list)
    memory_text: str = ""
    custom_instructions: str = ""
    git_info: GitInfo | None = None
    session_summary: str = ""


async def _run_git(cwd: str, *args: str, timeout: float = 5.0) -> str:
    """Run a single git command, return stdout or empty string on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode != 0:
            return ""
        return stdout.decode().strip()
    except (asyncio.TimeoutError, FileNotFoundError, OSError):
        return ""


async def gather_git_info(cwd: str) -> GitInfo:
    """Collect git info with 5-way parallel execution."""
    branch, status, log, diff_stat, remote = await asyncio.gather(
        _run_git(cwd, "rev-parse", "--abbrev-ref", "HEAD"),
        _run_git(cwd, "status", "--short"),
        _run_git(cwd, "log", "--oneline", "-5"),
        _run_git(cwd, "diff", "--stat", "HEAD"),
        _run_git(cwd, "remote", "-v"),
    )
    # Truncate status/diff_stat to 200 chars
    if len(status) > 200:
        status = status[:200] + "..."
    if len(diff_stat) > 200:
        diff_stat = diff_stat[:200] + "..."
    return GitInfo(
        branch=branch,
        status=status,
        log=log,
        diff_stat=diff_stat,
        remote=remote,
    )


def gather_git_info_sync(cwd: str) -> GitInfo:
    """Synchronous fallback for gathering git info (2-way)."""
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=cwd, timeout=5,
        )
        if branch.returncode != 0:
            return GitInfo()

        status = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True, text=True, cwd=cwd, timeout=5,
        )
        status_text = status.stdout.strip()
        if len(status_text) > 200:
            status_text = status_text[:200] + "..."

        return GitInfo(branch=branch.stdout.strip(), status=status_text)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return GitInfo()
