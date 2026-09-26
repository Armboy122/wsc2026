"""Public data contracts of the PEA Knowledge Voice Agent (no feature logic here)."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    """Use one camelCase JSON naming convention at every external boundary."""
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class FrozenModel(BaseModel):
    """Base class for immutable value objects crossing module boundaries."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
        alias_generator=to_camel,
    )


class ToolErrorCode(str, Enum):
    """Structured failure codes returned by the Knowledge tool to Gemini Live."""

    INVALID_INPUT = "invalid_input"
    UNAVAILABLE = "unavailable"
    INTERNAL = "internal"


class KnowledgeIndexHealth(FrozenModel):
    """Lifecycle status of the derived knowledge index (counts only, no paths or content)."""

    status: Literal["building", "ready", "stale", "error"]
    documents: int = Field(ge=0)
    chunks: int = Field(ge=0)


class HealthResponse(FrozenModel):
    status: Literal["ok", "degraded"]
    knowledge_backend: Literal["ready", "unavailable"] = Field(serialization_alias="knowledgeBackend")
    live_voice: Literal["configured", "not_configured"] = Field(serialization_alias="liveVoice")
    knowledge_index: KnowledgeIndexHealth = Field(serialization_alias="knowledgeIndex")
