"""Brand and project-level constants."""

BRAND_NAME = "haojun"
"""Brand name used for directory paths (.haojun/) and instruction file discovery."""

BRAND_DIR = f".{BRAND_NAME}"
"""Dot-prefixed brand directory name."""

INSTRUCTION_FILES = ("SUPERHAOJUN.md", "AGENT.md")
"""Instruction files to discover in project directories (no CLAUDE.md to avoid conflict)."""

SYSTEM_PROMPT_DYNAMIC_BOUNDARY = "--- DYNAMIC CONTEXT BELOW ---"
"""Marker separating cacheable (stable) prompt sections from uncacheable (dynamic) ones."""
