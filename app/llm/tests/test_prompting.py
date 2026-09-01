"""สัญญาของ tool catalogue ที่ส่งให้โมเดล LLM ทุก provider

Regression: schema ที่ไม่มี ``required`` เคยทำให้โมเดลบางครั้งลืมส่ง ``idempotencyKey``
มาด้วย (ผ่าน pydantic validation ไม่ได้เพราะ field required แต่โมเดลไม่รู้ว่าต้องส่ง)
ทำให้ผู้ใช้ที่แจ้งเหตุแบบไม่ทราบหมายเลขผู้ใช้ไฟถูกถามซ้ำวนหลายรอบจนหมดขีดจำกัดขั้นตอน
"""
from __future__ import annotations

import json
from uuid import uuid4

from app.contracts import (
    OmsGetOutageByCaInput,
    OmsPrepareAnonymousOutageInput,
    OmsPrepareOutageWithCaInput,
    ToolName,
    VocGetCaseInput,
    VocPrepareCaseInput,
)
from app.llm.models import LLMRequest, LLMMessage, ToolDefinition
from app.llm.prompting import tool_catalogue


def _catalogue_for(*tool_defs: ToolDefinition) -> dict:
    request = LLMRequest(
        messages=(LLMMessage("user", "test"),),
        tools=tool_defs,
        correlation_id=uuid4(),
    )
    text = tool_catalogue(request)
    return json.loads(text.split(":\n", 1)[1])


def _action_schema(catalogue: dict, tool_name: str, action_name: str) -> dict:
    tool = next(item for item in catalogue if item["name"] == tool_name)
    return next(item for item in tool["actions"] if item["name"] == action_name)


def test_prepare_anonymous_outage_schema_requires_every_mandatory_field() -> None:
    """Regression: ขาด required เคยทำให้ Gemini ลืมส่ง idempotencyKey เป็นครั้งคราว"""
    catalogue = _catalogue_for(
        ToolDefinition(ToolName.OMS, "OMS", ("get_outage_by_ca", "prepare_outage_with_ca", "prepare_anonymous_outage"))
    )
    schema = _action_schema(catalogue, "oms_tool", "prepare_anonymous_outage")
    assert set(schema["inputSchema"]["required"]) == {"description", "location", "contactPhone", "idempotencyKey"}
    # ต้องตรงกับ pydantic model จริงที่ registry validate ก่อนเรียก backend
    assert set(schema["inputSchema"]["required"]) == set(OmsPrepareAnonymousOutageInput.model_json_schema()["required"])


def test_get_outage_by_ca_schema_requires_ca_number() -> None:
    catalogue = _catalogue_for(
        ToolDefinition(ToolName.OMS, "OMS", ("get_outage_by_ca",))
    )
    schema = _action_schema(catalogue, "oms_tool", "get_outage_by_ca")
    assert schema["inputSchema"]["required"] == list(OmsGetOutageByCaInput.model_json_schema()["required"])


def test_prepare_outage_with_ca_schema_matches_contract_required_fields() -> None:
    catalogue = _catalogue_for(
        ToolDefinition(ToolName.OMS, "OMS", ("prepare_outage_with_ca",))
    )
    schema = _action_schema(catalogue, "oms_tool", "prepare_outage_with_ca")
    assert set(schema["inputSchema"]["required"]) == set(OmsPrepareOutageWithCaInput.model_json_schema()["required"])


def test_voc_prepare_case_schema_requires_all_contact_fields() -> None:
    catalogue = _catalogue_for(
        ToolDefinition(ToolName.VOC, "VOC", ("prepare_case",))
    )
    schema = _action_schema(catalogue, "voc_tool", "prepare_case")
    assert set(schema["inputSchema"]["required"]) == set(VocPrepareCaseInput.model_json_schema()["required"])


def test_get_case_schema_requires_both_tracking_fields() -> None:
    catalogue = _catalogue_for(
        ToolDefinition(ToolName.VOC, "VOC", ("get_case",))
    )
    schema = _action_schema(catalogue, "voc_tool", "get_case")
    assert set(schema["inputSchema"]["required"]) == set(VocGetCaseInput.model_json_schema()["required"])
