from __future__ import annotations

import json
import re
from urllib.parse import quote

import httpx
from pydantic import ValidationError
from .contracts import DraftAnswer, Evidence, Statement
from .prompt import SYSTEM


class ExtractiveProvider:
    """คืนข้อความจริงเพื่อทดสอบ retrieval เท่านั้น ไม่แกล้งเป็นคำตอบจาก LLM"""
    name = "extractive"

    async def answer(self, question: str, history: list[dict], evidence: tuple[Evidence, ...]):
        from .plugins.knowledge import terms
        query = set(terms(question))
        statements = []
        for doc in evidence:
            paragraphs = [p.strip() for p in doc.text.split("\n\n") if 10 <= len(p.strip()) <= 900
                          and not p.lstrip().startswith("#")]
            paragraphs.sort(key=lambda p: -len(query.intersection(terms(p))))
            if paragraphs:
                text = paragraphs[0]
                statements.append(Statement(text=text, source_id=doc.source_id, quote=text))
        return DraftAnswer(status="answered" if statements else "not_found", statements=tuple(statements))

    async def close(self):
        pass


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, *, transport=None):
        self.api_key, self.model = api_key, model
        self.client = httpx.AsyncClient(timeout=45, transport=transport)

    async def answer(self, question: str, history: list[dict], evidence: tuple[Evidence, ...]):
        if not self.api_key or not self.model:
            raise RuntimeError("ไม่ได้ตั้งค่า provider")
        data = {"current_question": question, "history": history,
                "sources": [doc.model_dump() for doc in evidence]}
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": json.dumps(data, ensure_ascii=False)}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 4096,
                "responseMimeType": "application/json", "responseJsonSchema": DraftAnswer.model_json_schema()},
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(self.model, safe='-._')}:generateContent"
        async with self.client.stream("POST", url, headers={"x-goog-api-key": self.api_key}, json=payload) as response:
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > 1_000_000:
                    raise ValueError("ผล provider ใหญ่เกินกำหนด")
        result = json.loads(body)
        candidate = result["candidates"][0]
        if candidate.get("finishReason") != "STOP":
            raise ValueError("provider ตอบไม่สมบูรณ์")
        text = "".join(p.get("text", "") for p in candidate["content"]["parts"] if not p.get("thought"))
        return DraftAnswer.model_validate_json(text)

    async def close(self):
        await self.client.aclose()


URL = re.compile(r"https?://[^\s<>\"'\]\)]+")


def validate_evidence(draft: DraftAnswer, evidence: tuple[Evidence, ...]):
    documents = {d.source_id: d for d in evidence}
    if draft.status == "not_found":
        if draft.statements:
            raise ValueError("not_found ต้องไม่มีข้อความอ้างอิง")
        return
    if not draft.statements:
        raise ValueError("คำตอบต้องมีหลักฐาน")
    for statement in draft.statements:
        doc = documents.get(statement.source_id)
        if doc is None or statement.quote not in doc.text:
            raise ValueError("ไม่พบข้อความอ้างอิงในเอกสารที่เลือก")
        allowed = set(URL.findall(doc.text))
        if not set(URL.findall(statement.text)).issubset(allowed):
            raise ValueError("URL ไม่ตรงกับเอกสาร")
