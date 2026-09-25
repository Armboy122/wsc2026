"""Selected-document Knowledge service: validated, complete, and answer-free.

The service turns a model-selected set of catalog source IDs into the complete Markdown
text of those approved documents. It never summarizes, never truncates silently, never
answers, and never calls a generative provider: it validates selection, reads files, and
returns structured provenance. Everything that can go wrong returns a structured, safe
failure instead of raising or guessing.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from app.contracts import ToolErrorCode
from app.knowledge.catalog import KnowledgeCatalog

DEFAULT_MAX_DOCUMENTS = 5
DEFAULT_MAX_TOTAL_CHARS = 120_000
KNOWLEDGE_URI_PREFIX = "knowledge://source/"

USER_SAFE_INVALID_SELECTION = (
    "รายการเอกสารที่เลือกไม่ถูกต้อง กรุณาเลือก sourceId จากแค็ตตาล็อกที่ให้ไว้เท่านั้น"
)
USER_SAFE_TOO_MANY_DOCUMENTS = "เลือกเอกสารเกินจำนวนที่อนุญาตในหนึ่งครั้ง"
USER_SAFE_CONTEXT_EXCEEDED = (
    "เนื้อหาของเอกสารที่เลือกเกินขอบเขตที่ระบบรองรับ กรุณาเลือกเอกสารให้แคบลง"
)
USER_SAFE_DOCUMENT_UNAVAILABLE = "อ่านเอกสารที่เลือกไม่สำเร็จ กรุณาลองใหม่อีกครั้ง"

_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class DocumentContent:
    """Complete approved document content with logical provenance."""

    source_id: str
    title: str
    uri: str
    content: str


@dataclass(frozen=True)
class SelectionFailure:
    """Structured safe failure for a rejected selection."""

    code: ToolErrorCode
    message: str


@dataclass(frozen=True)
class SelectionResult:
    """Either complete documents or one structured failure, never both."""

    documents: tuple[DocumentContent, ...] = field(default=())
    failure: SelectionFailure | None = None

    @property
    def ok(self) -> bool:
        return self.failure is None


class KnowledgeDocumentService:
    """Read approved documents selected by source ID, within explicit limits."""

    def __init__(
        self,
        catalog: KnowledgeCatalog,
        *,
        max_documents: int = DEFAULT_MAX_DOCUMENTS,
        max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
    ) -> None:
        if max_documents < 1:
            raise ValueError("max_documents must be at least 1")
        if max_total_chars < 1:
            raise ValueError("max_total_chars must be at least 1")
        self._catalog = catalog
        self._max_documents = max_documents
        self._max_total_chars = max_total_chars

    @property
    def catalog(self) -> KnowledgeCatalog:
        return self._catalog

    @property
    def max_documents(self) -> int:
        return self._max_documents

    @property
    def max_total_chars(self) -> int:
        return self._max_total_chars

    def catalog_entries(self) -> tuple[dict[str, object], ...]:
        """Compact selectable metadata for the conversational model."""
        return self._catalog.entries()

    def select(self, source_ids: Sequence[str]) -> SelectionResult:
        """Return complete content for every selected approved document."""
        validated = self._validate(source_ids)
        if isinstance(validated, SelectionFailure):
            return SelectionResult(failure=validated)

        documents: list[DocumentContent] = []
        total_chars = 0
        for source_id in validated:
            document = self._catalog.get(source_id)
            if document is None:
                return SelectionResult(failure=_invalid_selection())
            try:
                content = _read_document(document.path)
            except (OSError, UnicodeError):
                return SelectionResult(
                    failure=SelectionFailure(
                        code=ToolErrorCode.UNAVAILABLE,
                        message=USER_SAFE_DOCUMENT_UNAVAILABLE,
                    )
                )
            total_chars += len(content)
            if total_chars > self._max_total_chars:
                return SelectionResult(
                    failure=SelectionFailure(
                        code=ToolErrorCode.INVALID_INPUT,
                        message=USER_SAFE_CONTEXT_EXCEEDED,
                    )
                )
            documents.append(
                DocumentContent(
                    source_id=document.source_id,
                    title=document.title,
                    uri=f"{KNOWLEDGE_URI_PREFIX}{document.source_id}",
                    content=content,
                )
            )
        return SelectionResult(documents=tuple(documents))

    def _validate(self, source_ids: Sequence[str]) -> tuple[str, ...] | SelectionFailure:
        if isinstance(source_ids, (str, bytes)) or not isinstance(source_ids, Sequence):
            return _invalid_selection()
        if not source_ids:
            return _invalid_selection()
        if len(source_ids) > self._max_documents:
            return SelectionFailure(
                code=ToolErrorCode.INVALID_INPUT,
                message=USER_SAFE_TOO_MANY_DOCUMENTS,
            )
        seen: set[str] = set()
        for source_id in source_ids:
            if not isinstance(source_id, str) or not is_safe_source_id(source_id):
                return _invalid_selection()
            if source_id in seen:
                return _invalid_selection()
            if self._catalog.get(source_id) is None:
                return _invalid_selection()
            seen.add(source_id)
        return tuple(source_ids)


def is_safe_source_id(value: str) -> bool:
    """Accept only a relative POSIX source ID that cannot escape the approved root."""
    if not value or value != value.strip() or value != value.strip("/"):
        return False
    if "\\" in value or value.startswith("/") or _DRIVE_PREFIX.match(value):
        return False
    parts = value.split("/")
    if any(part in {"", ".", ".."} or part.startswith(".") for part in parts):
        return False
    return all(part.strip() == part for part in parts)


def _read_document(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _invalid_selection() -> SelectionFailure:
    return SelectionFailure(
        code=ToolErrorCode.INVALID_INPUT,
        message=USER_SAFE_INVALID_SELECTION,
    )
