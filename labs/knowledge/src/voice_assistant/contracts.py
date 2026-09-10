from __future__ import annotations

from typing import Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Principal(Model):
    id: str
    scopes: frozenset[str]


class Evidence(Model):
    source_id: str
    title: str
    version: str
    text: str


class SearchInput(Model):
    query: str = Field(min_length=1, max_length=2000)
    previous_sources: tuple[str, ...] = ()


class SearchResult(Model):
    evidence: tuple[Evidence, ...]
    publication: str
    omitted: int = 0


class Citation(Model):
    source_id: str
    title: str
    version: str
    quote: str


class Statement(Model):
    text: str = Field(min_length=1, max_length=1500)
    source_id: str
    quote: str = Field(min_length=10, max_length=1000)


class DraftAnswer(Model):
    status: Literal["answered", "not_found"]
    statements: tuple[Statement, ...] = Field(max_length=8)


class Answer(Model):
    session_id: str
    status: Literal["answered", "not_found", "evidence_only", "unavailable", "invalid_evidence"]
    message: str
    citations: tuple[Citation, ...] = ()
    sources: tuple[str, ...] = ()
    publication: str
    provider: str
    prompt_version: str
    elapsed_ms: int


class ReadPlugin(Protocol):
    id: str
    description: str
    scope: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]

    async def execute(self, value: BaseModel) -> BaseModel: ...


class AnswerProvider(Protocol):
    name: str
    async def answer(self, question: str, history: list[dict], evidence: tuple[Evidence, ...]) -> DraftAnswer: ...
    async def close(self) -> None: ...


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
