"""Typed, immutable data structures for the deterministic knowledge index.

Chunks and Q&A units are derived views of approved Markdown only. They carry verbatim
source text plus logical provenance (source ID, title, URI, heading path, char span) so a
caller can always trace an answer back to an approved document.
"""

from __future__ import annotations

from dataclasses import dataclass

KNOWLEDGE_URI_PREFIX = "knowledge://source/"

# Bumped whenever chunk boundaries or chunk IDs would change; read by ``_chunk_id``.
CHUNKER_VERSION = "chunker-v1"

QA_LANE_PREFIX = "qa/"


class InvalidQueryError(ValueError):
    """Raised when a search query is empty, wrongly typed, or over-long."""


@dataclass(frozen=True)
class Chunk:
    """One heading-aware slice of an approved document.

    ``text`` is an exact slice of the source (``source_text[start:end]``); ``heading_path``
    is the Markdown heading stack active at ``start`` and is kept out of the verbatim body.
    """

    chunk_id: str
    source_id: str
    title: str
    uri: str
    heading_path: tuple[str, ...]
    text: str
    start: int
    end: int

    @property
    def context(self) -> str:
        """Heading path used as the indexing prefix, separate from the verbatim body."""
        return "\n".join(self.heading_path)

    @property
    def index_text(self) -> str:
        """Text handed to tokens and embeddings: heading context first, then the body."""
        context = self.context
        return f"{context}\n{self.text}" if context else self.text


@dataclass(frozen=True)
class QaUnit:
    """One approved Q&A file, indexed as a single unit and returned verbatim.

    ``text`` is the complete file content; ``question`` and ``paraphrases`` are parsed from
    the heading line and ``answer`` from the ``## ตอบ`` section, used only for indexing.
    """

    source_id: str
    title: str
    uri: str
    question: str
    paraphrases: tuple[str, ...]
    answer: str
    text: str


@dataclass(frozen=True)
class QaHit:
    """A returned Q&A unit with its fused retrieval score."""

    source_id: str
    title: str
    uri: str
    question: str
    text: str
    score: float


@dataclass(frozen=True)
class ChunkHit:
    """A returned document chunk with its fused retrieval score."""

    chunk_id: str
    source_id: str
    title: str
    uri: str
    heading_path: tuple[str, ...]
    text: str
    start: int
    end: int
    score: float


@dataclass(frozen=True)
class SearchResult:
    """Bounded, source-attributed retrieval result: approved Q&A first, then chunks."""

    query: str
    qa: tuple[QaHit, ...]
    chunks: tuple[ChunkHit, ...]
    sources: tuple[str, ...]
    total_chars: int
