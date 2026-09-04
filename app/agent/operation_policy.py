"""Operation policy vocabulary for V2: the 4 policy kinds, limits, and clientContext."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class OperationPolicy(str, Enum):
    GROUNDED_ANSWER = "grounded_answer"
    WRITE_CONFIRM = "write_confirm"
    GUIDED_FLOW = "guided_flow"
    PLAIN_READ = "plain_read"


class ClientContextKey(str, Enum):
    LAT = "lat"
    LON = "lon"


KNOWN_CLIENT_CONTEXT = frozenset({key.value for key in ClientContextKey})


DEFAULT_POLICY = OperationPolicy.PLAIN_READ


def dedupe_default(policy: OperationPolicy) -> bool:
    """Default for dedupeIdenticalInput per CONTRACTS-V2 §3.3."""
    if policy in (OperationPolicy.PLAIN_READ, OperationPolicy.GROUNDED_ANSWER):
        return True
    # write_confirm and guided_flow: no dedupe by default
    return False


@dataclass(frozen=True, slots=True)
class OperationLimits:
    max_calls_per_turn: int | None = None
    dedupe_identical_input: bool | None = None

    def __post_init__(self) -> None:
        if self.max_calls_per_turn is not None and self.max_calls_per_turn <= 0:
            raise ValueError("max_calls_per_turn must be positive")
        if self.dedupe_identical_input is not None and not isinstance(
            self.dedupe_identical_input, bool
        ):
            raise ValueError("dedupe_identical_input must be boolean")

    def effective_dedupe(self, policy: OperationPolicy) -> bool:
        if self.dedupe_identical_input is not None:
            return self.dedupe_identical_input
        return dedupe_default(policy)


@dataclass(frozen=True, slots=True)
class OperationSpec:
    policy: OperationPolicy = DEFAULT_POLICY
    limits: OperationLimits | None = None
    client_context: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if self.client_context is not None:
            for key in self.client_context:
                if key not in KNOWN_CLIENT_CONTEXT:
                    raise ValueError(
                        f"clientContext key '{key}' not in known closed set {sorted(KNOWN_CLIENT_CONTEXT)}"
                    )
                if not self.client_context[key]:
                    raise ValueError("clientContext field must be non-empty string")