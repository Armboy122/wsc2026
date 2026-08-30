"""Tests for the deterministic simulated OMS backend."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.backends import BackendError
from app.backends.simulated_oms import SimulatedOmsBackend
from app.contracts import ToolErrorCode


def test_get_outage_status_includes_safety_message():
    backend = SimulatedOmsBackend()
    out = backend.get_outage_status("BKK-01")
    assert out["areaCode"] == "BKK-01"
    assert out["status"] == "normal"
    assert out["safetyMessage"]


def test_get_outage_status_unplanned_has_restore_time():
    backend = SimulatedOmsBackend()
    out = backend.get_outage_status("HKT-03")
    assert out["status"] == "unplanned_outage"
    assert out["estimatedRestoreAt"] is not None
    assert out["safetyMessage"]


def test_get_outage_status_unknown_area_raises_not_found():
    backend = SimulatedOmsBackend()
    with pytest.raises(BackendError) as exc:
        backend.get_outage_status("NOPE")
    assert exc.value.code is ToolErrorCode.NOT_FOUND


def test_prepare_outage_report_has_no_side_effect_and_includes_safety():
    backend = SimulatedOmsBackend()
    out = backend.prepare_outage_report(
        "CNX-02",
        "Main street near the market",
        "Power flickered then went out.",
        "k1",
    )
    assert out["areaCode"] == "CNX-02"
    assert out["summary"]
    assert out["safetyMessage"]
    # Preparing must not file a report.
    assert backend._reports == {}


def test_prepare_outage_report_unknown_area_raises_not_found():
    backend = SimulatedOmsBackend()
    with pytest.raises(BackendError) as exc:
        backend.prepare_outage_report("NOPE", "x", "y", "k1")
    assert exc.value.code is ToolErrorCode.NOT_FOUND


def test_submit_outage_report_without_prepare_raises_not_found():
    backend = SimulatedOmsBackend()
    with pytest.raises(BackendError) as exc:
        backend.submit_outage_report(uuid4(), "missing")
    assert exc.value.code is ToolErrorCode.NOT_FOUND


def test_submit_outage_report_deduplicates_by_idempotency_key():
    backend = SimulatedOmsBackend()
    backend.prepare_outage_report("HKT-03", "Near pier", "No power since morning.", "k1")
    first = backend.submit_outage_report(uuid4(), "k1")
    second = backend.submit_outage_report(uuid4(), "k1")
    assert first == second
    assert first["status"] == "submitted"
    assert first["areaCode"] == "HKT-03"
    assert len(backend._reports) == 1


def test_reset_clears_state():
    backend = SimulatedOmsBackend()
    backend.prepare_outage_report("BKK-01", "x", "y", "k1")
    backend.submit_outage_report(uuid4(), "k1")
    backend.reset()
    assert backend._prepared == {}
    assert backend._reports == {}
    assert backend._seq == 0
