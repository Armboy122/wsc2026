"""Simulated VOC (voice-of-customer) tool (``voc_tool``).

Exposes the frozen ``list_categories``, ``prepare_case``, and internal
``submit_case`` actions. All results are simulated.
"""

from __future__ import annotations

from typing import Any

from app.backends.simulated_voc import SimulatedVocBackend, default_backend
from app.contracts import ToolAction, ToolName
from app.tools._base import SimulatedTool


class VocTool(SimulatedTool):
    """Top-level VOC tool; owns only the three frozen VOC actions."""

    name = ToolName.VOC

    def __init__(self, backend: SimulatedVocBackend | None = None) -> None:
        self.backend = backend if backend is not None else default_backend

    def _run(self, action: ToolAction, input_model: Any) -> dict[str, Any]:
        if action is ToolAction.VOC_LIST_CATEGORIES:
            return self.backend.list_categories()
        if action is ToolAction.VOC_PREPARE_CASE:
            return self.backend.prepare_case(
                input_model.category,
                input_model.subject,
                input_model.detail,
                input_model.contact_channel,
                input_model.idempotency_key,
            )
        if action is ToolAction.VOC_SUBMIT_CASE:
            return self.backend.submit_case(
                input_model.pending_action_id,
                input_model.idempotency_key,
            )
        raise ValueError(f"Unhandled action {action.value}")
