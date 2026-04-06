"""LSP package — Language Server Protocol passive integration.

Connects to language servers to provide code intelligence:
- Diagnostics (errors/warnings)
- Hover information (type info, docs)
- Go-to-definition references
- Code completions

Context is injected into the prompt via LSPContextSection.
"""

from .client import LSPClient
from .service import LSPService

__all__ = ["LSPClient", "LSPService"]
