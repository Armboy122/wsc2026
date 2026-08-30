"""Tests for the deterministic simulated Sabuy backend."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.backends import BackendError
from app.backends.simulated_sabuy import SimulatedSabuyBackend
from app.contracts import PaymentMethod, ToolErrorCode


def test_get_account_summary_returns_fixture_data():
    backend = SimulatedSabuyBackend()
    out = backend.get_account_summary("PEA-1001")
    assert out["accountRef"] == "PEA-1001"
    assert out["customerDisplayName"] == "Somchai Jaidee"
    assert out["outstandingBalanceThb"] == "1250.50"
    assert out["dueDate"] == "2026-09-15"
    assert out["paymentStatus"] == "current"


def test_get_account_summary_paid_has_null_due_date():
    backend = SimulatedSabuyBackend()
    out = backend.get_account_summary("PEA-1003")
    assert out["paymentStatus"] == "paid"
    assert out["dueDate"] is None


def test_get_account_summary_unknown_raises_not_found():
    backend = SimulatedSabuyBackend()
    with pytest.raises(BackendError) as exc:
        backend.get_account_summary("NOPE")
    assert exc.value.code is ToolErrorCode.NOT_FOUND


def test_prepare_payment_has_no_side_effect():
    backend = SimulatedSabuyBackend()
    out = backend.prepare_payment("PEA-1001", Decimal("100.00"), PaymentMethod.DEMO_CARD, "k1")
    assert out["accountRef"] == "PEA-1001"
    assert out["amountThb"] == "100.00"
    assert out["paymentMethod"] == "demo_card"
    assert out["summary"]
    # Preparing must not record a receipt.
    assert backend._receipts == {}


def test_prepare_payment_unknown_account_raises_not_found():
    backend = SimulatedSabuyBackend()
    with pytest.raises(BackendError) as exc:
        backend.prepare_payment("NOPE", Decimal("10.00"), PaymentMethod.DEMO_CARD, "k1")
    assert exc.value.code is ToolErrorCode.NOT_FOUND


def test_submit_payment_without_prepare_raises_not_found():
    backend = SimulatedSabuyBackend()
    with pytest.raises(BackendError) as exc:
        backend.submit_payment(uuid4(), "missing")
    assert exc.value.code is ToolErrorCode.NOT_FOUND


def test_submit_payment_deduplicates_by_idempotency_key():
    backend = SimulatedSabuyBackend()
    backend.prepare_payment("PEA-1001", Decimal("100.00"), PaymentMethod.DEMO_BANK, "k1")
    first = backend.submit_payment(uuid4(), "k1")
    second = backend.submit_payment(uuid4(), "k1")
    assert first == second
    assert first["status"] == "accepted"
    assert first["accountRef"] == "PEA-1001"
    assert first["amountThb"] == "100.00"
    assert len(backend._receipts) == 1


def test_reset_clears_state():
    backend = SimulatedSabuyBackend()
    backend.prepare_payment("PEA-1001", Decimal("50.00"), PaymentMethod.DEMO_CARD, "k1")
    backend.submit_payment(uuid4(), "k1")
    backend.reset()
    assert backend._prepared == {}
    assert backend._receipts == {}
    assert backend._seq == 0
    with pytest.raises(BackendError):
        backend.submit_payment(uuid4(), "k1")
