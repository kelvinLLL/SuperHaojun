"""Launch the WebUI server (FastAPI + uvicorn)."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from ..agent import Agent
from ..bus import MessageBus
from ..config import load_config
from ..constants import BRAND_DIR
from ..hooks.config import HookRegistry
from ..hooks.runner import HookRunner
from ..memory.store import MemoryStore
from ..prompt.builder import SystemPromptBuilder
from ..tools import ToolRegistry, register_builtin_tools
from .server import create_app


def main() -> None:
    config = load_config()
    bus = MessageBus()
    tool_registry = ToolRegistry()
    register_builtin_tools(tool_registry)

    working_dir = os.getcwd()
    tool_summaries = [
        {"name": t["function"]["name"], "description": t["function"].get("description", "")}
        for t in tool_registry.to_openai_tools()
    ]

    brand_root = Path(working_dir) / BRAND_DIR
    memory_store = MemoryStore(storage_dir=brand_root / "memory")

    hook_registry = HookRegistry.load(brand_root / "hooks.json")
    hook_runner = HookRunner(registry=hook_registry, working_dir=working_dir) if hook_registry.list_hooks() else None

    prompt_builder = SystemPromptBuilder(
        working_dir=working_dir,
        tool_summaries=tool_summaries,
        memory_text=memory_store.to_prompt_text(),
    )

    agent = Agent(
        config=config, bus=bus, registry=tool_registry,
        prompt_builder=prompt_builder, hook_runner=hook_runner,
    )

    app = create_app(
        agent=agent, bus=bus,
        hook_registry=hook_registry,
    )

    port = int(os.environ.get("SUPERHAOJUN_PORT", "8765"))
    print(f"🚀 SuperHaojun WebUI → http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
