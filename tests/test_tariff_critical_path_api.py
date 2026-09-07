from __future__ import annotations

import json
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.agent.main_agent import MainAgent
from app.agent.registry import ToolRegistry
from app.api.routes import router
from app.backends.full_document_knowledge import FullDocumentKnowledgeBackend, GroundedEvidence
from app.core.di import agent_service
from app.core.startup import create_platform_app
from app.llm import DemoLLMAdapter, LLMClient, LLMResponse
from app.tools.knowledge_tool import KnowledgeTool


class _OfflineTariffBackend(FullDocumentKnowledgeBackend):
    async def search(self, query: str, max_results: int) -> GroundedEvidence:
        del query, max_results
        return GroundedEvidence("", 0, ())


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    backend = _OfflineTariffBackend(api_key="offline")
    agent = MainAgent(LLMClient(DemoLLMAdapter()), ToolRegistry([KnowledgeTool(backend)]))
    app = create_platform_app()
    app.include_router(router)
    agent_service.set_agent(agent)
    with TestClient(app) as test_client:
        yield test_client


def _chat(client: TestClient, message: str, conversation_id: str | None = None) -> dict:
    body = {"message": message}
    if conversation_id is not None:
        body["conversationId"] = conversation_id
    response = client.post("/api/v1/chat", json=body)
    assert response.status_code == 200
    return response.json()


def test_tariff_multiturn_reaches_verified_september_total(client: TestClient) -> None:
    first = _chat(client, "ใช้ไฟ 966 หน่วย ต้องจ่ายเท่าไร")
    assert "1.1.2" in first["message"]
    assert first["toolResults"][0]["data"]["billOutcome"]["status"] == "clarification"

    second = _chat(client, "กันยายน2569", first["conversationId"])
    assert second["toolResults"][0]["data"]["billOutcome"]["status"] == "clarification"

    third = _chat(client, "1.1.2", second["conversationId"])
    outcome = third["toolResults"][0]["data"]["billOutcome"]
    assert outcome["usage"] == "966"
    assert outcome["billingMonth"] == 9
    assert outcome["billingYear"] == 2569
    assert outcome["finalTotal"] == "4365.471172"
    assert "4,365.47" in third["message"]
    assert third["citations"]


def test_tariff_one_shot_and_correction_override_period(client: TestClient) -> None:
    one_shot = _chat(client, "ใช้ไฟ 966 หน่วย เดือนกันยายน 2569 ประเภท 1.1.2 ต้องจ่ายเท่าไร")
    assert one_shot["toolResults"][0]["data"]["billOutcome"]["displayTotal"] == "4365.47"

    half_cent = _chat(client, "ใช้ไฟ 4200 หน่วย เดือนกันยายน 2569 ประเภท 1.1.2 ต้องจ่ายเท่าไร")
    half_cent_outcome = half_cent["toolResults"][0]["data"]["billOutcome"]
    assert half_cent_outcome["vat"] == "1308.965000"
    assert half_cent_outcome["subtotalBeforeVat"] == "18699.5000"
    assert half_cent_outcome["finalTotal"] == "20008.465000"
    assert "VAT 1,308.97 บาท" in half_cent["message"]
    assert "ก่อน VAT 18,699.50 บาท" in half_cent["message"]
    assert "รวมทั้งสิ้น 20,008.47 บาท" in half_cent["message"]

    first = _chat(client, "ใช้ไฟ 966 หน่วย ต้องจ่ายเท่าไร")
    corrected = _chat(client, "ตุลาคม 2569 1.1.2", first["conversationId"])
    outcome = corrected["toolResults"][0]["data"]["billOutcome"]
    assert outcome["status"] == "partial"
    assert outcome["billingMonth"] == 10
    assert "4,079.88" in corrected["message"]
    assert "finalTotal" not in outcome


def test_tariff_confirmation_and_topic_switch_do_not_guess(client: TestClient) -> None:
    first = _chat(client, "ใช้ไฟ 966 หน่วย ต้องจ่ายเท่าไร")
    confirmed = _chat(client, "กันยายน2569", first["conversationId"])
    confirmed = _chat(client, "ยืนยันตามที่แจ้ง", confirmed["conversationId"])
    assert confirmed["toolResults"][0]["data"]["billOutcome"]["finalTotal"] == "4365.471172"

    switched = _chat(client, "ไฟดับที่บ้าน", first["conversationId"])
    assert all("billCalculation" not in (result.get("data") or {}) for result in switched["toolResults"])
    assert "4365" not in switched["message"]


def test_tariff_tou_and_invalid_usage_are_fail_closed(client: TestClient) -> None:
    tou = _chat(client, "ใช้ไฟ 966 หน่วย กันยายน2569 ประเภท TOU ต้องจ่ายเท่าไร")
    assert tou["toolResults"][0]["data"]["billOutcome"]["status"] == "unavailable"
    assert "ยังไม่สามารถคำนวณ" in tou["message"]

    invalid = _chat(client, "ใช้ไฟ -1 หน่วย กันยายน2569 ประเภท 1.1.2 ต้องจ่ายเท่าไร")
    assert invalid["toolResults"][0]["status"] == "error"
    assert "4365" not in invalid["message"]


class _ForgedPlanner:
    async def complete(self, request):
        del request
        return LLMResponse(
            text=json.dumps(
                {"message": "ค่าไฟ 4,365.47 บาท", "toolCalls": [], "directResponse": None},
                ensure_ascii=False,
            )
        )


def test_forged_planner_amount_is_not_user_facing() -> None:
    app = create_platform_app()
    app.include_router(router)
    agent_service.set_agent(
        MainAgent(
            LLMClient(_ForgedPlanner()),
            ToolRegistry([KnowledgeTool(_OfflineTariffBackend(api_key="offline"))]),
        )
    )
    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"message": "ใช้ไฟ 966 หน่วย ต้องจ่ายเท่าไร"})
    assert response.status_code == 200
    assert "4,365.47" not in response.json()["message"]
    assert "4365" not in response.json()["message"]
