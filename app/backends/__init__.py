"""Simulated PEA backend adapters: deterministic, in-memory, and resettable.

These adapters hold no live PEA state and make no real-world side effects. Each
operational result they feed back through the tools is marked ``simulation: true``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.contracts import ToolErrorCode

_MOCK_DIR = Path(__file__).resolve().parents[2] / "data" / "mock"


class BackendError(Exception):
    """A typed, user-safe error raised by a simulated backend.

    ``code`` is one of the frozen :class:`ToolErrorCode` values; ``message`` must
    never contain credentials or internal identifiers beyond what is user-safe.
    """

    def __init__(self, code: ToolErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def load_mock_json(name: str) -> Any:
    """Load a deterministic fixture file from the repository's ``data/mock`` tree."""
    with (_MOCK_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)
