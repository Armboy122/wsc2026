"""Legacy Chat Knowledge backend with no generative model calls.

The Knowledge router/answer model calls were removed in Story 2 Ticket 002: Gemini Live now
selects approved documents itself through ``app.knowledge`` and the ADK
``get_knowledge_documents`` tool. The remaining legacy Chat path keeps only the deterministic,
hash-verified tariff evidence used by bill calculation; free-text Chat Knowledge search fails
closed with a structured ``unavailable`` error. Story 3 deletes this module with the Chat
runtime.
"""

from __future__ import annotations

import asyncio
import hashlib
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree

from app.contracts import Citation, ToolErrorCode

DEFAULT_SOURCE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "source"
DEFAULT_HARD_CONTEXT_CHARS = 1_000_000
BILL_SOURCE_ID = "PEA_residential_normal_1_1_2_SEP_DEC_2569.md"
BILL_SOURCE_SHA256 = "24f32caffa1167cad5060af6a8c535d3fba2738ef9e3c7b6feebbcd8f1477b1e"
SUPPORTED_DOCUMENT_SUFFIXES = frozenset({".docx", ".md"})
USER_SAFE_CHAT_KNOWLEDGE_REMOVED = (
    "การค้นความรู้ผ่านแชตถูกปิดแล้ว กรุณาใช้โหมดเสียงเพื่อสอบถามข้อมูลจากเอกสาร PEA"
)


class KnowledgeBackendError(Exception):
    """ข้อผิดพลาดแบบมีชนิดและปลอดภัยสำหรับแสดงแก่ผู้ใช้"""

    def __init__(self, code: ToolErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class GroundedEvidence:
    """หลักฐานจากข้อความฉบับเต็มพร้อม citation ที่ตรวจสอบแล้ว"""

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
    """Deterministic legacy Chat backend: verified tariff evidence only, no model client."""

    def __init__(
        self,
        *,
        source_root: Path | str = DEFAULT_SOURCE_ROOT,
        hard_context_chars: int = DEFAULT_HARD_CONTEXT_CHARS,
    ) -> None:
        self._source_root = Path(source_root)
        self._hard_context_chars = hard_context_chars
        self._text_cache: dict[tuple[str, int, int], str] = {}

    def is_configured(self) -> bool:
        return self._source_root.is_dir() and self._hard_context_chars > 0

    async def is_ready(self) -> bool:
        if not self.is_configured():
            return False
        try:
            return bool(await asyncio.to_thread(self._catalog))
        except Exception:
            return False

    async def search(self, query: str, max_results: int) -> GroundedEvidence:
        """Free-text Chat Knowledge search no longer exists; fail closed and visibly."""
        raise KnowledgeBackendError(ToolErrorCode.UNAVAILABLE, USER_SAFE_CHAT_KNOWLEDGE_REMOVED)

    async def bill_evidence(self, max_results: int) -> GroundedEvidence:
        """Load and verify the fixed tariff evidence without invoking a provider."""
        try:
            return await asyncio.to_thread(self._bill_evidence_sync, max_results)
        except (OSError, UnicodeError, ValueError, zipfile.BadZipFile, ElementTree.ParseError):
            return GroundedEvidence("", 0, ())

    def _bill_evidence_sync(self, max_results: int) -> GroundedEvidence:
        if max_results < 1:
            return GroundedEvidence("", 0, ())
        catalog = self._catalog()
        document = catalog.get(BILL_SOURCE_ID)
        if document is None or len((document.source_id,)) > max_results:
            return GroundedEvidence("", 0, ())
        text = self._full_text(document)
        if len(text) > self._hard_context_chars:
            return GroundedEvidence("", 0, ())
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != BILL_SOURCE_SHA256:
            return GroundedEvidence("", 0, ())

        supporting_snippets = (
            ("ประเภทที่ 1 บ้านอยู่อาศัย สำหรับการใช้ไฟฟ้ากับบ้านที่อยู่อาศัย", 3),
            ("1.1.2 ใช้พลังงานไฟฟ้าเกิน 150 หน่วยต่อเดือน 24.62", 3),
            ("200 หน่วยแรก (หน่วยที่ 0 – 200) 3.0000\n200 หน่วยต่อไป (หน่วยที่ 201 – 400) 4.1584\nเกิน 400 หน่วยขึ้นไป (หน่วยที่ 401 เป็นต้นไป) 4.3583", 3),
            ("ค่า Ft\nหน่วยละ\n0.1623 บาท\nหรือ 16.23 สตางค์ (ยังไม่รวมภาษีมูลค่าเพิ่ม)", 1),
            ("มาตรา ๔ ให้ลดอัตราภาษีมูลค่าเพิ่มตามมาตรา ๘๐ แห่งประมวลรัษฎากร และคงจัดเก็บในอัตราร้อยละหกจุดสาม สำหรับการขายสินค้า การให้บริการ หรือการนําเข้าทุกกรณี ซึ่งความรับผิดในการเสียภาษีมูลค่าเพิ่มเกิดขึ้นตั้งแต่วันที่ ๑ ตุลาคม พ.ศ. ๒๕๖๘ ถึงวันที่ ๓๐ กันยายน พ.ศ. ๒๕๖๙", 2),
            ("ลดอัตราภาษีมูลค่าเพิ่มเป็นการชั่วคราวจากร้อยละ 10 เหลือร้อยละ 6.3 เมื่อรวมกับภาษีท้องถิ่นอีกร้อยละ 0.7 จะเท่ากับร้อยละ 7", 1),
        )
        citations: list[Citation] = []
        for snippet, page in supporting_snippets:
            if snippet not in text:
                return GroundedEvidence("", 0, ())
            citations.append(Citation(
                source_id=document.source_id,
                title=document.title,
                uri="knowledge://source/" + quote(document.source_id, safe="/"),
                snippet=snippet,
                page=page,
            ))
        return GroundedEvidence(
            "\n".join(snippet for snippet, _ in supporting_snippets),
            1,
            tuple(citations),
        )

    def _catalog(self) -> dict[str, _Document]:
        root = self._source_root.resolve(strict=True)
        if not root.is_dir():
            return {}
        catalog: dict[str, _Document] = {}
        for candidate in root.rglob("*"):
            if (
                candidate.suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES
                or candidate.is_symlink()
                or not candidate.is_file()
            ):
                continue
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(root):
                continue
            source_id = candidate.relative_to(root).as_posix()
            if source_id.startswith(".") or candidate.name.lower() == "readme.md" or source_id in catalog:
                continue
            try:
                title = _extract_document_title(candidate)
            except (OSError, UnicodeError, ValueError, zipfile.BadZipFile, ElementTree.ParseError):
                continue
            catalog[source_id] = _Document(source_id, candidate, candidate.name, title)
        return catalog

    def _full_text(self, document: _Document) -> str:
        status = document.path.stat()
        cache_key = (document.source_id, status.st_mtime_ns, status.st_size)
        if cache_key in self._text_cache:
            return self._text_cache[cache_key]
        text = _extract_document_text(document.path)
        if not text.strip():
            raise ValueError("empty document")
        self._text_cache = {
            key: value for key, value in self._text_cache.items() if key[0] != document.source_id
        }
        self._text_cache[cache_key] = text
        return text


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


def _extract_document_title(path: Path) -> str:
    """Read a title from an approved Markdown or DOCX document."""
    if path.suffix.lower() == ".md":
        return _extract_markdown_title(path)
    if path.suffix.lower() == ".docx":
        return _extract_docx_title(path)
    raise ValueError("unsupported document type")


def _extract_document_text(path: Path) -> str:
    """Read complete text from an approved Markdown or DOCX document."""
    if path.suffix.lower() == ".md":
        return path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".docx":
        return _extract_docx_text(path)
    raise ValueError("unsupported document type")


def _extract_markdown_title(path: Path) -> str:
    """Use the first non-empty Markdown line as the document title."""
    for line in path.read_text(encoding="utf-8").splitlines():
        title = line.strip()
        if title:
            return title.lstrip("#").strip()
    raise ValueError("missing document title")


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
