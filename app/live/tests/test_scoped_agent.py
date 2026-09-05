"""ขอบเขตเครื่องมือของช่องทางเสียง: เห็นเฉพาะ Knowledge กับ OMS

ข้อกำหนดที่คุ้มไว้:

- ช่องทางเสียงเห็นเฉพาะเครื่องมือใน allowlist ทั้งใน registry และ catalogue
- Main Agent กลางที่เว็บและ LINE ใช้ต้องไม่ถูกลดเครื่องมือ
- pending action และ trace ใช้ store ร่วมกัน จึงยืนยันข้ามช่องทางได้
- เครื่องมือที่ถูกกรองออกต้องถูกปฏิเสธที่ registry แม้โมเดลจะสั่งเรียกก็ตาม
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agent.guided_flow import GuidedFlows
from app.agent.main_agent import MainAgent
from app.agent.registry import ToolContext, ToolRegistry
from app.contracts import (
    ChatRequest,
    ToolAction,
    ToolCall,
    ToolName,
    ToolResult,
    ToolResultStatus,
)
from app.live.scoped_agent import VOICE_TOOLS, scoped_voice_agent
from app.llm.models import ToolDefinition
from app.plugins.voc.flow import VocGuidedFlow
from app.tools.voc_tool import VocTool


_OMS_OUTAGE_DATA = {
    "caNumber": "123456789012",
    "customerFound": True,
    "network": {"meterId": "M-1", "transformerId": "T-1", "feederId": "F-1"},
    "activeEvent": None,
    "recommendedAction": "CREATE_METER_EVENT",
}


class _StubTool:
    def __init__(self, name: ToolName) -> None:
        self.name = name

    async def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.SUCCESS,
            # registry ตรวจผลลัพธ์กับ schema ของ action จริง จึงต้องคืนรูปที่ถูกสัญญา
            data=_OMS_OUTAGE_DATA if call.name == ToolName.OMS else {},
            simulation=True,
        )

    def reset(self) -> None:
        return None


class _StubLLM:
    async def complete(self, request):  # pragma: no cover - ไม่ถูกเรียกในเทสต์นี้
        raise AssertionError("ไม่ควรเรียก LLM ในเทสต์ขอบเขตเครื่องมือ")


class _StubFlow:
    """flow ที่ประกาศเจ้าของผ่านเครื่องมือที่ถือไว้ เหมือน VocGuidedFlow จริง"""

    def __init__(self, tool_name: ToolName | None) -> None:
        self._tool = _StubTool(tool_name) if tool_name is not None else None


class _CatalogProbeVocTool(VocTool):
    def __init__(self) -> None:
        super().__init__()
        self.catalog_reads = 0

    def get_catalog(self) -> dict[str, object]:
        self.catalog_reads += 1
        return {
            "journeys": [
                {
                    "code": f"JOURNEY_{index}",
                    "label": f"ประเภท {index}",
                    "classificationRootCodes": [],
                }
                for index in range(6)
            ]
        }


def _flow_name(flow: object) -> ToolName | None:
    return getattr(getattr(flow, "_tool", None), "name", None)


def _full_agent() -> MainAgent:
    registry = ToolRegistry(
        [
            _StubTool(ToolName.KNOWLEDGE),
            _StubTool(ToolName.OMS),
            # ใช้ implementation จริงของ code tool เพื่อให้การกรองช่องเสียง
            # ไม่ผ่านได้เพียงเพราะ test double มี shape พิเศษ
            VocTool(),
        ],
        catalogue=(
            ToolDefinition(
                name=ToolName.OMS,
                description="เครื่องมือไฟฟ้าขัดข้อง",
                actions=(ToolAction.OMS_GET_OUTAGE_BY_CA,),
            ),
            ToolDefinition(
                name=ToolName.VOC,
                description="เครื่องมือเรื่องร้องเรียน",
                actions=(ToolAction.VOC_LIST_CATEGORIES,),
            ),
        ),
    )
    return MainAgent(_StubLLM(), registry)


def _full_agent_with_flows() -> MainAgent:
    agent = _full_agent()
    agent._guided_flows = GuidedFlows((_StubFlow(ToolName.VOC), _StubFlow(ToolName.OMS)))
    return agent


def test_voice_allowlist_is_knowledge_and_oms_only() -> None:
    assert VOICE_TOOLS == frozenset({ToolName.KNOWLEDGE, ToolName.OMS})


def test_scoped_agent_drops_tools_outside_the_allowlist() -> None:
    voice = scoped_voice_agent(_full_agent())

    assert voice._tools.names == VOICE_TOOLS
    assert ToolName.VOC not in voice._tools.names


def test_scoped_catalogue_hides_the_filtered_tool_from_the_planner() -> None:
    """โมเดลต้องไม่เห็น VOC ในแค็ตตาล็อก จึงไม่มีทางวางแผนเรียก"""
    voice = scoped_voice_agent(_full_agent())

    names = {definition.name for definition in voice._tool_catalogue}

    assert ToolName.VOC not in names
    assert {ToolName.KNOWLEDGE, ToolName.OMS} <= names


def test_the_shared_agent_keeps_every_tool_for_web_and_line() -> None:
    """เว็บและ LINE ใช้ agent ตัวเดิม การกรองฝั่งเสียงต้องไม่กระทบ"""
    full = _full_agent()

    scoped_voice_agent(full)

    assert ToolName.VOC in full._tools.names


def test_scoped_agent_shares_state_so_confirmation_works_across_channels() -> None:
    """รายการที่เตรียมด้วยเสียงต้องกดยืนยันบนเว็บได้ และ trace อ่านได้ที่เดิม"""
    full = _full_agent()

    voice = scoped_voice_agent(full)

    assert voice._pending_actions is full._pending_actions
    assert voice._traces is full._traces
    assert voice._conversations is full._conversations


@pytest.mark.asyncio
async def test_filtered_tool_is_refused_by_the_scoped_registry() -> None:
    """ด่านสุดท้าย: แม้จะสั่งเรียกตรง ๆ registry ของเสียงก็ต้องปฏิเสธ"""
    voice = scoped_voice_agent(_full_agent())
    call = ToolCall(
        call_id=uuid4(),
        name=ToolName.VOC,
        action=ToolAction.VOC_LIST_CATEGORIES,
        input={},
    )

    result = await voice._tools.execute(
        call, ToolContext(conversation_id=uuid4(), trace_id=uuid4())
    )

    assert result.status is ToolResultStatus.ERROR


@pytest.mark.asyncio
async def test_allowed_tools_still_execute_on_the_voice_path() -> None:
    voice = scoped_voice_agent(_full_agent())
    call = ToolCall(
        call_id=uuid4(),
        name=ToolName.OMS,
        action=ToolAction.OMS_GET_OUTAGE_BY_CA,
        input={"caNumber": "123456789012"},
    )

    result = await voice._tools.execute(
        call, ToolContext(conversation_id=uuid4(), trace_id=uuid4())
    )

    assert result.status is ToolResultStatus.SUCCESS


def test_guided_flow_of_a_filtered_tool_is_dropped() -> None:
    """flow ทำงานก่อน planner และไม่ผ่าน catalogue จึงต้องถูกกรองด้วย

    เป็นการกันถอยหลังของบั๊กจริง: ตัด VOC ออกจาก registry แล้ว แต่ VOC
    guided flow ยังรับเทิร์นและเดินคำถามร้องเรียนต่อในช่องทางเสียงได้
    """
    full = _full_agent_with_flows()

    voice = scoped_voice_agent(full)

    assert [_flow_name(flow) for flow in voice._guided_flows._flows] == [ToolName.OMS]
    # agent กลางต้องยังมี flow ครบทั้งสอง
    assert len(full._guided_flows._flows) == 2


def test_a_flow_without_an_identifiable_tool_is_dropped() -> None:
    """ระบุเจ้าของไม่ได้ให้ปิดไว้ก่อน ดีกว่าปล่อยผ่านโดยไม่ตั้งใจ"""
    full = _full_agent()
    full._guided_flows = GuidedFlows((_StubFlow(None),))

    voice = scoped_voice_agent(full)

    assert voice._guided_flows._flows == ()


def test_a_non_main_agent_gateway_is_returned_unchanged() -> None:
    """gateway จำลองในเทสต์ห่อไม่ได้ ต้องคืนตัวเดิมแทนการล้ม"""
    sentinel = object()

    assert scoped_voice_agent(sentinel) is sentinel  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_disabled_voc_flow_gates_catalog_and_reenable() -> None:
    """The live registry state gates VOC before flow code can access its catalog."""
    registry = _full_agent()._tools
    voc = _CatalogProbeVocTool()
    flow = VocGuidedFlow(voc, consent_notice_version="test")
    agent = MainAgent(_StubLLM(), registry, guided_flows=GuidedFlows((flow,)))
    conversation_id = uuid4()

    first = await agent.handle_chat(
        ChatRequest(message="ต้องการร้องเรียน", conversation_id=conversation_id)
    )
    assert first.choice_prompt is not None
    assert voc.catalog_reads == 1
    assert flow.is_active(conversation_id) is True

    registry.set_code_tool_enabled(ToolName.VOC.value, False)
    assert flow.is_active(conversation_id) is False
    await agent.handle_chat(
        ChatRequest(message="ต้องการร้องเรียน", conversation_id=conversation_id)
    )

    assert voc.catalog_reads == 1
    assert flow.is_active(conversation_id) is False

    registry.set_code_tool_enabled(ToolName.VOC.value, True)
    response = await agent.handle_chat(
        ChatRequest(message="ต้องการร้องเรียน", conversation_id=conversation_id)
    )

    assert voc.catalog_reads == 2
    assert response.choice_prompt is not None


def test_disabled_code_tool_state_carries_into_the_scoped_registry() -> None:
    """P4: ปิด code tool จากหน้า admin แล้ว ช่องทางเสียงต้องเห็นสถานะเดียวกัน

    scoped registry สร้างใหม่จาก registry กลาง — ถ้าไม่ส่งสถานะ disabled ต่อ
    tool ที่ปิดแล้วจะกลับมาใช้ได้ในช่องทางเสียง
    """
    full = _full_agent()
    full._tools.set_code_tool_enabled(ToolName.OMS.value, False)

    voice = scoped_voice_agent(full)

    assert voice._tools.code_tool_enabled(ToolName.OMS.value) is False
    assert ToolName.OMS in voice._tools.names  # ยังอยู่ใน allowlist เสียงได้ตามเดิม


def test_open_scoped_agent_tracks_later_shared_registry_toggle() -> None:
    full = _full_agent()
    voice = scoped_voice_agent(full)

    full._tools.set_code_tool_enabled(ToolName.OMS.value, False)

    assert voice._tools.code_tool_enabled(ToolName.OMS.value) is False


@pytest.mark.asyncio
async def test_disabled_code_tool_is_refused_on_the_voice_path() -> None:
    full = _full_agent()
    full._tools.set_code_tool_enabled(ToolName.OMS.value, False)

    voice = scoped_voice_agent(full)
    call = ToolCall(
        call_id=uuid4(),
        name=ToolName.OMS,
        action=ToolAction.OMS_GET_OUTAGE_BY_CA,
        input={"caNumber": "123456789012"},
    )

    result = await voice._tools.execute(
        call, ToolContext(conversation_id=uuid4(), trace_id=uuid4())
    )

    assert result.status is ToolResultStatus.ERROR
    assert result.error is not None
    assert "ปิดใช้งาน" in result.error.message
