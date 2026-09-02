"""Generic guided-intake seam contributed by enabled operational plugins.

Some operational writes need canonical codes that only the backend catalog
defines.  A language model cannot invent those, so the owning plugin drives a
deterministic question sequence instead and MainAgent only routes turns to it.
MainAgent therefore stays free of any plugin-specific intake knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.contracts import ChoicePrompt, ToolAction, ToolName


@dataclass(frozen=True, slots=True)
class GuidedTurn:
    """One deterministic guided step.

    Exactly one of ``prompt`` or ``tool_call`` is meaningful: the flow either
    still needs an answer, or it has everything required to prepare the write.
    """

    message: str
    prompt: ChoicePrompt | None = None
    tool_name: ToolName | None = None
    tool_action: ToolAction | None = None
    tool_input: dict[str, Any] | None = None
    # ยุติ session เมื่อผู้ใช้ไม่ยินยอมหรือยกเลิก เพื่อไม่ค้างสถานะไว้ในบทสนทนา
    finished: bool = False

    @property
    def has_tool_call(self) -> bool:
        return self.tool_name is not None and self.tool_action is not None


class GuidedFlow(Protocol):
    """A plugin-owned deterministic intake flow bound to one conversation."""

    async def start(self, conversation_id: UUID, message: str) -> GuidedTurn | None:
        """เริ่ม flow เมื่อข้อความบ่งชี้เจตนาที่ปลั๊กอินนี้รับผิดชอบ"""
        ...

    def is_active(self, conversation_id: UUID) -> bool:
        """True เมื่อบทสนทนานี้กำลังอยู่ระหว่างการถามตอบของ flow"""
        ...

    async def advance(
        self,
        conversation_id: UUID,
        message: str,
        selected_prompt_id: str | None,
        selected_value: str | None,
    ) -> GuidedTurn | None:
        """รับคำตอบหนึ่งขั้นแล้วคืนขั้นถัดไป"""
        ...

    def cancel(self, conversation_id: UUID) -> None:
        """ล้างสถานะของบทสนทนานี้"""
        ...

    def reset(self) -> None:
        """ล้างสถานะทั้งหมดสำหรับการรันเดโมใหม่"""
        ...

    def attach_llm(self, llm_client: Any) -> None:
        """รับ LLM client ไว้ช่วยตีความคำตอบ (ไม่บังคับ; flow ที่ไม่ใช้ไม่ต้องมี method นี้)"""
        ...


class GuidedFlows:
    """Route a turn to the first enabled flow that claims it."""

    def __init__(self, flows: tuple[GuidedFlow, ...] = ()) -> None:
        self._flows = flows

    def active_flow(self, conversation_id: UUID) -> GuidedFlow | None:
        return next((flow for flow in self._flows if flow.is_active(conversation_id)), None)

    async def start(self, conversation_id: UUID, message: str) -> GuidedTurn | None:
        for flow in self._flows:
            turn = await flow.start(conversation_id, message)
            if turn is not None:
                return turn
        return None

    def reset(self) -> None:
        for flow in self._flows:
            flow.reset()

    def attach_llm(self, llm_client: Any) -> None:
        """แจก LLM ให้ flow ที่ประกาศว่าใช้ได้ โดยไม่บังคับให้ทุก flow ต้องรองรับ"""
        for flow in self._flows:
            attach = getattr(flow, "attach_llm", None)
            if callable(attach):
                attach(llm_client)

    def __bool__(self) -> bool:
        return bool(self._flows)
