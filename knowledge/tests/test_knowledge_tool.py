"""Frozen-contract tests for knowledge_tool (Worker B — knowledge)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app import contracts
from app.backends.full_document_knowledge import GroundedEvidence, KnowledgeBackendError
from decimal import Decimal
from app.tools.knowledge_tool import KnowledgeTool

EMPTY_EVIDENCE = GroundedEvidence("", 0, ())

EVIDENCE = GroundedEvidence(
    answer_context="[1] PEA Billing\nBills are due on the 20th.\nsource: https://pea.example/billing",
    result_count=1,
    citations=(
        contracts.Citation(
            source_id="source/PEA_Billing.docx",
            title="PEA Billing",
            uri="https://pea.example/billing",
            snippet="Bills are due on the 20th.",
            page=2,
        ),
    ),
)


class BillBackend:
    def __init__(self, evidence: GroundedEvidence) -> None:
        self.evidence = evidence
        self.bill_calls = 0
        self.search_calls = 0

    async def bill_evidence(self, max_results: int) -> GroundedEvidence:
        self.bill_calls += 1
        return self.evidence

    async def search(self, query: str, max_results: int) -> GroundedEvidence:
        self.search_calls += 1
        raise AssertionError("bill path must not use generic search")


class FakeBackend:
    """Network-free structural stand-in for the knowledge search protocol."""

    def __init__(self, evidence: GroundedEvidence | None = None, error: Exception | None = None):
        self.evidence = evidence if evidence is not None else EMPTY_EVIDENCE
        self.error = error
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, max_results: int) -> GroundedEvidence:
        self.calls.append((query, max_results))
        if self.error is not None:
            raise self.error
        return self.evidence


def make_call(query: str = "when is my bill due", max_results: int | None = 3) -> contracts.ToolCall:
    payload: dict = {"query": query}
    if max_results is not None:
        payload["maxResults"] = max_results
    return contracts.ToolCall(
        call_id=uuid4(),
        name=contracts.ToolName.KNOWLEDGE,
        action=contracts.ToolAction.KNOWLEDGE_SEARCH,
        input=payload,
    )


def run(tool: KnowledgeTool, call: contracts.ToolCall) -> contracts.ToolResult:
    return asyncio.run(tool.execute(call, None))


def bill_call(**values: object) -> contracts.ToolCall:
    return contracts.ToolCall(
        call_id=uuid4(),
        name=contracts.ToolName.KNOWLEDGE,
        action=contracts.ToolAction.KNOWLEDGE_SEARCH,
        input={"query": "คำนวณค่าไฟ", "maxResults": 1, "billCalculation": values},
    )


def test_bill_path_uses_verified_evidence_before_calculation_and_never_searches() -> None:
    backend = BillBackend(EVIDENCE)
    result = run(
        KnowledgeTool(backend=backend),
        bill_call(usage=Decimal("966"), billingMonth=9, billingYear=2569, tariffSubtype="1.1.2"),
    )

    assert result.status is contracts.ToolResultStatus.SUCCESS
    assert result.data["billOutcome"]["status"] == "calculated"
    assert result.data["billOutcome"]["finalTotal"] == "4365.471172"
    assert result.data["billOutcome"]["displayTotal"] == "4365.47"
    assert result.citations == EVIDENCE.citations
    assert backend.bill_calls == 1
    assert backend.search_calls == 0


def test_bill_clarification_does_not_call_any_backend() -> None:
    backend = BillBackend(EVIDENCE)
    result = run(KnowledgeTool(backend=backend), bill_call(usage=Decimal("966")))

    assert result.data["billOutcome"]["status"] == "clarification"
    assert "finalTotal" not in result.data["billOutcome"]
    assert backend.bill_calls == 0
    assert backend.search_calls == 0


def test_bill_unavailable_period_does_not_call_backend() -> None:
    backend = BillBackend(EVIDENCE)
    result = run(
        KnowledgeTool(backend=backend),
        bill_call(usage=Decimal("966"), billingMonth=8, billingYear=2569, tariffSubtype="1.1.2"),
    )

    assert result.data["billOutcome"]["status"] == "unavailable"
    assert "finalTotal" not in result.data["billOutcome"]
    assert backend.bill_calls == 0
    assert backend.search_calls == 0


def test_bill_missing_evidence_fails_closed_without_total() -> None:
    backend = BillBackend(EMPTY_EVIDENCE)
    result = run(
        KnowledgeTool(backend=backend),
        bill_call(usage=Decimal("966"), billingMonth=9, billingYear=2569, tariffSubtype="1.1.2"),
    )

    assert result.data["billOutcome"]["status"] == "unavailable"
    assert "finalTotal" not in result.data["billOutcome"]


def test_success_shape_matches_frozen_contract() -> None:
    tool = KnowledgeTool(backend=FakeBackend(EVIDENCE))
    call = make_call()
    result = run(tool, call)

    assert result.status is contracts.ToolResultStatus.SUCCESS
    assert result.simulation is False
    assert result.error is None
    assert result.call_id == call.call_id
    assert result.name is contracts.ToolName.KNOWLEDGE
    assert result.action is contracts.ToolAction.KNOWLEDGE_SEARCH
    assert set(result.data) == {"answerContext", "resultCount"}
    assert result.data["answerContext"] == EVIDENCE.answer_context
    assert result.data["resultCount"] == 1
    assert result.citations == EVIDENCE.citations


def test_success_serializes_camel_case() -> None:
    tool = KnowledgeTool(backend=FakeBackend(EVIDENCE))
    result = run(tool, make_call())
    dumped = result.model_dump(by_alias=True, mode="json")
    assert dumped["callId"] == str(result.call_id)
    assert dumped["simulation"] is False
    assert dumped["data"] == {
        "answerContext": EVIDENCE.answer_context,
        "resultCount": 1,
    }
    assert dumped["citations"][0]["sourceId"] == "source/PEA_Billing.docx"
    assert dumped["citations"][0]["page"] == 2


def test_no_evidence_returns_empty_context_and_zero_results() -> None:
    tool = KnowledgeTool(backend=FakeBackend(EMPTY_EVIDENCE))
    result = run(tool, make_call())
    assert result.status is contracts.ToolResultStatus.SUCCESS
    assert result.data == {"answerContext": "", "resultCount": 0}
    assert result.citations == ()


def test_max_results_default_is_three() -> None:
    backend = FakeBackend(EMPTY_EVIDENCE)
    run(KnowledgeTool(backend=backend), make_call(max_results=None))
    assert backend.calls == [("when is my bill due", 3)]


def test_max_results_passthrough() -> None:
    backend = FakeBackend(EMPTY_EVIDENCE)
    run(KnowledgeTool(backend=backend), make_call(max_results=5))
    assert backend.calls == [("when is my bill due", 5)]


def test_invalid_input_empty_query() -> None:
    tool = KnowledgeTool(backend=FakeBackend())
    call = make_call(query="")
    result = run(tool, call)
    assert result.status is contracts.ToolResultStatus.ERROR
    assert result.data is None
    assert result.citations == ()
    assert result.simulation is False
    assert result.error is not None
    assert result.error.code is contracts.ToolErrorCode.INVALID_INPUT
    assert len(result.error.message) <= 500


def test_invalid_input_max_results_out_of_range() -> None:
    tool = KnowledgeTool(backend=FakeBackend())
    for bad in (0, 6):
        result = run(tool, make_call(max_results=bad))
        assert result.status is contracts.ToolResultStatus.ERROR
        assert result.error.code is contracts.ToolErrorCode.INVALID_INPUT


def test_invalid_input_extra_field_rejected() -> None:
    tool = KnowledgeTool(backend=FakeBackend())
    call = contracts.ToolCall(
        call_id=uuid4(),
        name=contracts.ToolName.KNOWLEDGE,
        action=contracts.ToolAction.KNOWLEDGE_SEARCH,
        input={"query": "ok", "unexpected": True},
    )
    result = run(tool, call)
    assert result.status is contracts.ToolResultStatus.ERROR
    assert result.error.code is contracts.ToolErrorCode.INVALID_INPUT


def test_backend_unavailable_maps_to_typed_user_safe_error() -> None:
    tool = KnowledgeTool(
        backend=FakeBackend(
            error=KnowledgeBackendError(
                contracts.ToolErrorCode.UNAVAILABLE,
                "The knowledge service is temporarily unavailable. Please try again shortly.",
            )
        )
    )
    result = run(tool, make_call())
    assert result.status is contracts.ToolResultStatus.ERROR
    assert result.data is None
    assert result.citations == ()
    assert result.simulation is False
    assert result.error.code is contracts.ToolErrorCode.UNAVAILABLE
    assert "key" not in result.error.message.lower()


def test_unexpected_backend_failure_maps_to_internal() -> None:
    tool = KnowledgeTool(backend=FakeBackend(error=RuntimeError("boom secret-42")))
    result = run(tool, make_call())
    assert result.status is contracts.ToolResultStatus.ERROR
    assert result.error.code is contracts.ToolErrorCode.INTERNAL
    assert "secret-42" not in result.error.message
    assert result.data is None


def test_result_passes_frozen_tool_result_validation() -> None:
    """Both success and error shapes satisfy the frozen ToolResult invariants."""
    ok = run(KnowledgeTool(backend=FakeBackend(EVIDENCE)), make_call())
    assert ok.name is contracts.ToolName.KNOWLEDGE and ok.simulation is False
    err = run(
        KnowledgeTool(
            backend=FakeBackend(
                error=KnowledgeBackendError(contracts.ToolErrorCode.UNAVAILABLE, "down")
            )
        ),
        make_call(),
    )
    assert err.data is None and err.error is not None
    assert err.citations == ()
