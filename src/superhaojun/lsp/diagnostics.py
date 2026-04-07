"""DiagnosticRegistry — per-file diagnostic aggregation with deduplication.

v2 addition: Tracks diagnostics from multiple sources (LSP servers, hooks),
deduplicates by (file, line, message), tracks which diagnostics were injected
by hooks vs native LSP.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .client import Diagnostic


@dataclass(frozen=True)
class DiagnosticSource:
    """Identifies where a diagnostic came from."""
    provider: str  # "lsp:python", "hook:lint", etc.
    file_path: str
    line: int
    character: int
    message: str
    severity: int = 1  # 1=error, 2=warning, 3=info, 4=hint

    @property
    def dedup_key(self) -> tuple:
        return (self.file_path, self.line, self.message)


@dataclass
class DiagnosticRegistry:
    """Per-file diagnostic aggregation with deduplication.

    Tracks:
    - Native LSP diagnostics (from language servers)
    - Injected diagnostics (from hooks, external linters)
    - Deduplication by (file, line, message)
    """
    _diagnostics: dict[str, list[DiagnosticSource]] = field(default_factory=dict)
    _seen_keys: set[tuple] = field(default_factory=set)

    def update_file(self, file_path: str, provider: str, diagnostics: list[Diagnostic]) -> None:
        """Replace diagnostics for a file+provider pair. Handles dedup."""
        # Remove old diagnostics from this provider for this file
        self._remove_provider(file_path, provider)

        for diag in diagnostics:
            source = DiagnosticSource(
                provider=provider,
                file_path=file_path,
                line=diag.line,
                character=diag.character,
                message=diag.message,
                severity=diag.severity,
            )
            if source.dedup_key not in self._seen_keys:
                self._seen_keys.add(source.dedup_key)
                self._diagnostics.setdefault(file_path, []).append(source)

    def inject(self, file_path: str, provider: str, line: int, message: str,
               severity: int = 1, character: int = 0) -> None:
        """Inject a single diagnostic (e.g., from a hook)."""
        source = DiagnosticSource(
            provider=provider, file_path=file_path,
            line=line, character=character,
            message=message, severity=severity,
        )
        if source.dedup_key not in self._seen_keys:
            self._seen_keys.add(source.dedup_key)
            self._diagnostics.setdefault(file_path, []).append(source)

    def get_file(self, file_path: str) -> list[DiagnosticSource]:
        """Get all diagnostics for a file."""
        return list(self._diagnostics.get(file_path, []))

    def get_all(self) -> list[DiagnosticSource]:
        """Get all diagnostics across all files."""
        result: list[DiagnosticSource] = []
        for diags in self._diagnostics.values():
            result.extend(diags)
        return result

    def get_errors(self, file_path: str | None = None) -> list[DiagnosticSource]:
        """Get error-level diagnostics."""
        source = self.get_file(file_path) if file_path else self.get_all()
        return [d for d in source if d.severity == 1]

    def clear_file(self, file_path: str) -> None:
        """Clear all diagnostics for a file."""
        removed = self._diagnostics.pop(file_path, [])
        for d in removed:
            self._seen_keys.discard(d.dedup_key)

    def clear_all(self) -> None:
        self._diagnostics.clear()
        self._seen_keys.clear()

    def to_prompt_context(self, max_errors: int = 10) -> str:
        """Produce text summary for prompt injection."""
        errors = self.get_errors()
        if not errors:
            return ""
        lines = ["## Diagnostics"]
        for d in errors[:max_errors]:
            lines.append(f"  ERROR [{d.provider}] {d.file_path}:{d.line+1}: {d.message}")
        if len(errors) > max_errors:
            lines.append(f"  ... and {len(errors) - max_errors} more errors")
        return "\n".join(lines)

    @property
    def total_count(self) -> int:
        return sum(len(d) for d in self._diagnostics.values())

    def _remove_provider(self, file_path: str, provider: str) -> None:
        """Remove all diagnostics from a specific provider for a file."""
        diags = self._diagnostics.get(file_path, [])
        remaining = []
        for d in diags:
            if d.provider == provider:
                self._seen_keys.discard(d.dedup_key)
            else:
                remaining.append(d)
        if remaining:
            self._diagnostics[file_path] = remaining
        elif file_path in self._diagnostics:
            del self._diagnostics[file_path]
