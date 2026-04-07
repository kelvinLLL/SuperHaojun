"""LSP package — Language Server Protocol passive integration.

Connects to language servers to provide code intelligence:
- Diagnostics (errors/warnings)
- Hover information (type info, docs)
- Go-to-definition references
- Code completions

Context is injected into the prompt via LSPContextSection.
"""

from .client import Diagnostic, HoverInfo, LSPClient, Location
from .diagnostics import DiagnosticRegistry, DiagnosticSource
from .managed import LSPState, ManagedLSPClient
from .service import LSPService, LSPServerConfig

__all__ = [
    "Diagnostic", "DiagnosticRegistry", "DiagnosticSource",
    "HoverInfo", "LSPClient", "LSPServerConfig", "LSPService",
    "LSPState", "Location", "ManagedLSPClient",
]
