from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.contracts import ToolAction, ToolName, ToolResult, ToolResultStatus
from app.llm.demo import DemoLLMAdapter
from app.llm.demo_behavior import DemoPlan, DemoToolCall
from app.llm.models import LLMMessage, LLMRequest
from app.plugins.runtime import BoundDemoBehavior
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


@pytest.mark.asyncio
async def test_voc_behavior_leaves_ambiguous_complaint_policy_to_knowledge() -> None:
    response = await DemoLLMAdapter((VocDemoBehavior(),)).complete(
        _request("What is the complaint policy?")
    )

    assert all(call.name is not ToolName.VOC for call in response.tool_calls)
    assert any(call.name is ToolName.KNOWLEDGE for call in response.tool_calls)


@pytest.mark.asyncio
async def test_voc_demo_does_not_start_an_intake_it_cannot_complete() -> None:
    response = await DemoLLMAdapter((VocDemoBehavior(),)).complete(
        _request("ต้องการร้องเรียน")
    )

    assert response.tool_calls == ()
    assert response.direct_response == "voc_demo_prepare_unavailable"


def test_oms_behavior_ignores_foreign_result_with_similar_shape() -> None:
    behavior = OmsDemoBehavior()
    plan = behavior.after_tools_demo(
        (LLMMessage("user", "description: ไฟดับ"),),
        ({
            "name": ToolName.VOC.value,
            "action": ToolAction.VOC_GET_CASE.value,
            "status": "success",
            "data": {
                "activeEvent": None,
                "recommendedAction": "CREATE_METER_EVENT",
                "caNumber": "100000000003",
            },
        },),
        uuid4(),
    )

    assert plan is None


@pytest.mark.asyncio
async def test_plugin_demo_cannot_call_another_plugin() -> None:
    class CrossPluginBehavior:
        tool_name = ToolName.OMS

        def has_demo_intent(self, message: str) -> bool:
            return True

        def plan_demo(self, message: str, correlation_id: UUID) -> DemoPlan:
            return DemoPlan(calls=(DemoToolCall(0, ToolName.VOC, ToolAction.VOC_LIST_CATEGORIES, {}),))

        def after_tools_demo(
            self,
            messages: tuple[LLMMessage, ...],
            results: tuple[dict[str, Any], ...],
            correlation_id: UUID,
        ) -> None:
            return None

    behavior = BoundDemoBehavior(
        behavior=CrossPluginBehavior(),
        tool_name=ToolName.OMS,
        allowed_actions=frozenset({ToolAction.OMS_GET_OUTAGE_BY_CA}),
    )

    with pytest.raises(ValueError, match="นอก manifest"):
        await DemoLLMAdapter((behavior,)).complete(_request("test"))


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


def test_voc_submit_presentation_labels_simulation_and_tracking_credentials() -> None:
    result = ToolResult(
        callId=uuid4(),
        name=ToolName.VOC,
        action=ToolAction.VOC_SUBMIT_CASE,
        status=ToolResultStatus.SUCCESS,
        data={"vocId": "SIM-CASE-1001", "trackingKey": "track-1001"},
        simulation=True,
    )

    message = VocResponsePolicy().result_fact(result)

    assert message is not None
    assert "ผลจำลอง" in message
    assert "SIM-CASE-1001" in message
    assert "track-1001" in message
