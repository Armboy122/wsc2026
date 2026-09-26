"""Offline answer-quality evaluation: retrieve context, answer, judge, record.

Two modes, both holding out the ``คำถามใกล้เคียง`` paraphrases:

- ``hybrid_qafirst`` — context is the ticket-003 ``search_knowledge`` payload rendered from the
  production :func:`app.agent.adk_agent.search_result_payload`. Q&A bodies are stripped of the
  held-out paraphrase list before rendering, so the answer model cannot read the question back.
- ``longctx_qafirst`` — every approved document, Q&A first, then document chunks, like the
  research harness long-context arm (only ``knowledge/source/**`` per decision D7).

Answering and judging are separate :class:`~evaluation.rag.models.AnswerModel` and
:class:`~evaluation.rag.models.JudgeModel` calls. The answer model receives an approved-Q&A-first
system prompt; the judge model receives the question, the approved gold answer and the produced
answer, and returns a JSON verdict. Judge output is parsed leniently; anything unparseable is
recorded as ``JUDGE_ERR`` rather than crashing the run.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from app.knowledge.catalog import KnowledgeCatalog
from app.knowledge.index import KnowledgeIndex, SearchResult
from evaluation.rag.dataset import (
    DEFAULT_SOURCE_ROOT,
    EvalQuestion,
    holdout_qa_text,
    longctx_corpus,
)
from evaluation.rag.models import AnswerModel, JudgeModel
from evaluation.rag.retrieval_eval import build_index, estimate_tokens_from_chars

HYBRID_QAFIRST = "hybrid_qafirst"
LONGCTX_QAFIRST = "longctx_qafirst"
MODES = (HYBRID_QAFIRST, LONGCTX_QAFIRST)

VALID_VERDICTS = ("CORRECT", "PARTIAL", "WRONG", "NO_ANSWER")
JUDGE_ERR = "JUDGE_ERR"

# Same answering rule as the runtime prompt: approved Q&A wins, never invent, refer to 1129.
ANSWER_SYSTEM_PROMPT = (
    "คุณคือเจ้าหน้าที่บริการลูกค้า การไฟฟ้าส่วนภูมิภาค (กฟภ./PEA) ตอบลูกค้าเป็นภาษาไทยแบบกระชับ"
    "เหมาะกับการพูด (ไม่เกิน 5 ประโยค) ใช้เฉพาะข้อมูลในเอกสารที่ให้มาเท่านั้น ห้ามเดา "
    "ถ้าเอกสารไม่มีข้อมูลที่ตอบคำถามได้ ให้ตอบว่าไม่พบข้อมูลในเอกสาร และแนะนำติดต่อ 1129 "
    "ถ้าคำถามกำกวม ให้บอกสิ่งที่ต้องถามลูกค้าเพิ่ม "
    "กติกาเพิ่มเติม: ข้อความที่ติดป้าย [APPROVED_QA] คือคำตอบที่ได้รับอนุมัติแล้ว ให้ยึดเป็นหลักเสมอ "
    "ถ้าเอกสารอื่นขัดแย้งให้เชื่อ APPROVED_QA ห้ามเพิ่มเงื่อนไข ตัวเลข ช่องทาง หรือขอบเขตที่ "
    "APPROVED_QA ไม่ได้ระบุ ถ้า APPROVED_QA บอกให้ถามลูกค้าเพิ่มหรือส่งต่อ 1129 ให้ทำตามนั้น"
)

JUDGE_SYSTEM_PROMPT = (
    "คุณเป็นผู้ตรวจคำตอบบริการลูกค้า กฟภ. อย่างเข้มงวด ตอบเป็น JSON เท่านั้น"
)


@dataclass(frozen=True)
class JudgeVerdict:
    verdict: str
    reason: str


@dataclass(frozen=True)
class AnswerRecord:
    """One question's answer and judge verdict."""

    question_id: str
    source_id: str
    kind: str
    mode: str
    model: str
    judge: str
    question: str
    retrieved_ids: tuple[str, ...]
    context_chars: int
    context_tokens: int
    answer: str
    verdict: str
    judge_reason: str
    answer_latency_s: float
    answer_cached: bool
    judge_latency_s: float
    judge_cached: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_answer_user_prompt(question: str, context: str, *, source_label: str) -> str:
    return f"{source_label}:\n{context}\n\nคำถามลูกค้า: {question}"


def build_judge_user_prompt(question: str, gold_answer: str, answer: str) -> str:
    return (
        f"คำถาม: {question}\n\n"
        f"คำตอบอ้างอิง (ถูกต้อง, ได้รับอนุมัติ):\n{gold_answer}\n\n"
        f"คำตอบของระบบ:\n{answer}\n\n"
        "ให้ตัดสิน: CORRECT = มีสาระสำคัญของคำตอบอ้างอิงครบถ้วนพอสำหรับลูกค้าและไม่มีข้อมูลขัดแย้ง "
        "(ถ้าคำตอบอ้างอิงเป็นแบบให้ถามเพิ่ม/ส่งต่อ 1129 คำตอบที่ทำแบบเดียวกันอย่างสมเหตุสมผลถือว่าถูก); "
        "PARTIAL = ถูกบางส่วน ขาดสาระสำคัญ แต่ไม่มีข้อมูลผิด; WRONG = มีข้อมูลขัดแย้งกับคำตอบอ้างอิง"
        "หรือตอบผิดเรื่อง; NO_ANSWER = บอกว่าไม่พบข้อมูล/ปฏิเสธ\n"
        'ตอบ JSON: {"verdict":"CORRECT|PARTIAL|WRONG|NO_ANSWER","reason":"เหตุผลสั้นๆ ภาษาไทย"}'
    )


def build_hybrid_context(result: SearchResult) -> str:
    """Render the production ``search_knowledge`` payload with paraphrases held out.

    The production payload builder is imported lazily so the retrieval half of the harness
    does not need the ADK/voice extras at import time.
    """
    from app.agent.adk_agent import search_result_payload

    payload = search_result_payload(result)
    parts: list[str] = []
    for qa in payload["approvedQa"]:
        content = holdout_qa_text(str(qa["content"]))
        parts.append(
            f'<approved_qa sourceId="{qa["sourceId"]}" uri="{qa["uri"]}">\n'
            f"[APPROVED_QA]\n{content}\n</approved_qa>"
        )
    for chunk in payload["chunks"]:
        parts.append(
            f'<chunk sourceId="{chunk["sourceId"]}" heading="{chunk["heading"]}">\n'
            f'{chunk["content"]}\n</chunk>'
        )
    return "\n\n".join(parts)


def build_longctx_context(corpus: tuple[tuple[str, str], ...]) -> str:
    parts: list[str] = []
    for source_id, text in corpus:
        if source_id.startswith("qa/"):
            parts.append(
                f'<document name="{source_id}">\n[APPROVED_QA]\n{text}\n</document>'
            )
        else:
            parts.append(f'<document name="{source_id}">\n{text}\n</document>')
    return "\n\n".join(parts)


def parse_verdict(text: str) -> JudgeVerdict:
    """Parse a judge reply into one of the four verdicts, or ``JUDGE_ERR``."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is not None:
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            verdict = str(data.get("verdict", "")).strip().upper()
            if verdict in VALID_VERDICTS:
                return JudgeVerdict(verdict=verdict, reason=str(data.get("reason", ""))[:500])
    return JudgeVerdict(verdict=JUDGE_ERR, reason=text[:200])


def run_answer_eval(
    questions: tuple[EvalQuestion, ...],
    *,
    mode: str,
    answer_model: AnswerModel,
    judge_model: JudgeModel,
    index: KnowledgeIndex | None = None,
    embedder: str = "fake",
    source_root: Path | str | None = None,
    limit: int | None = None,
) -> tuple[AnswerRecord, ...]:
    """Answer and judge every question in ``questions`` (optionally limited)."""
    if mode not in MODES:
        raise ValueError(f"unsupported mode {mode!r}: expected one of {', '.join(MODES)}")
    selected = questions[:limit] if limit is not None else questions
    corpus: tuple[tuple[str, str], ...] = ()
    if mode == LONGCTX_QAFIRST:
        root = Path(source_root) if source_root is not None else DEFAULT_SOURCE_ROOT
        corpus = longctx_corpus(KnowledgeCatalog(root))
    elif index is None:
        index = build_index(
            embedder, source_root=source_root, include_qa_paraphrases=False
        )

    records: list[AnswerRecord] = []
    for question in selected:
        if mode == HYBRID_QAFIRST:
            assert index is not None  # built above for this mode
            result = index.search(question.question)
            context = build_hybrid_context(result)
            retrieved_ids = tuple(hit.source_id for hit in result.qa) + tuple(
                hit.source_id for hit in result.chunks
            )
            source_label = "ข้อความที่ค้นเจอ"
        else:
            context = build_longctx_context(corpus)
            retrieved_ids = tuple(source_id for source_id, _ in corpus)
            source_label = "เอกสารทั้งหมด"

        answer_response = answer_model.answer(
            system=ANSWER_SYSTEM_PROMPT,
            user=build_answer_user_prompt(
                question.question, context, source_label=source_label
            ),
        )
        judge_response = judge_model.judge(
            system=JUDGE_SYSTEM_PROMPT,
            user=build_judge_user_prompt(
                question.question, question.gold_answer, answer_response.text
            ),
        )
        verdict = parse_verdict(judge_response.text)
        records.append(
            AnswerRecord(
                question_id=question.id,
                source_id=question.source_id,
                kind=question.kind,
                mode=mode,
                model=answer_model.spec,
                judge=judge_model.spec,
                question=question.question,
                retrieved_ids=retrieved_ids,
                context_chars=len(context),
                context_tokens=estimate_tokens_from_chars(len(context)),
                answer=answer_response.text,
                verdict=verdict.verdict,
                judge_reason=verdict.reason,
                answer_latency_s=answer_response.latency_s,
                answer_cached=answer_response.cached,
                judge_latency_s=judge_response.latency_s,
                judge_cached=judge_response.cached,
            )
        )
    return tuple(records)
