from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..contracts import Evidence, SearchInput, SearchResult


def terms(text: str) -> Counter:
    """English words + Thai character trigrams; ไม่ต้องดาวน์โหลดโมเดล/embedding"""
    text = unicodedata.normalize("NFC", text.lower())
    words = re.findall(r"[a-z0-9]{2,}|[\u0e00-\u0e7f]+", text)
    result: Counter = Counter()
    for word in words:
        if re.fullmatch(r"[a-z0-9]+", word):
            result[word] += 1
        else:
            result.update(word[i:i+3] for i in range(max(1, len(word)-2)))
    return result


@dataclass(frozen=True)
class Document:
    evidence: Evidence
    counts: Counter
    length: int
    title_terms: frozenset[str]


class KnowledgePlugin:
    id = "knowledge.search"
    scope = "knowledge:read"
    description = "ค้นเอกสาร Markdown ฉบับเต็มที่อยู่ใน publication สำหรับตอบพร้อมหลักฐาน"
    input_model = SearchInput
    output_model = SearchResult

    def __init__(self, root: Path, *, max_docs: int = 3, max_chars: int = 28000):
        self.root, self.max_docs, self.max_chars = root.resolve(), max_docs, max_chars

    def snapshot(self) -> tuple[str, list[Document]]:
        raw = (self.root / "publication.json").read_bytes()
        manifest = json.loads(raw)
        documents, seen = [], set()
        today = date.today().isoformat()
        for entry in manifest["documents"]:
            if entry["status"] != "published":
                continue
            if entry.get("effective_from") and entry["effective_from"] > today:
                continue
            if entry.get("effective_until") and entry["effective_until"] < today:
                continue
            relative = Path(entry["path"])
            candidate = self.root / relative
            if candidate.is_symlink() or relative.is_absolute() or ".." in relative.parts:
                raise ValueError("พาธเอกสารไม่ปลอดภัย")
            path = candidate.resolve()
            if not path.is_relative_to(self.root) or path.suffix != ".md":
                raise ValueError("เอกสารต้องเป็น Markdown ภายในโฟลเดอร์ knowledge")
            content = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(content.encode()).hexdigest()
            if digest != entry["sha256"] or entry["id"] in seen:
                raise ValueError("เอกสารเปลี่ยนหรือ source id ซ้ำ ต้องเผยแพร่ publication ใหม่")
            seen.add(entry["id"])
            title = entry["title"]
            counts = terms(content)
            documents.append(Document(Evidence(source_id=entry["id"], title=title,
                version=digest, text=content), counts, sum(counts.values()), frozenset(terms(title))))
        return hashlib.sha256(raw).hexdigest(), documents

    def search(self, value: SearchInput) -> SearchResult:
        publication, documents = self.snapshot()
        query = terms(value.query)
        n = len(documents)
        if not query or not n:
            return SearchResult(evidence=(), publication=publication)
        df = Counter(t for d in documents for t in d.counts)
        average = sum(d.length for d in documents) / n
        ranked = []
        followup = bool(re.match(r"^(แล้ว|ถ้าอย่างนั้น|อันนี้|แบบนี้|กรณีนี้|เรื่องเดิม|ขอรายละเอียดเพิ่ม|สรุปอีก)", value.query.strip()))
        for document in documents:
            score = 0.0
            for token in query:
                freq = document.counts[token]
                if not freq:
                    continue
                idf = math.log(1 + (n-df[token]+0.5)/(df[token]+0.5))
                score += idf * freq*2.2/(freq+1.2*(0.25+0.75*document.length/average))
                if token in document.title_terms:
                    score += idf * 2
            if score > 0:
                ranked.append((score, document))
        ranked.sort(key=lambda pair: (-pair[0], pair[1].evidence.source_id))
        # คำชี้กลับสั้นๆ จัดเอกสารก่อนหน้าไว้ก่อน; topic switch ที่ไม่มีคำชี้กลับค้นใหม่
        prior = [d for d in documents if d.evidence.source_id in value.previous_sources] if followup else []
        ordered = prior + [d for _, d in ranked if d not in prior]
        chosen, total, omitted = [], 0, 0
        for document in ordered:
            if len(chosen) >= self.max_docs:
                break
            size = len(document.evidence.text)
            if total + size > self.max_chars:
                omitted += 1
                continue  # ไม่ตัดครึ่งเอกสารแล้วอ้างว่าอ่านครบ
            chosen.append(document.evidence)
            total += size
        return SearchResult(evidence=tuple(chosen), publication=publication, omitted=omitted)

    async def execute(self, value: SearchInput) -> SearchResult:
        return await asyncio.to_thread(self.search, value)
