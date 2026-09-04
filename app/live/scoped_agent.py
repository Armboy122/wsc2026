"""Gateway ที่จำกัดชุดเครื่องมือของช่องทางเสียงโดยไม่แตะ Main Agent กลาง

ทุกช่องทาง (REST, LINE, เสียง) ใช้ ``MainAgent`` อินสแตนซ์เดียวกัน การตัด
เครื่องมือที่ ``ToolRegistry`` หรือ plugin manifest จึงตัดให้ทุกช่องทางพร้อมกัน
โมดูลนี้ห่อ Main Agent เดิมด้วย gateway บาง ๆ ที่ประกอบ ``MainAgent`` ตัวใหม่
ซึ่งใช้ registry ที่กรองแล้ว แต่ **ใช้ store ชุดเดียวกับต้นฉบับ** ทำให้

- ช่องทางเสียงเห็นเฉพาะเครื่องมือใน allowlist
- pending action ที่เตรียมผ่านเสียงยังกดยืนยันบนเว็บได้ และ trace อ่านได้ที่เดิม
- ช่องทางอื่นไม่สูญเสียเครื่องมือใด ๆ

ขอบเขตนี้เป็นการกรอง ไม่ใช่การเพิ่มสิทธิ์: allowlist จะตัดได้เฉพาะเครื่องมือ
ที่ registry ต้นทางมีอยู่แล้วเท่านั้น
"""

from __future__ import annotations

from app.agent.guided_flow import GuidedFlows
from app.agent.main_agent import MainAgent
from app.agent.registry import ToolRegistry
from app.contracts import ToolName
from app.live.models import MainAgentGateway

# ช่องทางเสียงตอบคำถามความรู้และงานไฟฟ้าขัดข้องเท่านั้น
VOICE_TOOLS: frozenset[ToolName] = frozenset({ToolName.KNOWLEDGE, ToolName.OMS})


def scoped_voice_agent(
    agent: MainAgentGateway,
    *,
    allowed: frozenset[ToolName] = VOICE_TOOLS,
) -> MainAgentGateway:
    """คืน gateway ที่เห็นเฉพาะเครื่องมือใน ``allowed``

    หากห่อไม่ได้ เช่น ถูกฉีด gateway จำลองในเทสต์ จะคืนตัวเดิมโดยไม่ล้ม
    เพราะการจำกัดเครื่องมือเป็นการลดสิทธิ์ ไม่ใช่ด่านความปลอดภัยสุดท้าย
    (registry ยังตรวจ tool/action ทุกครั้งที่ ``execute``)
    """
    if not isinstance(agent, MainAgent):
        return agent
    registry = _scoped_registry(agent._tools, allowed)  # noqa: SLF001 - ห่อ agent ของเราเอง
    if registry is None:
        return agent
    scoped = MainAgent(
        agent._llm,  # noqa: SLF001
        registry,
        # store ใช้ร่วมกับ agent เดิม เพื่อให้ยืนยัน/trace ข้ามช่องทางได้
        conversations=agent._conversations,  # noqa: SLF001
        pending_actions=agent._pending_actions,  # noqa: SLF001
        traces=agent._traces,  # noqa: SLF001
        # guided flow ทำงานก่อน planner และไม่ผ่าน catalogue จึงต้องกรองแยกต่างหาก
        # ไม่เช่นนั้น flow ของเครื่องมือที่ถูกตัดจะยังรับเทิร์นในช่องทางนี้ได้
        guided_flows=_scoped_flows(agent._guided_flows, allowed),  # noqa: SLF001
    )
    return scoped


def _scoped_flows(flows: GuidedFlows, allowed: frozenset[ToolName]) -> GuidedFlows:
    """คง flow เฉพาะของเครื่องมือใน allowlist

    flow ประกาศเจ้าของผ่านเครื่องมือที่ถือไว้ (``_tool.name``) flow ที่ระบุ
    เจ้าของไม่ได้จะถูกตัดออก เพื่อให้ค่าเริ่มต้นเป็นการปิดไว้ก่อน
    """
    return GuidedFlows(
        tuple(flow for flow in flows._flows if _flow_tool(flow) in allowed)  # noqa: SLF001
    )


def _flow_tool(flow: object) -> ToolName | None:
    name = getattr(getattr(flow, "_tool", None), "name", None)
    return name if isinstance(name, ToolName) else None


def _scoped_registry(
    registry: ToolRegistry, allowed: frozenset[ToolName]
) -> ToolRegistry | None:
    """สร้าง registry ใหม่ที่มีเฉพาะเครื่องมือใน allowlist

    คืน ``None`` เมื่อกรองแล้วประกอบ registry ไม่ได้ เช่น ไม่มี Knowledge ซึ่ง
    ``ToolRegistry`` บังคับว่าต้องมีเสมอ ผู้เรียกจะถอยไปใช้ registry เดิม
    """
    tools = [tool for name, tool in registry._tools.items() if name in allowed]  # noqa: SLF001
    catalogue = tuple(
        definition
        for definition in registry.llm_catalogue
        if definition.name in allowed
    )
    try:
        return ToolRegistry(
            tools,
            # BUILT_IN_CATALOGUE ถูกเติมโดย ToolRegistry เอง ส่งเฉพาะส่วนปลั๊กอิน
            catalogue=tuple(
                definition
                for definition in catalogue
                if definition.name is not ToolName.KNOWLEDGE
            ),
            # policy ไม่ได้ประกาศว่าเป็นของเครื่องมือใด จึงคงไว้ทั้งชุด ปลอดภัย
            # เพราะ policy จัดรูปแบบจาก ToolResult ที่เกิดขึ้นจริงเท่านั้น และ
            # เครื่องมือที่ถูกกรองออกจะไม่มีทางสร้างผลลัพธ์ในช่องทางนี้ได้เลย
            response_policies=registry.response_policies.policies,
        )
    except ValueError:
        return None
