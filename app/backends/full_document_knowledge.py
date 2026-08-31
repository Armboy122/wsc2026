"""Fail-closed Gemini long-context knowledge backend for approved DOCX files.

The first model call receives catalog metadata only and selects document identifiers.  A
second call receives only the selected, complete documents; this module never uses File
Search, embeddings, chunking, or an index.
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote
from xml.etree import ElementTree

from app.contracts import Citation, ToolErrorCode

ENV_API_KEY = "GEMINI_API_KEY"
ENV_FALLBACK_API_KEY = "GOOGLE_API_KEY"
DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_READINESS_TIMEOUT_SECONDS = 5.0
DEFAULT_SOURCE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "source"
DEFAULT_HARD_CONTEXT_CHARS = 1_000_000
MAX_ANSWER_CONTEXT_CHARS = 4000
MAX_SNIPPET_CHARS = 1000
USER_SAFE_NOT_CONFIGURED = (
    "เซิร์ฟเวอร์นี้ยังไม่ได้ตั้งค่าบริการความรู้ "
    "กรุณาติดต่อผู้ดูแลระบบเพื่อตรวจสอบการตั้งค่าบริการ"
)
USER_SAFE_UNAVAILABLE = "บริการความรู้ไม่พร้อมใช้งานชั่วคราว กรุณาลองใหม่อีกสักครู่"

ClientFactory = Callable[[str], Any]


class KnowledgeBackendError(Exception):
    """ข้อผิดพลาดแบบมีชนิดและปลอดภัยสำหรับแสดงแก่ผู้ใช้"""

    def __init__(self, code: ToolErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class GroundedEvidence:
    """คำตอบจากข้อความฉบับเต็มพร้อม citation ที่ตรวจสอบแล้ว"""

    answer_context: str
    result_count: int
    citations: tuple[Citation, ...]
_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass(frozen=True)
class _Document:
    source_id: str
    path: Path
    filename: str
    title: str


class FullDocumentKnowledgeBackend:
    """Route a query to allowlisted DOCX files, then ground Gemini on their full text."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        source_root: Path | str = DEFAULT_SOURCE_ROOT,
        model: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        readiness_timeout_seconds: float = DEFAULT_READINESS_TIMEOUT_SECONDS,
        client_factory: ClientFactory | None = None,
        hard_context_chars: int = DEFAULT_HARD_CONTEXT_CHARS,
    ) -> None:
        self._api_key = api_key if api_key is not None else (
            os.environ.get(ENV_API_KEY) or os.environ.get(ENV_FALLBACK_API_KEY)
        )
        self._source_root = Path(source_root)
        self._model = model or DEFAULT_MODEL
        self._timeout_seconds = timeout_seconds
        self._readiness_timeout_seconds = readiness_timeout_seconds
        self._client_factory = client_factory
        self._hard_context_chars = hard_context_chars
        self._text_cache: dict[tuple[str, int, int], str] = {}

    @property
    def model(self) -> str:
        return self._model

    def is_configured(self) -> bool:
        return bool(self._api_key and self._source_root.is_dir() and self._hard_context_chars > 0)

    async def is_ready(self) -> bool:
        if not self.is_configured():
            return False
        try:
            await asyncio.wait_for(asyncio.to_thread(self._ready_sync), self._readiness_timeout_seconds)
        except Exception:
            return False
        return True

    def _ready_sync(self) -> None:
        if not self._catalog():
            raise ValueError("no approved DOCX documents")
        self._make_client()

    async def search(self, query: str, max_results: int) -> GroundedEvidence:
        """ให้ router และ answer call ได้รับ timeout budget แยกกัน"""
        try:
            if not self.is_configured():
                raise KnowledgeBackendError(ToolErrorCode.UNAVAILABLE, USER_SAFE_NOT_CONFIGURED)
            if not isinstance(query, str) or not query.strip() or max_results < 1:
                return GroundedEvidence("", 0, ())

            catalog = await asyncio.to_thread(self._catalog)
            if not catalog:
                return GroundedEvidence("", 0, ())
            client = self._make_client()
            selected_ids = await asyncio.wait_for(
                asyncio.to_thread(self._route, client, query, catalog, max_results),
                self._timeout_seconds,
            )
            if not selected_ids:
                return GroundedEvidence("", 0, ())

            selected = [catalog[source_id] for source_id in selected_ids]
            texts: dict[str, str] = {}
            for document in selected:
                try:
                    texts[document.source_id] = await asyncio.to_thread(
                        self._full_text, document
                    )
                except (OSError, ValueError, zipfile.BadZipFile, ElementTree.ParseError):
                    return GroundedEvidence("", 0, ())
            if sum(len(text) for text in texts.values()) > self._hard_context_chars:
                return GroundedEvidence("", 0, ())

            return await asyncio.wait_for(
                asyncio.to_thread(self._answer, client, query, selected, texts),
                self._timeout_seconds,
            )
        except KnowledgeBackendError:
            raise
        except asyncio.TimeoutError as exc:
            raise KnowledgeBackendError(ToolErrorCode.UNAVAILABLE, USER_SAFE_UNAVAILABLE) from exc
        except Exception as exc:
            raise KnowledgeBackendError(ToolErrorCode.UNAVAILABLE, USER_SAFE_UNAVAILABLE) from exc

    def _make_client(self) -> Any:
        if self._client_factory is not None:
            return self._client_factory(self._api_key)
        from google import genai
        return genai.Client(api_key=self._api_key)

    def _catalog(self) -> dict[str, _Document]:
        root = self._source_root.resolve(strict=True)
        if not root.is_dir():
            return {}
        catalog: dict[str, _Document] = {}
        for candidate in root.rglob("*"):
            if candidate.suffix.lower() != ".docx" or candidate.is_symlink() or not candidate.is_file():
                continue
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(root):
                continue
            source_id = candidate.relative_to(root).as_posix()
            if source_id.startswith(".") or source_id in catalog:
                continue
            try:
                title = _extract_docx_title(candidate)
            except (OSError, ValueError, zipfile.BadZipFile, ElementTree.ParseError):
                continue
            catalog[source_id] = _Document(source_id, candidate, candidate.name, title)
        return catalog

    def _route(
        self, client: Any, query: str, catalog: dict[str, _Document], max_results: int
    ) -> list[str]:
        metadata = [
            {"sourceId": item.source_id, "filename": item.filename, "title": item.title}
            for item in catalog.values()
        ]
        prompt = (
            "Select documents relevant to the Thai user query. You only know this catalog, "
            "not document contents. A follow-up query may contain a current question plus prior "
            "document/topic context; select for the current question and use prior context only "
            "to disambiguate it. Return JSON only, exactly {\"sourceIds\":[...]} with no "
            f"more than {max_results} unique sourceIds. Query: {query}\nCatalog: "
            + json.dumps(metadata, ensure_ascii=False)
        )
        data = _json_response(client, self._model, prompt)
        if not isinstance(data, dict) or set(data) != {"sourceIds"}:
            return []
        source_ids = data.get("sourceIds")
        if not isinstance(source_ids, list) or not source_ids or len(source_ids) > max_results:
            return []
        if any(not isinstance(source_id, str) for source_id in source_ids):
            return []
        if len(set(source_ids)) != len(source_ids) or any(source_id not in catalog for source_id in source_ids):
            return []
        return source_ids

    def _full_text(self, document: _Document) -> str:
        status = document.path.stat()
        cache_key = (document.source_id, status.st_mtime_ns, status.st_size)
        if cache_key in self._text_cache:
            return self._text_cache[cache_key]
        text = _extract_docx_text(document.path)
        if not text.strip():
            raise ValueError("empty document")
        self._text_cache = {
            key: value for key, value in self._text_cache.items() if key[0] != document.source_id
        }
        self._text_cache[cache_key] = text
        return text

    def _answer(
        self, client: Any, query: str, selected: list[_Document], texts: dict[str, str]
    ) -> GroundedEvidence:
        blocks = "\n\n".join(
            f"<source sourceId={json.dumps(doc.source_id)} filename={json.dumps(doc.filename)}>\n"
            f"{texts[doc.source_id]}\n</source>"
            for doc in selected
        )
        prompt = (
            "Answer the Thai user directly and completely using only the full documents below. "
            "If the query labels a current question and prior context, answer only the current "
            "question; use the prior context solely to identify what it refers to. "
            "Do not provide links or a summary. Return JSON only exactly in this shape: "
            "{\"answer\":string,\"citations\":[{\"sourceId\":string,\"snippet\":string}]}. "
            "Every citation snippet must be one short contiguous passage copied verbatim "
            "from its cited source, at most 200 characters; preserve its whitespace exactly "
            "and never combine or reformat separate passages. "
            f"Query: {query}\nDocuments:\n{blocks}"
        )
        data = _json_response(client, self._model, prompt)
        if not isinstance(data, dict) or set(data) != {"answer", "citations"}:
            return GroundedEvidence("", 0, ())
        answer, raw_citations = data.get("answer"), data.get("citations")
        if not isinstance(answer, str) or not answer.strip() or len(answer) > MAX_ANSWER_CONTEXT_CHARS:
            return GroundedEvidence("", 0, ())
        if not isinstance(raw_citations, list) or not raw_citations:
            return GroundedEvidence("", 0, ())
        allowed = {document.source_id: document for document in selected}
        citations: list[Citation] = []
        for item in raw_citations:
            if not isinstance(item, dict) or set(item) != {"sourceId", "snippet"}:
                return GroundedEvidence("", 0, ())
            source_id, snippet = item.get("sourceId"), item.get("snippet")
            if (
                not isinstance(source_id, str)
                or not isinstance(snippet, str)
                or not snippet
                or len(snippet) > MAX_SNIPPET_CHARS
                or source_id not in allowed
                or snippet not in texts[source_id]
            ):
                return GroundedEvidence("", 0, ())
            document = allowed[source_id]
            citations.append(Citation(
                source_id=source_id,
                title=document.title,
                uri="knowledge://source/" + quote(source_id, safe="/"),
                snippet=snippet,
            ))
        return GroundedEvidence(answer, len({citation.source_id for citation in citations}), tuple(citations))


def _json_response(client: Any, model: str, prompt: str) -> Any:
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    text = getattr(response, "text", None)
    if not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


_CORE_TITLE = "{http://purl.org/dc/elements/1.1/}title"
_SUPPORTED_FIXED_TEXT_PARTS = frozenset(
    {
        "word/document.xml",
        "word/footnotes.xml",
        "word/endnotes.xml",
        "word/comments.xml",
    }
)


def _validate_archive_members(archive: zipfile.ZipFile) -> tuple[str, ...]:
    """ตรวจสอบสมาชิก ZIP และคืนชื่อแบบปกติโดยไม่แตกไฟล์ลงดิสก์"""
    names: list[str] = []
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        parts = Path(name).parts
        if (
            name.startswith("/")
            or (len(name) >= 3 and name[1:3] == ":/")
            or ".." in parts
            or stat.S_ISLNK(info.external_attr >> 16)
        ):
            raise ValueError("unsafe DOCX archive member")
        names.append(name)
    return tuple(names)


def _paragraph_text(root: ElementTree.Element) -> list[str]:
    """คืนข้อความตามลำดับ Word XML โดยคง line break และ tab ภายในย่อหน้า"""
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{_WORD_NS}p"):
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == f"{_WORD_NS}t":
                parts.append(node.text or "")
            elif node.tag in {f"{_WORD_NS}br", f"{_WORD_NS}cr"}:
                parts.append("\n")
            elif node.tag == f"{_WORD_NS}tab":
                parts.append("\t")
        text = "".join(parts)
        if text:
            paragraphs.append(text)
    return paragraphs


def _is_supported_text_part(name: str) -> bool:
    return (
        name in _SUPPORTED_FIXED_TEXT_PARTS
        or (name.startswith("word/header") and name.endswith(".xml"))
        or (name.startswith("word/footer") and name.endswith(".xml"))
    )


def _extract_docx_title(path: Path) -> str:
    """อ่านชื่อเอกสารจาก core properties หรือหัวเรื่องย่อหน้าแรกแบบ fail closed"""
    with zipfile.ZipFile(path) as archive:
        names = _validate_archive_members(archive)
        if "docProps/core.xml" in names:
            core = ElementTree.fromstring(archive.read("docProps/core.xml"))
            title = core.findtext(_CORE_TITLE)
            if isinstance(title, str) and title.strip():
                return title.strip()
        try:
            document = ElementTree.fromstring(archive.read("word/document.xml"))
        except KeyError as exc:
            raise ValueError("missing document XML") from exc
    paragraphs = _paragraph_text(document)
    if not paragraphs:
        raise ValueError("missing document title")
    return paragraphs[0].strip()


def _extract_docx_text(path: Path) -> str:
    """แปลงข้อความครบทุก Word content part ที่รองรับ โดยไม่แตก ZIP ลงดิสก์"""
    with zipfile.ZipFile(path) as archive:
        names = _validate_archive_members(archive)
        if "word/document.xml" not in names:
            raise ValueError("missing document XML")

        parsed_parts: dict[str, ElementTree.Element] = {}
        for name in names:
            if not name.startswith("word/") or not name.endswith(".xml"):
                continue
            root = ElementTree.fromstring(archive.read(name))
            contains_text = any(True for _ in root.iter(f"{_WORD_NS}t"))
            if contains_text and not _is_supported_text_part(name):
                raise ValueError(f"unsupported textual DOCX part: {name}")
            if _is_supported_text_part(name):
                parsed_parts[name] = root

    ordered_names = ["word/document.xml"]
    ordered_names.extend(sorted(name for name in parsed_parts if name.startswith("word/header")))
    ordered_names.extend(sorted(name for name in parsed_parts if name.startswith("word/footer")))
    ordered_names.extend(
        name
        for name in ("word/footnotes.xml", "word/endnotes.xml", "word/comments.xml")
        if name in parsed_parts
    )
    paragraphs: list[str] = []
    for name in ordered_names:
        paragraphs.extend(_paragraph_text(parsed_parts[name]))
    return "\n".join(paragraphs)
