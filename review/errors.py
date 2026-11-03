"""The single error type the CLI turns into a friendly message."""
from __future__ import annotations


class PipelineError(Exception):
    """A problem the researcher (or agent) can fix. `problems` lists each one."""

    def __init__(self, message: str, problems: list[str] | None = None):
        self.message = message
        self.problems = list(problems or [])
        detail = ''.join(f'\n  - {p}' for p in self.problems)
        super().__init__(message + detail)
