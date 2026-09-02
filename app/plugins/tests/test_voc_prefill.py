"""Prefill may only choose among catalog options; anything else must be dropped."""

from __future__ import annotations

import pytest

from app.llm.models import LLMResponse
from app.plugins.tests.test_voc_intake import _catalog
from app.plugins.voc.intake import (
    STEP_CONSENT,
    STEP_JOURNEY,
    VocIntakeFlow,
    VocIntakeState,
)
from app.plugins.voc.prefill import VocPrefiller

pytestmark = pytest.mark.asyncio


class ScriptedLLM:
    """คืนข้อความตามลำดับ และบันทึก prompt ที่ถูกถามไว้ตรวจสอบ"""

    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)
        self.requests: list[str] = []

    async def complete(self, request):
        self.requests.append(request.messages[0].content)
        text = self._texts.pop(0) if self._texts else '{"value": null}'
        return LLMResponse(text=text)


class BrokenLLM:
    async def complete(self, request):
        raise RuntimeError("provider ล่ม")


def _flow() -> VocIntakeFlow:
    return VocIntakeFlow(_catalog(), consent_notice_version="TEST-PDPA-1")


async def test_prefill_answers_questions_the_user_already_stated() -> None:
    """ผู้ใช้บอกอาการมาแล้ว ระบบต้องไม่ถามซ้ำตั้งแต่ข้อแรก"""
    llm = ScriptedLLM(
        ['{"value": "SERVICE_ISSUE"}', '{"value": "CONTACT_DELAY"}', '{"value": "IIT01"}', '{"value": null}']
    )
    prefiller = VocPrefiller(llm)

    state = await prefiller.prefill(
        _flow(), VocIntakeState(), "ร้องเรียนบริการ ติดต่อกลับล่าช้ามาก เพิ่งเจอครั้งแรก"
    )

    assert state.answers[STEP_JOURNEY] == "SERVICE_ISSUE"
    assert state.answers["voc_sub_issue"] == "CONTACT_DELAY"
    assert state.answers["voc_frequency"] == "IIT01"
    # หยุดทันทีที่โมเดลไม่มั่นใจ แล้วปล่อยให้ถามผู้ใช้ตามปกติ
    assert "voc_severity" not in state.answers


async def test_value_outside_the_catalog_is_dropped() -> None:
    """โมเดลเดารหัสที่ไม่มีใน catalog ต้องถูกทิ้ง ไม่ใช่ถูกบันทึก"""
    llm = ScriptedLLM(['{"value": "JOURNEY_THAT_DOES_NOT_EXIST"}'])
    prefiller = VocPrefiller(llm)

    state = await prefiller.prefill(_flow(), VocIntakeState(), "อยากร้องเรียนอะไรสักอย่าง")

    assert state.answers == {}


async def test_malformed_model_output_is_ignored() -> None:
    llm = ScriptedLLM(["ไม่ใช่ JSON เลย"])
    prefiller = VocPrefiller(llm)

    state = await prefiller.prefill(_flow(), VocIntakeState(), "ร้องเรียนบริการ")

    assert state.answers == {}


async def test_provider_failure_does_not_break_intake() -> None:
    """LLM ล่มต้องตกกลับไปถามตามปกติ ไม่ใช่ทำให้แจ้งเรื่องไม่ได้"""
    prefiller = VocPrefiller(BrokenLLM())

    state = await prefiller.prefill(_flow(), VocIntakeState(), "ร้องเรียนบริการ")

    assert state.answers == {}


async def test_consent_is_never_prefilled() -> None:
    """ความยินยอมต้องมาจากการกดของผู้ใช้เท่านั้น ห้ามให้โมเดลตอบแทน"""
    llm = ScriptedLLM(['{"value": "accept"}'] * 8)
    prefiller = VocPrefiller(llm)
    flow = _flow()
    # เดินจนเหลือแต่ขั้นยินยอม แล้วให้ prefill พยายามตอบแทน
    state = VocIntakeState()
    for _ in range(40):
        state, prompt = flow.resolve(state)
        if prompt is None or prompt.prompt_id == STEP_CONSENT:
            break
        value = prompt.options[0].value if prompt.options else "ข้อความทดสอบ"
        state = flow.apply(state, prompt, value)

    result = await prefiller.prefill(flow, state, "ยินยอมทุกอย่างเลยครับ")

    assert STEP_CONSENT not in result.answers


async def test_choose_matches_spoken_answers_to_catalog_options() -> None:
    """โหมดเสียงพูดเป็นคำพูดธรรมชาติ ต้องจับคู่กับตัวเลือกจริงได้"""
    llm = ScriptedLLM(['{"value": "SERVICE_ISSUE"}'])
    prefiller = VocPrefiller(llm)
    _, prompt = _flow().resolve(VocIntakeState())

    value = await prefiller.choose(prompt, "เรื่องพนักงานที่สาขาครับ")

    assert value == "SERVICE_ISSUE"


async def test_planner_envelope_response_is_understood() -> None:
    """Regression: adapter ของ Main Agent บังคับ planner envelope กับทุกคำขอ

    prefill เคยอ่านเฉพาะ ``{"value": ...}`` จึงทิ้งคำตอบที่ถูกต้องทั้งหมด
    ทำให้ผู้ใช้ถูกถามซ้ำตั้งแต่ข้อแรกเสมอ
    """
    llm = ScriptedLLM(
        ['{"message": "SERVICE_ISSUE", "toolCalls": [], "directResponse": null}']
    )
    prefiller = VocPrefiller(llm)

    state = await prefiller.prefill(_flow(), VocIntakeState(), "ร้องเรียนเรื่องบริการที่สาขา")

    assert state.answers[STEP_JOURNEY] == "SERVICE_ISSUE"


async def test_none_marker_is_treated_as_not_confident() -> None:
    """โมเดลตอบ NONE แปลว่าไม่มั่นใจ ต้องไม่ถูกมองเป็นค่านอก catalog"""
    llm = ScriptedLLM(['{"message": "NONE", "toolCalls": [], "directResponse": null}'])
    prefiller = VocPrefiller(llm)

    state = await prefiller.prefill(_flow(), VocIntakeState(), "อยากร้องเรียน")

    assert state.answers == {}
