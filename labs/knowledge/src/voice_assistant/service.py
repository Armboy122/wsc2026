from __future__ import annotations

import asyncio
import time

from .contracts import Answer, Citation, DomainError, Principal
from .prompt import VERSION
from .providers import validate_evidence


class KnowledgeService:
    def __init__(self, registry, sessions, provider, plugin_id: str):
        self.registry, self.sessions, self.provider, self.plugin_id = registry, sessions, provider, plugin_id

    async def ask(self, principal: Principal, question: str, session_id: str | None = None) -> Answer:
        started = time.perf_counter()
        question = question.strip()
        if not question or len(question) > 2000:
            raise DomainError("invalid_question", "คำถามต้องมี 1–2,000 ตัวอักษร")
        sid, revision, context = await self.sessions.load(principal.id, session_id)
        try:
            result = await self.registry.invoke(self.plugin_id,
                {"query": question, "previous_sources": context["sources"]}, principal)
        except DomainError:
            raise
        except Exception as e:
            raise DomainError("publication_invalid", "เอกสารเปลี่ยนหรือ publication ไม่พร้อม กรุณาตรวจสอบก่อนถามใหม่", 503) from e
        status, message, citations = "not_found", "ยังไม่พบหลักฐานเพียงพอในเอกสารที่เลือก กรุณาระบุหัวข้อหรือรายละเอียดเพิ่มเติมครับ", ()
        if result.evidence:
            try:
                draft = await asyncio.wait_for(self.provider.answer(question, context["history"], result.evidence), timeout=50)
            except Exception:
                status, message = "unavailable", "บริการตอบคำถามไม่พร้อมใช้งาน กรุณาตรวจการตั้งค่าโมเดลแล้วลองใหม่ครับ"
            else:
                try:
                    validate_evidence(draft, result.evidence)
                except (ValueError, AttributeError):
                    status, message = "invalid_evidence", "คำตอบรอบนี้มีหลักฐานที่ตรวจสอบไม่ผ่าน จึงยังไม่แสดงคำตอบครับ"
                else:
                    if draft.status == "answered":
                        status = "evidence_only" if self.provider.name == "extractive" else "answered"
                        docs = {d.source_id: d for d in result.evidence}
                        message = "\n\n".join(f"{s.text} [{i}]" for i, s in enumerate(draft.statements, 1))
                        citations = tuple(Citation(source_id=s.source_id, title=docs[s.source_id].title,
                            version=docs[s.source_id].version, quote=s.quote) for s in draft.statements)
        answer = Answer(session_id=sid, status=status, message=message, citations=citations,
            sources=tuple(d.source_id for d in result.evidence), publication=result.publication,
            provider=self.provider.name, prompt_version=VERSION,
            elapsed_ms=round((time.perf_counter()-started)*1000))
        # เก็บเฉพาะคำตอบที่ผ่าน validation; failures ไม่กลายเป็นความจริงรอบถัดไป
        if status in {"answered", "evidence_only"}:
            context["history"] = (context["history"] + [
                {"role": "user", "text": question}, {"role": "assistant", "text": message[:4000]}
            ])[-6:]
            context["sources"] = list(answer.sources)
            await self.sessions.save(principal.id, sid, revision, context)
        return answer
