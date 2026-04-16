"""Launch the WebUI server (FastAPI + uvicorn)."""

from __future__ import annotations

import asyncio
import os

import uvicorn

from ..runtime import build_runtime
from .server import create_app


def main() -> None:
    runtime = build_runtime(working_dir=os.getcwd())

    app = create_app(
        agent=runtime.agent,
        bus=runtime.bus,
        mcp_manager=runtime.mcp_manager,
        hook_registry=runtime.hook_registry,
        model_registry=runtime.model_registry,
        command_registry=runtime.command_registry,
        session_manager=runtime.session_manager,
        memory_store=runtime.memory_store,
        extension_runtime=runtime.extension_runtime,
    )

    port = int(os.environ.get("SUPERHAOJUN_PORT", "8765"))
    active = runtime.model_registry.active
    print(f"🚀 SuperHaojun WebUI → http://localhost:{port}")
    print(f"   Model: {active.model_id} @ {active.base_url}")
    print(f"   Profiles: {', '.join(runtime.model_registry.profiles)}")
    try:
        asyncio.run(runtime.startup())
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    finally:
        asyncio.run(runtime.shutdown())
