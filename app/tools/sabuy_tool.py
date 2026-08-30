"""Simulated Sabuy bill-payment tool (``sabuy_tool``).

Exposes the frozen ``get_account_summary``, ``prepare_payment``, and internal
``submit_payment`` actions. All results are simulated.
"""

from __future__ import annotations

from typing import Any

from app.backends.simulated_sabuy import SimulatedSabuyBackend, default_backend
from app.contracts import ToolAction, ToolName
from app.tools._base import SimulatedTool


class SabuyTool(SimulatedTool):
    """Top-level Sabuy tool; owns only the three frozen Sabuy actions."""

    name = ToolName.SABUY

    def __init__(self, backend: SimulatedSabuyBackend | None = None) -> None:
        self.backend = backend if backend is not None else default_backend

    def _run(self, action: ToolAction, input_model: Any) -> dict[str, Any]:
        if action is ToolAction.SABUY_ACCOUNT_SUMMARY:
            return self.backend.get_account_summary(input_model.account_ref)
        if action is ToolAction.SABUY_PREPARE_PAYMENT:
            return self.backend.prepare_payment(
                input_model.account_ref,
                input_model.amount_thb,
                input_model.payment_method,
                input_model.idempotency_key,
            )
        if action is ToolAction.SABUY_SUBMIT_PAYMENT:
            return self.backend.submit_payment(
                input_model.pending_action_id,
                input_model.idempotency_key,
            )
        raise ValueError(f"Unhandled action {action.value}")
