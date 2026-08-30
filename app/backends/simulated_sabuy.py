"""Deterministic in-memory Sabuy (bill payment) backend.

Reads fixed fixture accounts from ``data/mock/sabuy_accounts.json`` and records
simulated payments in process-local state. No live PEA call is ever made.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from app.backends import BackendError, load_mock_json
from app.contracts import PaymentMethod, ToolErrorCode


class SimulatedSabuyBackend:
    """Simulated Sabuy account/payment backend with resettable process-local state."""

    def __init__(self) -> None:
        rows = load_mock_json("sabuy_accounts.json")
        self._accounts: dict[str, dict[str, Any]] = {row["accountRef"]: row for row in rows}
        self._prepared: dict[str, dict[str, Any]] = {}
        self._receipts: dict[str, dict[str, Any]] = {}
        self._seq = 0

    def reset(self) -> None:
        """Clear prepared drafts and submitted receipts, restoring pristine state."""
        self._prepared.clear()
        self._receipts.clear()
        self._seq = 0

    def get_account_summary(self, account_ref: str) -> dict[str, Any]:
        """Return the fixture summary for ``account_ref`` (read-only)."""
        account = self._accounts.get(account_ref)
        if account is None:
            raise BackendError(ToolErrorCode.NOT_FOUND, "Account not found.")
        return {
            "accountRef": account["accountRef"],
            "customerDisplayName": account["customerDisplayName"],
            "outstandingBalanceThb": account["outstandingBalanceThb"],
            "dueDate": account["dueDate"],
            "paymentStatus": account["paymentStatus"],
        }

    def prepare_payment(
        self,
        account_ref: str,
        amount_thb: Decimal,
        payment_method: PaymentMethod,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Validate and stage a payment draft. No simulated payment is recorded."""
        if account_ref not in self._accounts:
            raise BackendError(ToolErrorCode.NOT_FOUND, "Account not found.")
        amount = str(amount_thb)
        self._prepared[idempotency_key] = {
            "accountRef": account_ref,
            "amountThb": amount,
            "paymentMethod": payment_method.value,
        }
        summary = (
            f"Prepare a payment of {amount} THB to account {account_ref} "
            f"using {payment_method.value}."
        )
        return {
            "accountRef": account_ref,
            "amountThb": amount,
            "paymentMethod": payment_method.value,
            "summary": summary,
        }

    def submit_payment(self, pending_action_id: UUID, idempotency_key: str) -> dict[str, Any]:
        """Record the staged payment exactly once, de-duplicating by idempotency key."""
        existing = self._receipts.get(idempotency_key)
        if existing is not None:
            return dict(existing)
        prepared = self._prepared.get(idempotency_key)
        if prepared is None:
            raise BackendError(
                ToolErrorCode.NOT_FOUND,
                "No prepared payment for this idempotency key.",
            )
        self._seq += 1
        receipt = {
            "receiptId": f"SIM-RCPT-{self._seq:06d}",
            "accountRef": prepared["accountRef"],
            "amountThb": prepared["amountThb"],
            "status": "accepted",
        }
        self._receipts[idempotency_key] = receipt
        return dict(receipt)


default_backend = SimulatedSabuyBackend()
