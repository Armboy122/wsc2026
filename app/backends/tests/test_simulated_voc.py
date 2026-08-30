"""Tests for the deterministic simulated VOC backend."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.backends import BackendError
from app.backends.simulated_voc import SimulatedVocBackend
from app.contracts import ContactChannel, ToolErrorCode, VocCategory


def test_list_categories_returns_fixture_categories():
    backend = SimulatedVocBackend()
    out = backend.list_categories()
    codes = [item["code"] for item in out["categories"]]
    assert codes == ["billing", "service", "safety", "other"]
    assert all(item["label"] for item in out["categories"])


def test_prepare_case_has_no_side_effect():
    backend = SimulatedVocBackend()
    subject = "Wrong bill amount"
    detail = "My latest bill looks too high."
    out = backend.prepare_case(
        VocCategory.BILLING,
        subject,
        detail,
        ContactChannel.EMAIL,
        "k1",
    )
    assert out["category"] == "billing"
    assert out["subject"] == subject
    # The confirmation summary must be PII-safe and category-only: it must
    # never expose the user-supplied subject or detail.
    assert out["summary"] == "Prepare a billing case."
    assert subject not in out["summary"]
    assert detail not in out["summary"]
    # Preparing must not create a case.
    assert backend._cases == {}


def test_submit_case_without_prepare_raises_not_found():
    backend = SimulatedVocBackend()
    with pytest.raises(BackendError) as exc:
        backend.submit_case(uuid4(), "missing")
    assert exc.value.code is ToolErrorCode.NOT_FOUND


def test_submit_case_deduplicates_by_idempotency_key():
    backend = SimulatedVocBackend()
    backend.prepare_case(
        VocCategory.SAFETY,
        "Fallen line",
        "A power line is down on my street.",
        ContactChannel.PHONE,
        "k1",
    )
    first = backend.submit_case(uuid4(), "k1")
    second = backend.submit_case(uuid4(), "k1")
    assert first == second
    assert first["status"] == "submitted"
    assert first["category"] == "safety"
    assert len(backend._cases) == 1


def test_reset_clears_state():
    backend = SimulatedVocBackend()
    backend.prepare_case(
        VocCategory.OTHER,
        "Question",
        "General question.",
        ContactChannel.NONE,
        "k1",
    )
    backend.submit_case(uuid4(), "k1")
    backend.reset()
    assert backend._prepared == {}
    assert backend._cases == {}
    assert backend._seq == 0
