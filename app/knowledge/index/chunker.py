"""Heading-aware, lossless Markdown chunking and approved Q&A unit parsing.

Chunking is deliberately configuration-free. A document is split into contiguous character
spans at ``#``–``###`` headings; tiny consecutive sections are merged, oversize spans are cut
at paragraph or line boundaries, and every chunk body is an exact slice of the source text
(``source_text[start:end]``), so concatenating chunk bodies reproduces the source exactly.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.knowledge.index.models import (
    CHUNKER_VERSION,
    KNOWLEDGE_URI_PREFIX,
    Chunk,
    QaUnit,
)

MAX_CHUNK_CHARS = 1200
MIN_CHUNK_CHARS = 400
_MIN_CUT_GAP = 200

_HEADING = re.compile(r"^(?P<level>#{1,3})[ \t]+(?P<text>.+?)[ \t]*#*[ \t]*$")
_FENCE = re.compile(r"^[ \t]*(?:```|~~~)")

_QA_PARA_SEP = "| คำถามใกล้เคียง:"
_QA_ANSWER = re.compile(
    r"^##[ \t]+ตอบ[ \t]*\r?\n(?P<body>.*?)(?=^##[ \t]|\Z)",
    re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True)
class _Section:
    heading_path: tuple[str, ...]
    start: int
    end: int


@dataclass(frozen=True)
class _Span:
    heading_path: tuple[str, ...]
    start: int
    end: int


def chunk_markdown(source_id: str, title: str, text: str) -> tuple[Chunk, ...]:
    """Split one approved document into deterministic, verbatim chunks."""
    if not text:
        return ()
    spans = _split_oversize(_merge_sections(_split_sections(text)), text)
    return tuple(
        Chunk(
            chunk_id=_chunk_id(source_id, span.start, span.end),
            source_id=source_id,
            title=title,
            uri=f"{KNOWLEDGE_URI_PREFIX}{source_id}",
            heading_path=span.heading_path,
            text=text[span.start : span.end],
            start=span.start,
            end=span.end,
        )
        for span in spans
    )


def parse_qa_unit(source_id: str, title: str, text: str) -> QaUnit:
    """Parse one ``qa_*.md`` file into a single Q&A unit whose ``text`` stays verbatim."""
    head = text.split("\n", 1)[0].lstrip("#").strip()
    main, _, paraphrase_part = head.partition(_QA_PARA_SEP)
    question = main.replace("ถาม:", "").strip()
    paraphrases = tuple(
        part.strip() for part in paraphrase_part.split("/") if part.strip()
    )
    answer_match = _QA_ANSWER.search(text)
    answer = answer_match.group("body").strip() if answer_match else text.strip()
    return QaUnit(
        source_id=source_id,
        title=question or title,
        uri=f"{KNOWLEDGE_URI_PREFIX}{source_id}",
        question=question or title,
        paraphrases=paraphrases,
        answer=answer,
        text=text,
    )


def qa_index_text(unit: QaUnit, *, include_paraphrases: bool = True) -> str:
    """Text used to score a Q&A unit: question, optional paraphrases, then the answer."""
    parts = [unit.question]
    if include_paraphrases:
        parts.extend(unit.paraphrases)
    parts.append(unit.answer)
    return "\n".join(part for part in parts if part)


def _chunk_id(source_id: str, start: int, end: int) -> str:
    payload = f"{CHUNKER_VERSION}|{source_id}|{start}|{end}"
    # blake2b keeps chunk IDs stable across processes without a security requirement.
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=8).hexdigest()


def _split_sections(text: str) -> list[_Section]:
    """Partition ``text`` into contiguous sections at level 1–3 headings."""
    boundaries: list[tuple[int, tuple[str, ...]]] = []
    stack: list[tuple[int, str]] = []
    in_fence = False
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        if _FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence and (match := _HEADING.match(line)) is not None:
            level = len(match.group("level"))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, match.group("text").strip()))
            boundaries.append((offset, tuple(heading for _, heading in stack)))
        offset += len(raw_line)

    if not boundaries:
        return [_Section((), 0, len(text))]

    sections: list[_Section] = []
    if boundaries[0][0] > 0:
        sections.append(_Section((), 0, boundaries[0][0]))
    for index, (start, heading_path) in enumerate(boundaries):
        end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(text)
        sections.append(_Section(heading_path, start, end))
    return sections


def _merge_sections(sections: list[_Section]) -> list[_Span]:
    """Merge consecutive tiny sections so headings do not produce fragment chunks."""
    merged: list[_Span] = []
    for section in sections:
        if merged:
            previous = merged[-1]
            if (
                previous.end - previous.start < MIN_CHUNK_CHARS
                and section.end - previous.start <= MAX_CHUNK_CHARS
            ):
                merged[-1] = _Span(previous.heading_path, previous.start, section.end)
                continue
        merged.append(_Span(section.heading_path, section.start, section.end))

    if len(merged) >= 2:
        last = merged[-1]
        previous = merged[-2]
        if last.end - last.start < MIN_CHUNK_CHARS and last.end - previous.start <= MAX_CHUNK_CHARS:
            merged[-2] = _Span(previous.heading_path, previous.start, last.end)
            merged.pop()
    return merged


def _split_oversize(spans: list[_Span], text: str) -> list[_Span]:
    """Cut spans longer than ``MAX_CHUNK_CHARS`` at paragraph/line boundaries."""
    result: list[_Span] = []
    for span in spans:
        cursor = span.start
        while span.end - cursor > MAX_CHUNK_CHARS:
            cut = _find_cut(text, cursor, cursor + MAX_CHUNK_CHARS)
            result.append(_Span(span.heading_path, cursor, cut))
            cursor = cut
        result.append(_Span(span.heading_path, cursor, span.end))
    return result


def _find_cut(text: str, cursor: int, limit: int) -> int:
    """Largest cut offset in ``(cursor, limit]`` preferring paragraph then line boundaries."""
    window = text[cursor:limit]
    paragraph = None
    for match in re.finditer(r"\n[ \t]*\n", window):
        paragraph = cursor + match.end()
    if paragraph is not None and paragraph - cursor >= _MIN_CUT_GAP:
        return paragraph
    newline = window.rfind("\n")
    if newline != -1 and cursor + newline + 1 - cursor >= _MIN_CUT_GAP:
        return cursor + newline + 1
    return limit
