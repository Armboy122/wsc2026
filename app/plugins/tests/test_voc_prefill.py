"""VOC extraction is bounded, evidence-backed, and fail closed."""

from __future__ import annotations

# pyright: reportMissingImports=false

import json

import pytest

from app.llm.models import LLMResponse
from app.plugins.tests.test_voc_intake import _catalog
from app.plugins.voc.intake import (
    STEP_CA_NUMBER,
    STEP_DETAIL,
    STEP_ISSUE,
    STEP_JOURNEY,
    STEP_REQUEST_TYPE,
    STEP_SUBJECT,
    STEP_TOPIC,
    VocIntakeFlow,
    VocIntakeState,
)
from app.plugins.voc.prefill import VocPrefiller

pytestmark = pytest.mark.asyncio


class ScriptedLLM:
    def __init__(self, payloads: list[object]) -> None:
        self._payloads = list(payloads)
        self.requests: list[str] = []

    async def complete(self, request):
        self.requests.append(request.messages[0].content)
        payload = self._payloads.pop(0) if self._payloads else {"fields": {}}
        return LLMResponse(text=payload if isinstance(payload, str) else json.dumps(payload))


class BrokenLLM:
    async def complete(self, request):
        raise RuntimeError("provider failure")


def _flow() -> VocIntakeFlow:
    return VocIntakeFlow(_catalog(), consent_notice_version="TEST-PDPA-1")


def _envelope(fields: dict) -> str:
    return json.dumps({
        "message": json.dumps({"fields": fields}, ensure_ascii=False),
        "toolCalls": [],
        "directResponse": None,
    }, ensure_ascii=False)


async def test_one_structured_extraction_retains_multiple_evidence_backed_facts() -> None:
    detail = "ไปติดต่อสำนักงานแล้วพนักงานพูดไม่สุภาพ"
    message = f"แจ้งปัญหาด้านบริการ {detail}"
    llm = ScriptedLLM([_envelope({
        "journey": {"value": "SERVICE_ISSUE", "evidence": "แจ้งปัญหาด้านบริการ"},
        "detail": {"value": detail, "evidence": detail},
        "issue": {"value": "SERVICE_DELAY", "evidence": "พนักงานพูดไม่สุภาพ"},
        "caNumber": {"value": "100000000003", "evidence": "100000000003"},
        "consent": {"value": "accept", "evidence": "ร้องเรียนบริการ"},
    })])

    state = await VocPrefiller(llm).prefill(_flow(), VocIntakeState(), message)

    assert state.answers[STEP_JOURNEY] == "SERVICE_ISSUE"
    assert state.answers[STEP_DETAIL] == detail
    assert state.answers[STEP_SUBJECT] == detail[:140]
    assert "voc_issue" not in state.answers  # parent request/topic were not supplied
    assert STEP_CA_NUMBER not in state.answers  # model cannot provide CA without a label in user text
    assert len(llm.requests) == 1


async def test_catalog_evidence_must_be_a_full_unique_label() -> None:
    catalog = _catalog()
    catalog["requestTypes"][0]["topics"][0]["issues"].append({
        "code": "STAFF_CONDUCT",
        "name": "บริการไม่ดี",
        "subIssues": [],
    })
    flow = VocIntakeFlow(catalog, consent_notice_version="TEST-PDPA-1")
    state = VocIntakeState({
        STEP_JOURNEY: "SERVICE_ISSUE",
        STEP_REQUEST_TYPE: "REQUEST_1",
        STEP_TOPIC: "SERVICE",
    })
    llm = ScriptedLLM([_envelope({
        "issue": {"value": "SERVICE_DELAY", "evidence": "บริการ"},
    })])

    result = await VocPrefiller(llm).prefill(flow, state, "ร้องเรียนบริการไม่ดี")

    assert STEP_ISSUE not in result.answers


async def test_catalog_evidence_accepts_an_exact_unique_label() -> None:
    flow = _flow()
    state = VocIntakeState({
        STEP_JOURNEY: "SERVICE_ISSUE",
        STEP_REQUEST_TYPE: "REQUEST_1",
        STEP_TOPIC: "SERVICE",
    })
    llm = ScriptedLLM([_envelope({
        "issue": {"value": "SERVICE_DELAY", "evidence": "บริการล่าช้า"},
    })])

    result = await VocPrefiller(llm).prefill(flow, state, "ร้องเรียนบริการล่าช้า")

    assert result.answers[STEP_ISSUE] == "SERVICE_DELAY"


async def test_free_text_value_must_itself_be_a_user_span() -> None:
    message = "ร้องเรียนบริการ สมชาย"
    llm = ScriptedLLM([_envelope({
        "detail": {"value": "พนักงานคืนเงินให้แล้ว", "evidence": "ร้องเรียนบริการ"},
        "reporterPhone": {"value": "0812345678", "evidence": "สมชาย"},
    })])

    state = await VocPrefiller(llm).prefill(_flow(), VocIntakeState(), message)

    assert STEP_DETAIL not in state.answers
    assert "voc_reporter_phone" not in state.answers


async def test_model_correction_flag_cannot_overwrite_known_value() -> None:
    existing = VocIntakeState({STEP_DETAIL: "รายละเอียดเดิม"})
    llm = ScriptedLLM([_envelope({
        "detail": {
            "value": "รายละเอียดใหม่",
            "evidence": "รายละเอียดใหม่",
            "explicitCorrection": True,
        },
    })])

    state = await VocPrefiller(llm).prefill(_flow(), existing, "รายละเอียดใหม่")

    assert state.answers[STEP_DETAIL] == "รายละเอียดเดิม"


async def test_deterministic_user_correction_can_replace_known_value() -> None:
    existing = VocIntakeState({STEP_DETAIL: "รายละเอียดเดิม"})
    llm = ScriptedLLM([_envelope({
        "detail": {
            "value": "รายละเอียดใหม่",
            "evidence": "รายละเอียดใหม่",
            "explicitCorrection": False,
        },
    })])

    state = await VocPrefiller(llm).prefill(_flow(), existing, "ขอแก้รายละเอียดเป็น รายละเอียดใหม่")

    assert state.answers[STEP_DETAIL] == "รายละเอียดใหม่"


async def test_malformed_and_legacy_outputs_preserve_state_without_retry() -> None:
    existing = VocIntakeState({STEP_DETAIL: "known"})
    for response in ("not JSON", '{"value":"SERVICE_ISSUE"}'):
        llm = ScriptedLLM([response])
        state = await VocPrefiller(llm).prefill(_flow(), existing, "ร้องเรียนบริการ")
        assert state == existing
        assert len(llm.requests) == 1


async def test_provider_failure_preserves_state() -> None:
    existing = VocIntakeState({STEP_DETAIL: "known"})
    state = await VocPrefiller(BrokenLLM()).prefill(_flow(), existing, "ข้อความใหม่")
    assert state == existing


async def test_area_codes_are_ignored_and_labelled_ca_is_deterministic() -> None:
    message = "แจ้งปัญหาด้านบริการ CA 100000000003 กรุงเทพมหานคร"
    llm = ScriptedLLM([_envelope({
        "journey": {"value": "SERVICE_ISSUE", "evidence": "แจ้งปัญหาด้านบริการ"},
        "location": {"value": "กรุงเทพมหานคร", "evidence": "กรุงเทพมหานคร"},
        "province": {"value": "10", "evidence": "กรุงเทพมหานคร"},
        "district": {"value": "1001", "evidence": "กรุงเทพมหานคร"},
        "office": {"value": "PEA-BKK-01", "evidence": "กรุงเทพมหานคร"},
        "caNumber": {"value": "999999999999", "evidence": "CA"},
    })])

    state = await VocPrefiller(llm).prefill(_flow(), VocIntakeState(), message)

    assert state.answers[STEP_CA_NUMBER] == "100000000003"
    assert state.answers["voc_location_text"] == "กรุงเทพมหานคร"
    assert "voc_province" not in state.answers
    assert "voc_district" not in state.answers
    assert "voc_office" not in state.answers
