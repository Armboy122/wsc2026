"""Gemini Live voice mode integration (session-bound).

``VoiceBridge`` คือตัวกลางบาง ๆ ระหว่าง Gemini Live backend และ Main Agent
โดยเรียกได้เพียง ``handle_chat`` / ``confirm_pending_action`` /
``reject_pending_action`` และไม่แตะ ToolRegistry หรือ backend ธุรกิจใด ๆ
"""

from app.live.bridge import (
    ActionConflictError,
    InvalidTextError,
    NoPendingActionError,
    VoiceBridge,
    VoiceBridgeError,
)
from app.live.models import ActionDecisionResult, ChatTurnResult, MainAgentGateway

__all__ = [
    "ActionConflictError",
    "ActionDecisionResult",
    "ChatTurnResult",
    "InvalidTextError",
    "MainAgentGateway",
    "NoPendingActionError",
    "VoiceBridge",
    "VoiceBridgeError",
]
