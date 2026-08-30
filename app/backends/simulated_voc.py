"""Deterministic in-memory VOC (voice-of-customer) backend.

Reads fixed categories from ``data/mock/voc_categories.json`` and records
simulated cases in process-local state. No live CRM or contact-centre call is made.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.backends import BackendError, load_mock_json
from app.contracts import ContactChannel, ToolErrorCode, VocCategory


class SimulatedVocBackend:
    """Simulated VOC category/case backend with resettable process-local state."""

    def __init__(self) -> None:
        self._categories: list[dict[str, Any]] = load_mock_json("voc_categories.json")
        self._prepared: dict[str, dict[str, Any]] = {}
        self._cases: dict[str, dict[str, Any]] = {}
        self._seq = 0

    def reset(self) -> None:
        """Clear prepared drafts and submitted cases, restoring pristine state."""
        self._prepared.clear()
        self._cases.clear()
        self._seq = 0

    def list_categories(self) -> dict[str, Any]:
        """Return the fixed category list (read-only)."""
        return {
            "categories": [
                {"code": item["code"], "label": item["label"]} for item in self._categories
            ]
        }

    def prepare_case(
        self,
        category: VocCategory,
        subject: str,
        detail: str,
        contact_channel: ContactChannel,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Validate and stage a case draft. No simulated case is created yet."""
        self._prepared[idempotency_key] = {
            "category": category.value,
            "subject": subject,
            "detail": detail,
            "contactChannel": contact_channel.value,
        }
        summary = f"Prepare a {category.value} case."
        return {
            "category": category.value,
            "subject": subject,
            "summary": summary,
        }

    def submit_case(self, pending_action_id: UUID, idempotency_key: str) -> dict[str, Any]:
        """Create the staged case exactly once, de-duplicating by idempotency key."""
        existing = self._cases.get(idempotency_key)
        if existing is not None:
            return dict(existing)
        prepared = self._prepared.get(idempotency_key)
        if prepared is None:
            raise BackendError(
                ToolErrorCode.NOT_FOUND,
                "No prepared case for this idempotency key.",
            )
        self._seq += 1
        case = {
            "caseId": f"SIM-CASE-{self._seq:06d}",
            "status": "submitted",
            "category": prepared["category"],
        }
        self._cases[idempotency_key] = case
        return dict(case)


default_backend = SimulatedVocBackend()
