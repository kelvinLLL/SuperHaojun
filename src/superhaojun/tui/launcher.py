"""Launch the Rich TUI through the shared runtime assembly."""

from __future__ import annotations

import asyncio
import os

from ..runtime import AppRuntime, build_runtime
from .app import TUIApp


async def run_tui(runtime: AppRuntime) -> None:
    """Run the TUI with the shared runtime lifecycle."""
    app = TUIApp(
        agent=runtime.agent,
        cmd_registry=runtime.command_registry,
        history_file=str(runtime.brand_root / "input_history"),
        command_context=runtime.build_command_context(),
    )
    try:
        await runtime.startup()
        await app.run()
    finally:
        await runtime.shutdown()


def main() -> None:
    runtime = build_runtime(working_dir=os.getcwd())
    asyncio.run(run_tui(runtime))
