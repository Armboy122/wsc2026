"""Deterministic in-memory OMS (outage management) backend.

Reads fixed outage areas from ``data/mock/oms_outages.json`` and records
simulated outage reports in process-local state. No live OMS call is made. Every
outage read/prepare result carries a ``safetyMessage``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.backends import BackendError, load_mock_json
from app.contracts import ToolErrorCode


class SimulatedOmsBackend:
    """Simulated OMS outage/report backend with resettable process-local state."""

    def __init__(self) -> None:
        rows = load_mock_json("oms_outages.json")
        self._areas: dict[str, dict[str, Any]] = {row["areaCode"]: row for row in rows}
        self._prepared: dict[str, dict[str, Any]] = {}
        self._reports: dict[str, dict[str, Any]] = {}
        self._seq = 0

    def reset(self) -> None:
        """Clear prepared drafts and submitted reports, restoring pristine state."""
        self._prepared.clear()
        self._reports.clear()
        self._seq = 0

    def get_outage_status(self, area_code: str) -> dict[str, Any]:
        """Return the fixture outage status for ``area_code`` (read-only)."""
        area = self._areas.get(area_code)
        if area is None:
            raise BackendError(ToolErrorCode.NOT_FOUND, "Area not found.")
        return {
            "areaCode": area["areaCode"],
            "status": area["status"],
            "updatedAt": area["updatedAt"],
            "estimatedRestoreAt": area["estimatedRestoreAt"],
            "safetyMessage": area["safetyMessage"],
        }

    def prepare_outage_report(
        self,
        area_code: str,
        location_note: str,
        symptoms: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Validate and stage an outage report draft. No simulated report is filed yet."""
        area = self._areas.get(area_code)
        if area is None:
            raise BackendError(ToolErrorCode.NOT_FOUND, "Area not found.")
        self._prepared[idempotency_key] = {
            "areaCode": area_code,
            "locationNote": location_note,
            "symptoms": symptoms,
        }
        summary = f"Prepare an outage report for area {area_code}."
        return {
            "areaCode": area_code,
            "summary": summary,
            "safetyMessage": area["safetyMessage"],
        }

    def submit_outage_report(self, pending_action_id: UUID, idempotency_key: str) -> dict[str, Any]:
        """File the staged report exactly once, de-duplicating by idempotency key."""
        existing = self._reports.get(idempotency_key)
        if existing is not None:
            return dict(existing)
        prepared = self._prepared.get(idempotency_key)
        if prepared is None:
            raise BackendError(
                ToolErrorCode.NOT_FOUND,
                "No prepared outage report for this idempotency key.",
            )
        self._seq += 1
        report = {
            "reportId": f"SIM-RPT-{self._seq:06d}",
            "status": "submitted",
            "areaCode": prepared["areaCode"],
        }
        self._reports[idempotency_key] = report
        return dict(report)


default_backend = SimulatedOmsBackend()
