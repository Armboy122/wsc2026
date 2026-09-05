"""Generic guided-intake seam contributed by enabled operational plugins.

Some operational writes need canonical codes that only the backend catalog
defines.  A language model cannot invent those, so the owning plugin drives a
deterministic question sequence instead and MainAgent only routes turns to it.
MainAgent therefore stays free of any plugin-specific intake knowledge.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.contracts import ChoicePrompt, ToolAction, ToolName
from app.core.logging import get_logger, log_extra

logger = get_logger(__name__)


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

    def __init__(
        self,
        flows: tuple[GuidedFlow, ...] = (),
        *,
        flow_enabled: Callable[[GuidedFlow], bool] | None = None,
    ) -> None:
        self._flows = flows
        self._flow_enabled = flow_enabled
        self._invalidated_owners: set[str] = set()

    def _enabled_flows(self) -> Iterator[GuidedFlow]:
        for flow in self._flows:
            if self._flow_enabled is None or self._flow_enabled(flow):
                yield flow
            else:
                owner = _flow_owner_slug(flow)
                if owner is not None and owner in self._invalidated_owners:
                    continue
                if owner is not None:
                    self._invalidated_owners.add(owner)
                    self._reset_flows(owner)
                else:
                    self._reset_flow(flow, None)

    def bind_tool_enabled(self, tool_enabled: Callable[[str], bool]) -> None:
        """Bind live registry state so plugin flows cannot outlive their tool."""
        self._flow_enabled = lambda flow: (
            (owner := _flow_owner_slug(flow)) is not None
            and owner not in self._invalidated_owners
            and tool_enabled(owner)
        )

    def code_tool_state_changed(self, slug: str, enabled: bool) -> None:
        """Eagerly clear active flow state when its owning tool is disabled."""
        if enabled:
            if slug not in self._invalidated_owners:
                return
            if self._reset_flows(slug):
                self._invalidated_owners.discard(slug)
            else:
                logger.warning(
                    "guided_flow_remains_quarantined",
                    extra=log_extra(slug=slug),
                )
            return
        # Quarantine before cleanup: a failing reset must never leave a flow
        # eligible for resurrection when the tool is enabled again.
        self._invalidated_owners.add(slug)
        if not self._reset_flows(slug):
            logger.warning(
                "guided_flow_remains_quarantined",
                extra=log_extra(slug=slug),
            )

    def _reset_flows(self, owner: str) -> bool:
        clean = True
        for flow in self._flows:
            if _flow_owner_slug(flow) != owner:
                continue
            clean = self._reset_flow(flow, owner) and clean
        return clean

    @staticmethod
    def _reset_flow(flow: GuidedFlow, owner: str | None) -> bool:
        try:
            flow.reset()
        except Exception as exc:
            logger.warning(
                "guided_flow_reset_failed",
                extra=log_extra(
                    slug=owner or "unknown", error_type=type(exc).__name__
                ),
            )
            return False
        return True

    def active_flow(self, conversation_id: UUID) -> GuidedFlow | None:
        return next(
            (flow for flow in self._enabled_flows() if flow.is_active(conversation_id)),
            None,
        )

    async def start(self, conversation_id: UUID, message: str) -> GuidedTurn | None:
        for flow in self._enabled_flows():
            turn = await flow.start(conversation_id, message)
            if turn is not None:
                return turn
        return None

    def reset(self) -> None:
        clean = True
        for flow in self._flows:
            owner = _flow_owner_slug(flow)
            if not self._reset_flow(flow, owner):
                clean = False
                if owner is not None:
                    self._invalidated_owners.add(owner)
        if not clean:
            # Demo reset is an explicit lifecycle operation: callers must not
            # receive reset:true when any flow could not be cleaned up.
            raise RuntimeError("guided flow reset failed")
        self._invalidated_owners.clear()

    def attach_llm(self, llm_client: Any) -> None:
        """แจก LLM ให้ flow ที่ประกาศว่าใช้ได้ โดยไม่บังคับให้ทุก flow ต้องรองรับ"""
        for flow in self._flows:
            attach = getattr(flow, "attach_llm", None)
            if callable(attach):
                attach(llm_client)

    def __bool__(self) -> bool:
        return any(self._enabled_flows())


def _flow_owner_slug(flow: object) -> str | None:
    owner = getattr(getattr(flow, "_tool", None), "name", None)
    if owner is None:
        return None
    return getattr(owner, "value", owner)
