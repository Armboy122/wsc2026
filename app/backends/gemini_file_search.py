"""แบ็กเอนด์ Gemini File Search RAG แบบโฮสต์ (Worker B — ความรู้)

นี่คือแบ็กเอนด์ความรู้เพียงตัวเดียวในเดโม การค้นคืนและการยึดโยงหลักฐานมอบหมายให้
บริการ File Search แบบโฮสต์ของ Google โมดูลนี้มีหน้าที่เพียงแปลงข้อมูลกำกับของหลักฐาน
ที่ส่งกลับมาเป็นค่า ``Citation`` ตามสัญญาและ ``answerContext`` แบบกระชับ โดยตั้งใจ
ไม่มีการฝังข้อมูล การแบ่งส่วน การทำดัชนี การจัดอันดับ ที่เก็บเวกเตอร์ภายในเครื่อง หรือการใช้
ความจำโมเดลเป็นทางเลือกสำรอง (CONTRACTS.md: สิ่งที่ไม่ทำอย่างชัดเจน; ARCHITECTURE.md:
“ไม่ทำการฝังข้อมูล แบ่งส่วน ทำดัชนี จัดอันดับ หรือจัดเก็บเอกสารด้วยตนเอง”)

SDK ของผู้ให้บริการ (``google-genai``) เป็นส่วนพึ่งพาเสริมและจะนำเข้าเมื่อใช้งานครั้งแรก
จึงสามารถนำเข้าและสร้างโมดูลนี้ได้โดยไม่ต้องติดตั้ง SDK หากขาด SDK หรือการตั้งค่า
ระบบจะแสดง :class:`KnowledgeBackendError` แบบมีชนิดและปลอดภัยสำหรับผู้ใช้ โดยไม่ล้มเหลว
ขณะนำเข้าและไม่เปิดเผยข้อมูลรับรองหรือปลายทาง
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable

from app.contracts import Citation, ToolErrorCode

logger = logging.getLogger("pea_one_agent.gemini_file_search")

ENV_API_KEY = "GEMINI_API_KEY"
ENV_FALLBACK_API_KEY = "GOOGLE_API_KEY"
ENV_STORE = "GEMINI_FILE_SEARCH_STORE"
ENV_MODEL = "GEMINI_FILE_SEARCH_MODEL"

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_TIMEOUT_SECONDS = 30.0
# ตัวตรวจสอบความพร้อมมีขีดจำกัดเวลาสั้นของตนเอง การตรวจสุขภาพเมื่อเริ่มต้น
# ต้องไม่รอนานเท่าการค้นคืนแบบเต็ม
DEFAULT_READINESS_TIMEOUT_SECONDS = 5.0

# จุดเชื่อมต่อของตัวสร้างไคลเอนต์ที่ส่งเข้ามาได้ (สำหรับการทดสอบแบบกำหนดผลลัพธ์ได้): รับคีย์ API
# ที่ตั้งค่าไว้และส่งคืนไคลเอนต์ของผู้ให้บริการ ส่วนระบบใช้งานจริงจะสร้าง
# ``google.genai.Client`` จริงแทน
ClientFactory = Callable[[str], Any]

# ขีดจำกัดตามสัญญา (app/contracts.py: Citation, KnowledgeSearchOutput)
MAX_ANSWER_CONTEXT_CHARS = 4000
MAX_SNIPPET_CHARS = 1000
MAX_TITLE_CHARS = 500
MAX_URI_CHARS = 2000

# ข้อความที่ปลอดภัยต่อผู้ใช้และไม่มีข้อมูลรับรอง
USER_SAFE_NOT_CONFIGURED = (
    "เซิร์ฟเวอร์นี้ยังไม่ได้ตั้งค่าบริการความรู้ "
    "กรุณาติดต่อผู้ดูแลระบบเพื่อตรวจสอบการตั้งค่าบริการ"
)
USER_SAFE_UNAVAILABLE = (
    "บริการความรู้ไม่พร้อมใช้งานชั่วคราว กรุณาลองใหม่อีกสักครู่"
)


class KnowledgeBackendError(Exception):
    """ข้อผิดพลาดของแบ็กเอนด์แบบมีชนิด ซึ่ง ``message`` ปลอดภัยสำหรับแสดงแก่ผู้ใช้

    ``code`` เป็น :class:`~app.contracts.ToolErrorCode` ที่ตรึงค่าไว้ ส่วน ``message``
    ต้องไม่มีข้อมูลรับรอง URL ของปลายทาง หรือรายละเอียดคำขอโดยเด็ดขาด
    """

    def __init__(self, code: ToolErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class GroundedEvidence:
    """ผลลัพธ์รูปแบบตรึงค่าจากการค้นคืนแบบโฮสต์หนึ่งครั้ง

    ``answer_context`` จะว่างและ ``result_count`` จะเป็นศูนย์เมื่อ
    ผู้ให้บริการไม่ส่งข้อมูลอ้างอิงหลักฐานที่ใช้งานได้กลับมา (ไม่มีหลักฐาน)
    """

    answer_context: str
    result_count: int
    citations: tuple[Citation, ...]


def _clip(text: str, limit: int) -> str:
    return text[:limit]


def _first_text(value: Any, *names: str) -> str:
    """แอตทริบิวต์สตริงแรกใน ``names`` ที่ไม่ว่าง (รองรับรูปแบบข้อมูลผู้ให้บริการที่ต่างกัน)"""
    for name in names:
        candidate = getattr(value, name, None)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def _first_int(value: Any, name: str) -> int | None:
    candidate = getattr(value, name, None)
    if isinstance(candidate, int) and candidate > 0:
        return candidate
    return None


def _grounding_contexts(response: Any) -> list[Any]:
    """รวบรวมบริบทอ้างอิงหลักฐานของ File Search จากการตอบกลับของผู้ให้บริการ

    ทำงานตามโครงสร้าง (เข้าถึงผ่านแอตทริบิวต์) เพื่อให้การทดสอบสามารถใช้
    วัตถุจำลองขนาดเล็กแทนวัตถุการตอบกลับของ SDK ได้
    """
    contexts: list[Any] = []
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        metadata = getattr(candidate, "grounding_metadata", None)
        if metadata is None:
            continue
        for chunk in getattr(metadata, "grounding_chunks", None) or []:
            context = getattr(chunk, "retrieved_context", None)
            if context is not None:
                contexts.append(context)
    return contexts


def _build_context(citations: list[Citation]) -> str:
    """รวมการอ้างอิงไว้ใน ``answerContext`` ที่ตัวแทนหลักใช้สร้างคำตอบ"""
    parts = [
        f"[{index}] {citation.title}\n{citation.snippet}\nแหล่งที่มา: {citation.uri}"
        for index, citation in enumerate(citations, start=1)
    ]
    return _clip("\n\n".join(parts), MAX_ANSWER_CONTEXT_CHARS)


def normalize_grounding(response: Any, *, max_results: int) -> GroundedEvidence:
    """แปลงการตอบกลับของผู้ให้บริการเป็นหลักฐานที่ตรึงค่าไว้ (ไม่มีชนิดข้อมูลของผู้ให้บริการ)

    กฎ (CONTRACTS.md, ``knowledge_tool.search``):
    - หากไม่มีข้อมูลอ้างอิงหลักฐานที่ใช้งานได้ -> ``answerContext`` ว่าง, ``resultCount`` เป็น 0 และไม่มีการอ้างอิง
    - จำกัดจำนวนการอ้างอิงไว้ที่ ``max_results`` และตัดรายการซ้ำตามแหล่งที่มา + หน้า
    - ส่วนข้อมูลที่ไม่มี URI ของแหล่งที่มาหรือข้อความคัดย่อถือเป็นหลักฐานที่ใช้ไม่ได้และจะถูกข้าม
    """
    citations: list[Citation] = []
    seen: set[tuple[str, int | None]] = set()
    for context in _grounding_contexts(response):
        uri = _first_text(context, "uri")
        if not uri:
            continue
        snippet = _first_text(context, "text")
        if not snippet:
            continue
        page = _first_int(context, "page_number")
        source_id = _first_text(context, "document_name") or (
            f"{uri}#page-{page}" if page is not None else uri
        )
        key = (source_id, page)
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            Citation(
                source_id=_clip(source_id, MAX_URI_CHARS),
                title=_clip(_first_text(context, "title") or uri, MAX_TITLE_CHARS),
                uri=_clip(uri, MAX_URI_CHARS),
                snippet=_clip(snippet, MAX_SNIPPET_CHARS),
                page=page,
            )
        )
        if len(citations) >= max(1, max_results):
            break
    if not citations:
        return GroundedEvidence("", 0, ())
    return GroundedEvidence(_build_context(citations), len(citations), tuple(citations))


class GeminiFileSearchKnowledgeBackend:
    """จุดเชื่อมต่อขอบเขตแคบสำหรับ Gemini File Search RAG แบบโฮสต์

    การดำเนินการสาธารณะ:

    - ``search(query, max_results) -> GroundedEvidence`` — การค้นคืนแบบโฮสต์
    - ``is_ready() -> bool`` — การตรวจสอบความพร้อมของผู้ให้บริการจริงแบบจำกัดเวลา
    - ``is_configured() -> bool`` — ตรวจสอบการตั้งค่าภายในเครื่องอย่างรวดเร็วเท่านั้น

    ไคลเอนต์ SDK จะถูกสร้างเมื่อจำเป็นในการเรียกแต่ละครั้ง เพื่อให้อ่านการตั้งค่า
    (ตัวแปรสภาพแวดล้อม) ใหม่เสมอ และกักข้อผิดพลาดของผู้ให้บริการไว้ภายในขอบเขต
    ข้อผิดพลาดแบบมีชนิด สามารถส่ง ``client_factory`` เข้ามาเพื่อแทนที่การสร้างไคลเอนต์
    สำหรับการทดสอบแบบกำหนดผลลัพธ์ได้ ส่วนระบบใช้งานจริงจะใช้ไคลเอนต์จริงของผู้ให้บริการเสมอ
    ระบบใช้การแบ่งส่วนตามค่าเริ่มต้นของผู้ให้บริการ โดยจะไม่ส่งการตั้งค่าการแบ่งส่วนใด ๆ
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        store_name: str | None = None,
        model: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        readiness_timeout_seconds: float = DEFAULT_READINESS_TIMEOUT_SECONDS,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._api_key = (
            api_key
            if api_key is not None
            else os.environ.get(ENV_API_KEY) or os.environ.get(ENV_FALLBACK_API_KEY)
        )
        self._store_name = (
            store_name if store_name is not None else os.environ.get(ENV_STORE)
        )
        self._model = model if model is not None else os.environ.get(ENV_MODEL) or DEFAULT_MODEL
        self._timeout_seconds = timeout_seconds
        self._readiness_timeout_seconds = readiness_timeout_seconds
        self._client_factory = client_factory

    @property
    def store_name(self) -> str | None:
        """ที่เก็บ File Search ที่ตั้งค่าไว้ (ชื่อทรัพยากรแบบเต็ม) หากมี"""
        return self._store_name

    @property
    def model(self) -> str:
        """โมเดลสร้างคำตอบโดยอ้างอิงหลักฐานที่ใช้สำหรับการค้นคืนแบบโฮสต์"""
        return self._model

    def is_configured(self) -> bool:
        """เป็นจริงเมื่อมีคีย์ API และที่เก็บพร้อมใช้งาน (ตรวจสอบภายในเครื่องอย่างรวดเร็ว)"""
        return bool(self._api_key and self._store_name)

    async def is_ready(self) -> bool:
        """ตรวจสอบความพร้อมกับผู้ให้บริการจริงภายในเวลาที่กำหนด

        เมธอดนี้ต่างจาก :meth:`is_configured` (การตรวจสอบภายในเครื่องอย่างรวดเร็ว)
        เพราะจะตรวจสอบที่เก็บ File Search ที่ตั้งค่าไว้ผ่านไคลเอนต์จริงของผู้ให้บริการ
        ดังนั้นข้อมูลรับรองที่ถูกเพิกถอน ที่เก็บหรือ SDK ที่ขาดหาย หรือบริการของผู้ให้บริการ
        ขัดข้อง ล้วนทำให้รายงาน ``False`` การตรวจสอบนี้อ่านข้อมูลอย่างเดียว จำกัดเวลาด้วย
        ``readiness_timeout_seconds`` และไม่แสดงข้อมูลรับรอง ปลายทาง หรือรายละเอียด
        ข้อยกเว้นจากผู้ให้บริการ โดยจะส่งคืนเพียง ``False`` เท่านั้น
        """
        if not self._api_key or not self._store_name:
            return False
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._verify_store_sync),
                timeout=self._readiness_timeout_seconds,
            )
        except Exception:  # ขอบเขตข้อผิดพลาดของผู้ให้บริการ: ห้ามเปิดเผยรายละเอียด
            logger.debug("การตรวจความพร้อมของความรู้ล้มเหลว (ปกปิดรายละเอียดแล้ว)")
            return False
        return True

    def _make_client(self) -> Any:
        """สร้างไคลเอนต์ของผู้ให้บริการผ่านจุดเชื่อมต่อที่ส่งเข้ามาได้

        หากไม่ได้ส่ง ``client_factory`` เข้ามา ระบบจะนำเข้า SDK ``google-genai``
        ซึ่งเป็นส่วนเสริมเมื่อจำเป็น แล้วสร้างไคลเอนต์จริง ดังนั้นหากขาด SDK
        จะแสดงเป็น ``ImportError`` (ผู้เรียกจะจัดประเภทว่า "ยังไม่ได้ตั้งค่า")
        """
        if self._client_factory is not None:
            return self._client_factory(self._api_key)
        from google import genai  # นำเข้าเมื่อจำเป็น: ส่วนพึ่งพาเสริมของผู้ให้บริการ
        return genai.Client(api_key=self._api_key)

    def _verify_store_sync(self) -> None:
        """ตรวจสอบกับบริการจริงแบบอ่านอย่างเดียวว่าที่เก็บที่ตั้งค่าไว้มีอยู่

        ``file_search_stores.get`` คือการค้นหาที่เก็บของผู้ให้บริการ ซึ่งจะสำเร็จ
        เมื่อข้อมูลรับรองถูกต้อง และที่เก็บ File Search ที่ตั้งค่าไว้มีอยู่และเข้าถึงได้เท่านั้น
        """
        client = self._make_client()
        client.file_search_stores.get(name=self._store_name)

    async def search(self, query: str, max_results: int) -> GroundedEvidence:
        """ดำเนินการค้นคืนแบบโฮสต์และปรับข้อมูลอ้างอิงหลักฐานเป็นผลลัพธ์ที่ตรึงค่าไว้

        ข้อยกเว้น:
            KnowledgeBackendError: ข้อผิดพลาดแบบมีชนิดที่ปลอดภัยสำหรับผู้ใช้ (``unavailable``)
                สำหรับปัญหาใด ๆ จากผู้ให้บริการ เช่น ขาด SDK หรือการตั้งค่า ข้อผิดพลาด
                ของเครือข่ายหรือ API หรือหมดเวลา
        """
        try:
            evidence = await asyncio.wait_for(
                asyncio.to_thread(self._search_sync, query, max_results),
                timeout=self._timeout_seconds,
            )
        except KnowledgeBackendError:
            raise
        except asyncio.TimeoutError as exc:
            logger.warning("Gemini File Search หมดเวลาหลัง %s วินาที", self._timeout_seconds)
            raise KnowledgeBackendError(ToolErrorCode.UNAVAILABLE, USER_SAFE_UNAVAILABLE) from exc
        except Exception as exc:  # ขอบเขตข้อผิดพลาดของผู้ให้บริการ: ห้ามเปิดเผยรายละเอียด
            logger.debug("Gemini File Search ล้มเหลว: %s", exc)
            raise KnowledgeBackendError(ToolErrorCode.UNAVAILABLE, USER_SAFE_UNAVAILABLE) from exc
        return evidence

    def _search_sync(self, query: str, max_results: int) -> GroundedEvidence:
        if not self._api_key or not self._store_name:
            raise KnowledgeBackendError(ToolErrorCode.UNAVAILABLE, USER_SAFE_NOT_CONFIGURED)
        try:
            from google import genai  # นำเข้าเมื่อจำเป็น: ส่วนพึ่งพาเสริมของผู้ให้บริการ
        except ImportError as exc:
            raise KnowledgeBackendError(ToolErrorCode.UNAVAILABLE, USER_SAFE_NOT_CONFIGURED) from exc
        try:
            client = self._make_client()
            response = client.models.generate_content(
                model=self._model,
                contents=query,
                config=genai.types.GenerateContentConfig(
                    tools=[
                        genai.types.Tool(
                            file_search=genai.types.FileSearch(
                                file_search_store_names=[self._store_name],
                                top_k=max_results,
                            )
                        )
                    ]
                ),
            )
        except Exception as exc:  # ขอบเขตข้อผิดพลาดของผู้ให้บริการ: ห้ามเปิดเผยรายละเอียด
            logger.debug("การเรียก Gemini File Search ล้มเหลว: %s", exc)
            raise KnowledgeBackendError(ToolErrorCode.UNAVAILABLE, USER_SAFE_UNAVAILABLE) from exc
        return normalize_grounding(response, max_results=max_results)
