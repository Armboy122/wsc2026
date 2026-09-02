from __future__ import annotations

from uuid import uuid4

import pytest

from app.contracts import ToolAction, ToolName, ToolResult, ToolResultStatus
from app.llm.demo import DemoLLMAdapter
from app.llm.models import LLMMessage, LLMRequest
from app.plugins.oms.demo import OmsDemoBehavior
from app.plugins.voc.demo import VocDemoBehavior
from app.plugins.voc.response import VocResponsePolicy


def _request(message: str) -> LLMRequest:
    return LLMRequest(
        messages=(LLMMessage("user", message),),
        tools=(),
        correlation_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_demo_adapter_has_no_implicit_oms_behavior() -> None:
    response = await DemoLLMAdapter().complete(_request("check outage status 100000000003"))

    assert all(call.name is not ToolName.OMS for call in response.tool_calls)
    assert response.direct_response not in {
        "oms_ca_number", "oms_outage_start", "oms_with_ca_inputs", "oms_anonymous_inputs",
    }


@pytest.mark.asyncio
async def test_enabled_oms_behavior_contributes_the_same_typed_call() -> None:
    response = await DemoLLMAdapter((OmsDemoBehavior(),)).complete(
        _request("check outage status 100000000003")
    )

    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name is ToolName.OMS
    assert response.tool_calls[0].action is ToolAction.OMS_GET_OUTAGE_BY_CA
    assert response.tool_calls[0].input == {"caNumber": "100000000003"}


@pytest.mark.asyncio
async def test_enabled_voc_behavior_owns_category_selection() -> None:
    response = await DemoLLMAdapter((VocDemoBehavior(),)).complete(
        _request("ขอดูประเภทเรื่องร้องเรียน")
    )

    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name is ToolName.VOC
    assert response.tool_calls[0].action is ToolAction.VOC_LIST_CATEGORIES


def test_voc_policy_formats_categories_for_people_not_raw_json() -> None:
    policy = VocResponsePolicy()
    result = ToolResult(
        callId=uuid4(),
        name=ToolName.VOC,
        action=ToolAction.VOC_LIST_CATEGORIES,
        status=ToolResultStatus.SUCCESS,
        data={"categories": [{"code": "service", "label": "แจ้งปัญหาด้านบริการ"}]},
        simulation=True,
    )

    message = policy.result_fact(result)

    assert message is not None
    assert "แจ้งปัญหาด้านบริการ" in message
    assert "{\"categories\"" not in message
