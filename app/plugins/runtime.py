"""Typed contribution bundle returned by every enabled plugin factory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent.response_policy import ResponsePolicy
from app.llm.demo_behavior import DemoBehavior


@dataclass(frozen=True, slots=True)
class PluginRuntime:
    tool: Any
    response_policy: ResponsePolicy | None = None
    demo_behavior: DemoBehavior | None = None
