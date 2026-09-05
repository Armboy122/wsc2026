"""P7 SQLite state regressions: persistence, ordering, redaction, and reset semantics."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet

from app.agent.main_agent import InvalidActionStateError, MainAgent
from app.agent.operation_policy import OperationSpec
from app.agent.registry import ToolRegistry
from app.agent.stores import PendingActionStore, TraceStore, trace_channel
from app.contracts import (
    PendingAction,
    PendingActionStatus,
    ToolCall,
    ToolErrorCode,
    ToolName,
    ToolResult,
    ToolResultStatus,
    TraceEventKind,
)
from app.db import Database
from app.llm import DemoLLMAdapter, LLMClient
from app.live.scoped_agent import scoped_voice_agent
from app.plugins import load_operation_specs
from app.plugins.oms.declarative_shape import oms_declarative_tool
from app.tools.knowledge_tool import KnowledgeTool


def _db(tmp_path) -> Database:
    db = Database(tmp_path / "p7.db")
    db.migrate()
    return db


def _pending() -> PendingAction:
    now = datetime.now(UTC)
    return PendingAction(
        pending_action_id=uuid4(),
        conversation_id=uuid4(),
        tool_name="write_tool",
        prepare_action="prepare",
        submit_action="submit",
        prepared_input={
            "idempotencyKey": "idem-raw",
            "password": "TOPSECRET",
            "paymentToken": "PAYMENT-TOKEN",
            "chainOfThought": "PRIVATE-COT",
            "payment-token": "HYPHEN-PAYMENT",
            "chain of thought": "SPACED-COT",
            "api-key": "HYPHEN-API-KEY",
            "contactPhone": "0800000000",
            "location": "customer home",
            "description": "no power",
        },
        summary="safe summary",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="idem-raw",
        created_at=now,
        updated_at=now,
    )


def test_trace_and_pending_survive_an_actual_process_restart(tmp_path) -> None:
    db_path = tmp_path / "process-restart.db"
    pending_id = str(uuid4())
    conversation_id = str(uuid4())
    trace_id = str(uuid4())
    child_env = {**os.environ, "PEA_STATE_KEY": Fernet.generate_key().decode()}
    project_root = Path(__file__).resolve().parents[1]
    writer = textwrap.dedent(
        """
        import asyncio
        import sys
        from datetime import UTC, datetime
        from uuid import UUID

        from app.agent.stores import PendingActionStore, TraceStore
        from app.contracts import PendingAction, PendingActionStatus, TraceEventKind
        from app.db import Database

        async def main():
            db = Database(sys.argv[1])
            db.migrate()
            now = datetime.now(UTC)
            action = PendingAction(
                pendingActionId=UUID(sys.argv[2]),
                conversationId=UUID(sys.argv[3]),
                toolSlug="write_tool",
                prepareAction="prepare",
                submitAction="submit",
                preparedInput={"description": "[redacted]"},
                summary="safe summary",
                status=PendingActionStatus.PENDING_CONFIRMATION,
                idempotencyKey="restart-key",
                createdAt=now,
                updatedAt=now,
            )
            trace_id = UUID(sys.argv[4])
            await TraceStore(db).append(
                trace_id, TraceEventKind.CHAT_RECEIVED, {"message": "safe"}
            )
            await PendingActionStore(db).put(
                action,
                trace_id,
                execution_input={"description": "outage", "idempotencyKey": "restart-key"},
            )
            db.close()

        asyncio.run(main())
        """
    )
    reader = textwrap.dedent(
        """
        import json
        import sys
        from uuid import UUID

        from app.agent.stores import PendingActionStore, TraceStore
        from app.db import Database

        db = Database(sys.argv[1])
        db.migrate()
        action = PendingActionStore(db).get(UUID(sys.argv[2]))
        trace = TraceStore(db).get(UUID(sys.argv[3]))
        print(json.dumps({
            "status": action.status.value if action else None,
            "idempotencyKey": action.idempotency_key if action else None,
            "traceKinds": [event.kind.value for event in trace.events] if trace else [],
        }))
        db.close()
        """
    )

    subprocess.run(
        [sys.executable, "-c", writer, str(db_path), pending_id, conversation_id, trace_id],
        cwd=project_root,
        env=child_env,
        capture_output=True,
        text=True,
        check=True,
    )
    read_result = subprocess.run(
        [sys.executable, "-c", reader, str(db_path), pending_id, trace_id],
        cwd=project_root,
        env=child_env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert json.loads(read_result.stdout) == {
        "status": "pending_confirmation",
        "idempotencyKey": "restart-key",
        "traceKinds": ["chat_received"],
    }


def test_file_backed_state_fails_closed_without_a_durable_key(tmp_path) -> None:
    db_path = tmp_path / "missing-key.db"
    child_env = dict(os.environ)
    child_env.pop("PEA_STATE_KEY", None)
    project_root = Path(__file__).resolve().parents[1]
    bootstrap = textwrap.dedent(
        """
        import sys
        from app.db import Database

        db = Database(sys.argv[1])
        db.migrate()
        db.close()
        """
    )
    reopen = textwrap.dedent(
        """
        import sys
        from app.agent.stores import PendingActionStore
        from app.db import Database

        db = Database(sys.argv[1])
        db.migrate()
        PendingActionStore(db)
        """
    )

    subprocess.run(
        [sys.executable, "-c", bootstrap, str(db_path)],
        cwd=project_root,
        env=child_env,
        capture_output=True,
        text=True,
        check=True,
    )
    result = subprocess.run(
        [sys.executable, "-c", reopen, str(db_path)],
        cwd=project_root,
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "PEA_STATE_KEY is required for file-backed state" in result.stderr


def _race_action() -> PendingAction:
    now = datetime.now(UTC)
    return PendingAction(
        pending_action_id=uuid4(),
        conversation_id=uuid4(),
        tool_slug="race_tool",
        prepare_action="prepare_write",
        submit_action="submit_write",
        prepared_input={"description": "[redacted]"},
        summary="safe",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="race-key",
        created_at=now,
        updated_at=now,
    )


def _race_registry(
    submit_keys: list[str],
    *,
    submit_started: asyncio.Event | None = None,
    release_submit: asyncio.Event | None = None,
) -> ToolRegistry:
    class RaceTool:
        name = "race_tool"
        actions = frozenset({"prepare_write", "submit_write"})

        def reset(self) -> None:
            return None

        async def execute(self, call, context):
            del context
            if call.action == "submit_write":
                submit_keys.append(call.input["idempotencyKey"])
                if submit_started is not None:
                    submit_started.set()
                if release_submit is not None:
                    await release_submit.wait()
                else:
                    await asyncio.sleep(0)
            return ToolResult(
                call_id=call.call_id,
                name=call.name,
                action=call.action,
                status=ToolResultStatus.SUCCESS,
                data={"accepted": True},
                simulation=True,
            )

    return ToolRegistry(
        [
            KnowledgeTool(type("Backend", (), {"search": lambda self, query, max_results: None})()),
            RaceTool(),
        ],
        operation_specs={
            ("race_tool", "prepare_write"): OperationSpec(mode="prepare"),
            ("race_tool", "submit_write"): OperationSpec(mode="submit", exposure="internal"),
        },
    )


@pytest.mark.asyncio
async def test_trace_store_persists_redacted_metadata_and_stable_sequence(tmp_path) -> None:
    db = _db(tmp_path)
    trace_id = uuid4()
    try:
        store = TraceStore(db)
        events = await asyncio.gather(
            *(
                store.append(
                    trace_id,
                    TraceEventKind.TOOL_RESULT,
                    {
                        "name": "write_tool",
                        "action": "read",
                        "password": "TOPSECRET",
                        "chainOfThought": "private reasoning",
                        "api-key": "trace-api-secret",
                        "chain-of-thought": "trace-private-reasoning",
                        "index": index,
                    },
                )
                for index in range(5)
            )
        )
        assert [event.sequence for event in store.get(trace_id).events] == [1, 2, 3, 4, 5]
        assert {event.sequence for event in events} == {1, 2, 3, 4, 5}
        row = await db.fetch_one("SELECT * FROM trace_event WHERE trace_id = ?", (str(trace_id),))
        assert row is not None
        assert row["tool_slug"] == "write_tool"
        assert row["action"] == "read"
        assert "TOPSECRET" not in row["data"]
        assert "private reasoning" not in row["data"]
    finally:
        db.close()

    reopened_db = _db(tmp_path)
    try:
        reopened = TraceStore(reopened_db).get(trace_id)
        assert reopened is not None
        assert [event.sequence for event in reopened.events] == [1, 2, 3, 4, 5]
        assert all("TOPSECRET" not in str(event.data) for event in reopened.events)
        assert all(event.data["api-key"] == "[redacted]" for event in reopened.events)
        assert all(
            event.data["chain-of-thought"] == "[redacted]" for event in reopened.events
        )
    finally:
        reopened_db.close()

    db_bytes = (tmp_path / "p7.db").read_bytes()
    for marker in (
        b"TOPSECRET",
        b"PAYMENT-TOKEN",
        b"PRIVATE-COT",
        b"HYPHEN-PAYMENT",
        b"SPACED-COT",
        b"HYPHEN-API-KEY",
        b"trace-api-secret",
        b"trace-private-reasoning",
        b"private reasoning",
        b"idem-raw",
        b"0800000000",
        b"customer home",
        b"no power",
    ):
        assert marker not in db_bytes


@pytest.mark.asyncio
async def test_trace_event_optional_metadata_roundtrips(tmp_path) -> None:
    db = _db(tmp_path)
    trace_id = uuid4()
    try:
        event = await TraceStore(db).append(
            trace_id,
            TraceEventKind.TOOL_CALLED,
            {"name": "tool", "action": "read"},
            config_version=7,
            policy="plain_read",
            channel="web",
        )
        assert (event.tool_slug, event.action, event.config_version, event.policy, event.channel) == (
            "tool", "read", 7, "plain_read", "web"
        )
    finally:
        db.close()
    reopened_db = _db(tmp_path)
    try:
        event = TraceStore(reopened_db).get(trace_id).events[0]
        assert event.config_version == 7 and event.policy == "plain_read" and event.channel == "web"
    finally:
        reopened_db.close()


@pytest.mark.asyncio
async def test_trace_channel_context_is_applied_and_reset(tmp_path) -> None:
    db = _db(tmp_path)
    store = TraceStore(db)
    trace_id = uuid4()
    first_pending_id = uuid4()
    try:
        with trace_channel("line"):
            line_event = await store.append(
                trace_id, TraceEventKind.CHAT_RECEIVED, {"message": "safe"}
            )
        context_free_event = await store.append(
            trace_id, TraceEventKind.LLM_RESPONDED, {"status": "ok"}
        )
        await store.append(
            trace_id,
            TraceEventKind.ACTION_CONFIRMED,
            {"pendingActionId": str(first_pending_id)},
        )

        assert line_event.channel == "line"
        assert context_free_event.channel is None
        assert [event.channel for event in store.get(trace_id).events] == ["line", None, None]
        assert store.has_kind(
            trace_id,
            TraceEventKind.ACTION_CONFIRMED,
            pending_action_id=first_pending_id,
        )
        assert not store.has_kind(
            trace_id,
            TraceEventKind.ACTION_CONFIRMED,
            pending_action_id=uuid4(),
        )
    finally:
        db.close()


@pytest.mark.asyncio
async def test_pending_store_roundtrips_raw_idempotency_and_terminal_state(tmp_path) -> None:
    db = _db(tmp_path)
    action = _pending()
    trace_id = uuid4()
    try:
        store = PendingActionStore(db)
        await store.put(action, trace_id)
        row = await db.fetch_one("SELECT * FROM pending_action WHERE id = ?", (str(action.pending_action_id),))
        assert row is not None
        assert row["idempotency_key"] != "idem-raw"
        assert "idem-raw" not in row["idempotency_key"]
        assert "TOPSECRET" not in row["prepared_input"]
        stored = json.loads(
            db.state_cipher().decrypt(row["prepared_input"].encode()).decode()
        )
        persisted_text = json.dumps(stored).lower()
        for forbidden in (
            "password",
            "topsecret",
            "paymenttoken",
            "payment-token",
            "chainofthought",
            "private-cot",
            "payment-token",
            "hyphen-payment",
            "chain of thought",
            "spaced-cot",
            "api-key",
            "hyphen-api-key",
        ):
            assert forbidden not in persisted_text
        assert store.get(action.pending_action_id).model_dump(by_alias=True)["idempotencyKey"] == "[redacted]"
        result = ToolResult(
            call_id=uuid4(),
            name="write_tool",
            action="submit",
            status=ToolResultStatus.SUCCESS,
            data={
                "accepted": True,
                "api-key": "submission-secret",
                "chain of thought": "submission-reasoning",
            },
            simulation=True,
        )
        terminal = action.model_copy(
            update={"status": PendingActionStatus.SUBMITTED, "submission_result": result, "updated_at": datetime.now(UTC)}
        )
        await store.update(terminal)
        terminal_row = await db.fetch_one(
            "SELECT submission_result FROM pending_action WHERE id = ?",
            (str(action.pending_action_id),),
        )
        decrypted_result = db.state_cipher().decrypt(
            terminal_row["submission_result"].encode()
        ).decode()
        assert "submission-secret" not in decrypted_result
        assert "submission-reasoning" not in decrypted_result
    finally:
        db.close()

    reopened_db = _db(tmp_path)
    try:
        reopened = PendingActionStore(reopened_db).get(action.pending_action_id)
        assert reopened is not None
        assert reopened.status is PendingActionStatus.SUBMITTED
        assert reopened.submission_result is not None
        assert reopened.idempotency_key == "idem-raw"
        await PendingActionStore(reopened_db).clear()
        retained = await reopened_db.fetch_one("SELECT status FROM pending_action WHERE id = ?", (str(action.pending_action_id),))
        assert retained is not None and retained["status"] == "submitted"
    finally:
        reopened_db.close()


@pytest.mark.asyncio
async def test_existing_encrypted_state_fails_closed_with_wrong_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PEA_STATE_KEY", Fernet.generate_key().decode())
    db = _db(tmp_path)
    try:
        await PendingActionStore(db).put(_pending(), uuid4())
    finally:
        db.close()
    assert not (tmp_path / "p7.db.key").exists()
    monkeypatch.setenv("PEA_STATE_KEY", Fernet.generate_key().decode())
    reopened = Database(tmp_path / "p7.db")
    try:
        reopened.migrate()
        with pytest.raises(RuntimeError, match="persisted state"):
            PendingActionStore(reopened)
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_confirmation_claim_has_one_owner_for_concurrent_callers(tmp_path) -> None:
    db = _db(tmp_path)
    action = _pending()
    try:
        store = PendingActionStore(db)
        await store.put(action, uuid4())
        confirmed = action.model_copy(update={"status": PendingActionStatus.CONFIRMED})
        claims = await asyncio.gather(
            store.claim_confirmation(confirmed, PendingActionStatus.PENDING_CONFIRMATION),
            store.claim_confirmation(confirmed, PendingActionStatus.PENDING_CONFIRMATION),
        )
        assert sum(owner for owner, _ in claims) == 1
        event = next(event for owner, event in claims if not owner)
        assert event is not None
        store.finish_confirmation(action.pending_action_id)
        await asyncio.wait_for(event.wait(), timeout=1)
        row = await db.fetch_one("SELECT status FROM pending_action WHERE id = ?", (str(action.pending_action_id),))
        assert row is not None and row["status"] == "confirmed"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_concurrent_confirms_submit_once_through_sqlite_agent_path(tmp_path) -> None:
    db = _db(tmp_path)
    action = _race_action()
    trace_id = uuid4()
    submit_keys: list[str] = []
    try:
        pending = PendingActionStore(db)
        traces = TraceStore(db)
        await pending.put(
            action,
            trace_id,
            execution_input={"description": "customer detail", "idempotencyKey": "race-key"},
        )
        agent_a = MainAgent(
            LLMClient(DemoLLMAdapter(())),
            _race_registry(submit_keys),
            pending_actions=pending,
            traces=traces,
        )
        agent_b = MainAgent(
            LLMClient(DemoLLMAdapter(())),
            _race_registry(submit_keys),
            pending_actions=pending,
            traces=traces,
        )

        first, second = await asyncio.gather(
            agent_a.confirm_pending_action(action.pending_action_id),
            agent_b.confirm_pending_action(action.pending_action_id),
        )

        assert first.pending_action.status is PendingActionStatus.SUBMITTED
        assert second.pending_action.status is PendingActionStatus.SUBMITTED
        assert submit_keys == ["race-key"]
        events = traces.get(trace_id).events
        kinds = [event.kind for event in events]
        assert kinds.count(TraceEventKind.ACTION_CONFIRMED) == 1
        assert kinds.count(TraceEventKind.ACTION_SUBMITTED) == 1
        assert all(
            event.policy == "plain_read"
            for event in events
            if event.kind in {TraceEventKind.TOOL_CALLED, TraceEventKind.TOOL_RESULT}
        )
    finally:
        db.close()


@pytest.mark.asyncio
async def test_concurrent_confirm_and_reject_have_one_terminal_winner(tmp_path) -> None:
    db = _db(tmp_path)
    action = _race_action()
    trace_id = uuid4()
    submit_keys: list[str] = []
    try:
        pending = PendingActionStore(db)
        traces = TraceStore(db)
        await pending.put(
            action,
            trace_id,
            execution_input={"description": "customer detail", "idempotencyKey": "race-key"},
        )
        agent = MainAgent(
            LLMClient(DemoLLMAdapter(())),
            _race_registry(submit_keys),
            pending_actions=pending,
            traces=traces,
        )

        outcomes = await asyncio.gather(
            agent.confirm_pending_action(action.pending_action_id),
            agent.reject_pending_action(action.pending_action_id, "cancel"),
            return_exceptions=True,
        )

        assert sum(isinstance(item, InvalidActionStateError) for item in outcomes) == 1
        terminal = pending.get(action.pending_action_id)
        assert terminal is not None
        assert terminal.status in {PendingActionStatus.SUBMITTED, PendingActionStatus.REJECTED}
        kinds = [event.kind for event in traces.get(trace_id).events]
        if terminal.status is PendingActionStatus.SUBMITTED:
            assert submit_keys == ["race-key"]
            assert TraceEventKind.ACTION_REJECTED not in kinds
            assert kinds.count(TraceEventKind.ACTION_SUBMITTED) == 1
        else:
            assert submit_keys == []
            assert TraceEventKind.ACTION_SUBMITTED not in kinds
            assert kinds.count(TraceEventKind.ACTION_REJECTED) == 1
    finally:
        db.close()


@pytest.mark.asyncio
async def test_reset_drains_confirmation_owned_by_scoped_agent(tmp_path) -> None:
    db = _db(tmp_path)
    action = _race_action()
    trace_id = uuid4()
    submit_keys: list[str] = []
    submit_started = asyncio.Event()
    release_submit = asyncio.Event()
    try:
        pending = PendingActionStore(db)
        traces = TraceStore(db)
        await pending.put(
            action,
            trace_id,
            execution_input={"description": "customer detail", "idempotencyKey": "race-key"},
        )
        full = MainAgent(
            LLMClient(DemoLLMAdapter(())),
            _race_registry(
                submit_keys,
                submit_started=submit_started,
                release_submit=release_submit,
            ),
            pending_actions=pending,
            traces=traces,
        )
        scoped = scoped_voice_agent(
            full,
            allowed=frozenset({ToolName.KNOWLEDGE, "race_tool"}),
        )

        confirmation = asyncio.create_task(
            scoped.confirm_pending_action(action.pending_action_id)
        )
        await asyncio.wait_for(submit_started.wait(), timeout=1)
        reset = asyncio.create_task(full.reset_demo())
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(reset), timeout=0.05)

        release_submit.set()
        decision, reset_result = await asyncio.gather(confirmation, reset)
        assert decision.pending_action.status is PendingActionStatus.SUBMITTED
        assert reset_result.reset is True
        assert submit_keys == ["race-key"]
        assert pending.get(action.pending_action_id).status is PendingActionStatus.SUBMITTED
        row = await db.fetch_one(
            "SELECT status FROM pending_action WHERE id = ?",
            (str(action.pending_action_id),),
        )
        assert row is not None and row["status"] == "submitted"
    finally:
        release_submit.set()
        db.close()


@pytest.mark.asyncio
async def test_failed_confirmation_audit_claim_is_recoverable(tmp_path) -> None:
    db = _db(tmp_path)
    action = _race_action()
    trace_id = uuid4()
    submit_keys: list[str] = []
    traces = TraceStore(db)
    pending = PendingActionStore(db)
    await pending.put(
        action,
        trace_id,
        execution_input={"description": "customer detail", "idempotencyKey": "race-key"},
    )
    original_append = traces.append

    async def fail_confirmation_audit(trace, kind, data=None, **kwargs):
        if kind is TraceEventKind.ACTION_CONFIRMED:
            raise RuntimeError("audit unavailable")
        return await original_append(trace, kind, data, **kwargs)

    traces.append = fail_confirmation_audit
    try:
        agent = MainAgent(
            LLMClient(DemoLLMAdapter(())), _race_registry(submit_keys),
            pending_actions=pending, traces=traces,
        )
        with pytest.raises(RuntimeError, match="audit unavailable"):
            await agent.confirm_pending_action(action.pending_action_id)
        assert pending.get(action.pending_action_id).status is PendingActionStatus.CONFIRMED
        traces.append = original_append
        response = await agent.confirm_pending_action(action.pending_action_id)
        assert response.pending_action.status is PendingActionStatus.SUBMITTED
        assert submit_keys == ["race-key"]
        kinds = [event.kind for event in traces.get(trace_id).events]
        assert kinds.count(TraceEventKind.ACTION_CONFIRMED) == 1
    finally:
        db.close()


@pytest.mark.asyncio
async def test_disabled_dispatch_emits_tool_disabled_trace_metadata(tmp_path) -> None:
    db = _db(tmp_path)
    trace_id = uuid4()
    registry = _race_registry([])
    registry.set_code_tool_enabled("race_tool", False)
    try:
        traces = TraceStore(db)
        agent = MainAgent(
            LLMClient(DemoLLMAdapter(())),
            registry,
            pending_actions=PendingActionStore(db),
            traces=traces,
        )
        call = ToolCall(
            call_id=uuid4(),
            name="race_tool",
            action="prepare_write",
            input={"idempotencyKey": "race-key"},
        )

        result = await agent._execute_internal(  # noqa: SLF001 - test the trace boundary
            call, uuid4(), trace_id
        )

        assert result.error is not None
        assert result.error.code is ToolErrorCode.UNAVAILABLE
        disabled = next(
            event
            for event in traces.get(trace_id).events
            if event.kind is TraceEventKind.TOOL_DISABLED
        )
        assert disabled.tool_slug == "race_tool"
        assert disabled.action == "prepare_write"
        assert disabled.policy == "plain_read"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_trace_cancellation_finishes_worker_and_keeps_sqlite_and_ram_aligned(
    tmp_path, monkeypatch
) -> None:
    db = _db(tmp_path)
    started = threading.Event()
    release = threading.Event()
    original_transaction = db._run_in_transaction_sync

    def slow_transaction(fn):
        started.set()
        assert release.wait(2)
        return original_transaction(fn)

    try:
        monkeypatch.setattr(db, "_run_in_transaction_sync", slow_transaction)
        store = TraceStore(db)
        trace_id = uuid4()
        task = asyncio.create_task(
            store.append(trace_id, TraceEventKind.ERROR, {"stage": "cancel-probe"})
        )
        await asyncio.to_thread(started.wait, 2)
        task.cancel()
        # Give cancellation enough loop turns to propagate. The outer task must stay
        # pending until the thread exits; otherwise the lock can be released early.
        for _ in range(10):
            await asyncio.sleep(0)
        assert not task.done()
        assert db._write_lock.locked()
        release.set()
        event = await task
        assert event.sequence == 1
        assert [item.sequence for item in store.get(trace_id).events] == [1]
        rows = await db.fetch_all(
            "SELECT sequence FROM trace_event WHERE trace_id = ? ORDER BY sequence",
            (str(trace_id),),
        )
        assert [row["sequence"] for row in rows] == [1]
    finally:
        release.set()
        db.close()


@pytest.mark.asyncio
async def test_pending_cas_cancellation_keeps_sqlite_and_ram_aligned(
    tmp_path, monkeypatch
) -> None:
    db = _db(tmp_path)
    store = PendingActionStore(db)
    action = _pending()
    await store.put(action, uuid4())
    confirmed = action.model_copy(update={"status": PendingActionStatus.CONFIRMED})
    started = threading.Event()
    release = threading.Event()
    original_transaction = db._run_in_transaction_sync

    def slow_transaction(fn):
        started.set()
        assert release.wait(2)
        return original_transaction(fn)

    try:
        monkeypatch.setattr(db, "_run_in_transaction_sync", slow_transaction)
        task = asyncio.create_task(
            store.compare_and_set(confirmed, PendingActionStatus.PENDING_CONFIRMATION)
        )
        await asyncio.to_thread(started.wait, 2)
        task.cancel()
        for _ in range(10):
            await asyncio.sleep(0)
        assert not task.done()
        assert db._write_lock.locked()
        release.set()
        assert await task is True
        assert store.get(action.pending_action_id).status is PendingActionStatus.CONFIRMED
        row = await db.fetch_one(
            "SELECT status FROM pending_action WHERE id = ?",
            (str(action.pending_action_id),),
        )
        assert row is not None and row["status"] == "confirmed"
    finally:
        release.set()
        db.close()


@pytest.mark.asyncio
async def test_confirm_replays_declarative_prepare_after_restart_and_is_idempotent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PEA_STATE_KEY", Fernet.generate_key().decode())
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(201, json={"reportId": "R-1", "status": "RECEIVED", "message": "ok", "location": None})

    def make_registry() -> ToolRegistry:
        return ToolRegistry(
            [
                KnowledgeTool(type("Backend", (), {"search": lambda self, query, max_results: None})()),
                oms_declarative_tool(
                    "http://oms.test/api/v1/oms",
                    transport=httpx.MockTransport(handler),
                ),
            ],
            operation_specs=load_operation_specs(ToolName.OMS),
        )

    action = PendingAction(
        pending_action_id=uuid4(),
        conversation_id=uuid4(),
        tool_slug="oms_tool",
        prepare_action="prepare_anonymous_outage",
        submit_action="submit_anonymous_outage",
        prepared_input={"description": "[redacted]"},
        summary="รายการแจ้งเหตุไฟฟ้าขัดข้อง",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="idem-restart",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    raw_input = {
        "description": "no power",
        "location": "customer home",
        "contactPhone": "0800000000",
        "idempotencyKey": "idem-restart",
    }
    db = _db(tmp_path)
    try:
        store = PendingActionStore(db)
        trace_id = uuid4()
        await store.put(action, trace_id, execution_input=raw_input)
        # Simulate a crash after the durable confirmation transition but before dispatch.
        assert await store.compare_and_set(
            action.model_copy(update={"status": PendingActionStatus.CONFIRMED}),
            PendingActionStatus.PENDING_CONFIRMATION,
        )
    finally:
        db.close()

    restarted_db = _db(tmp_path)
    try:
        agent = MainAgent(
            LLMClient(DemoLLMAdapter(())),
            make_registry(),
            pending_actions=PendingActionStore(restarted_db),
            traces=TraceStore(restarted_db),
        )
        first = await agent.confirm_pending_action(action.pending_action_id)
        second = await agent.confirm_pending_action(action.pending_action_id)
        assert first.pending_action.status is PendingActionStatus.SUBMITTED
        assert second.pending_action.status is PendingActionStatus.SUBMITTED
        assert calls == 1
    finally:
        restarted_db.close()


@pytest.mark.asyncio
async def test_declarative_retry_after_terminal_failure_uses_downstream_idempotency(
    tmp_path, monkeypatch
) -> None:
    request_keys: list[str] = []
    downstream_effects: set[str] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.headers["Idempotency-Key"]
        request_keys.append(key)
        if key not in downstream_effects:
            downstream_effects.add(key)
        return httpx.Response(
            201,
            json={"reportId": "R-1", "status": "RECEIVED", "message": "ok", "location": None},
        )

    def make_registry() -> ToolRegistry:
        return ToolRegistry(
            [
                KnowledgeTool(type("Backend", (), {"search": lambda self, query, max_results: None})()),
                oms_declarative_tool("http://oms.test/api/v1/oms", transport=httpx.MockTransport(handler)),
            ],
            operation_specs=load_operation_specs(ToolName.OMS),
        )

    action = PendingAction(
        pending_action_id=uuid4(),
        conversation_id=uuid4(),
        tool_slug="oms_tool",
        prepare_action="prepare_anonymous_outage",
        submit_action="submit_anonymous_outage",
        prepared_input={"description": "[redacted]"},
        summary="รายการแจ้งเหตุไฟฟ้าขัดข้อง",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="idem-downstream",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    raw_input = {
        "description": "no power",
        "location": "customer home",
        "contactPhone": "0800000000",
        "idempotencyKey": "idem-downstream",
    }
    monkeypatch.setenv("PEA_STATE_KEY", Fernet.generate_key().decode())
    db = _db(tmp_path)
    store = PendingActionStore(db)
    await store.put(action, uuid4(), execution_input=raw_input)
    original_update = store.update
    failed_once = True

    async def fail_terminal_persist(updated):
        nonlocal failed_once
        if failed_once and updated.status is PendingActionStatus.SUBMITTED:
            failed_once = False
            raise RuntimeError("terminal persistence failure")
        await original_update(updated)

    store.update = fail_terminal_persist
    try:
        agent = MainAgent(
            LLMClient(DemoLLMAdapter(())), make_registry(),
            pending_actions=store, traces=TraceStore(db),
        )
        with pytest.raises(RuntimeError, match="terminal persistence"):
            await agent.confirm_pending_action(action.pending_action_id)
    finally:
        db.close()

    retry_db = _db(tmp_path)
    try:
        retry_agent = MainAgent(
            LLMClient(DemoLLMAdapter(())), make_registry(),
            pending_actions=PendingActionStore(retry_db), traces=TraceStore(retry_db),
        )
        response = await retry_agent.confirm_pending_action(action.pending_action_id)
        assert response.pending_action.status is PendingActionStatus.SUBMITTED
        assert request_keys == ["idem-downstream", "idem-downstream"]
        assert downstream_effects == {"idem-downstream"}
    finally:
        retry_db.close()


@pytest.mark.asyncio
async def test_retry_after_terminal_persist_failure_reuses_idempotency_key(tmp_path, monkeypatch) -> None:
    effects: set[str] = set()
    monkeypatch.setenv("PEA_STATE_KEY", Fernet.generate_key().decode())
    attempts: list[str] = []

    class IdempotentTool:
        name = "idempotent_tool"
        actions = frozenset({"prepare_write", "submit_write"})

        def reset(self) -> None:
            return None

        async def execute(self, call, context):
            del context
            if call.action == "submit_write":
                key = call.input["idempotencyKey"]
                attempts.append(key)
                effects.add(key)
            return ToolResult(
                call_id=call.call_id,
                name=call.name,
                action=call.action,
                status=ToolResultStatus.SUCCESS,
                data={"accepted": True},
                simulation=True,
            )

    def registry() -> ToolRegistry:
        return ToolRegistry(
            [
                KnowledgeTool(type("Backend", (), {"search": lambda self, query, max_results: None})()),
                IdempotentTool(),
            ],
            operation_specs={
                ("idempotent_tool", "prepare_write"): OperationSpec(mode="prepare"),
                ("idempotent_tool", "submit_write"): OperationSpec(mode="submit", exposure="internal"),
            },
        )

    action = PendingAction(
        pending_action_id=uuid4(),
        conversation_id=uuid4(),
        tool_slug="idempotent_tool",
        prepare_action="prepare_write",
        submit_action="submit_write",
        prepared_input={"description": "[redacted]"},
        summary="safe",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="same-key",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    raw_input = {"description": "customer detail", "idempotencyKey": "same-key"}
    db = _db(tmp_path)
    try:
        await PendingActionStore(db).put(action, uuid4(), execution_input=raw_input)
    finally:
        db.close()

    restarted_db = _db(tmp_path)
    store = PendingActionStore(restarted_db)
    original_update = store.update
    failed_once = True

    async def fail_terminal_persist(updated):
        nonlocal failed_once
        if failed_once and updated.status is PendingActionStatus.SUBMITTED:
            failed_once = False
            raise RuntimeError("simulated terminal persistence failure")
        await original_update(updated)

    monkeypatch.setattr(store, "update", fail_terminal_persist)
    try:
        agent = MainAgent(
            LLMClient(DemoLLMAdapter(())),
            registry(),
            pending_actions=store,
            traces=TraceStore(restarted_db),
        )
        with pytest.raises(RuntimeError, match="terminal persistence"):
            await agent.confirm_pending_action(action.pending_action_id)
        assert effects == {"same-key"}
        assert attempts == ["same-key"]
    finally:
        restarted_db.close()

    retry_db = _db(tmp_path)
    try:
        retry_agent = MainAgent(
            LLMClient(DemoLLMAdapter(())),
            registry(),
            pending_actions=PendingActionStore(retry_db),
            traces=TraceStore(retry_db),
        )
        response = await retry_agent.confirm_pending_action(action.pending_action_id)
        assert response.pending_action.status is PendingActionStatus.SUBMITTED
        assert effects == {"same-key"}
        assert attempts == ["same-key", "same-key"]
    finally:
        retry_db.close()


@pytest.mark.asyncio
async def test_pending_store_reset_leaves_no_nonterminal_rows(tmp_path) -> None:
    db = _db(tmp_path)
    pending = _pending()
    confirmed = _pending().model_copy(update={"status": PendingActionStatus.CONFIRMED})
    terminal = _pending().model_copy(update={"status": PendingActionStatus.REJECTED})
    try:
        store = PendingActionStore(db)
        await store.put(pending, uuid4())
        await store.put(confirmed, uuid4())
        await store.put(terminal, uuid4())
        await store.clear()
        assert store.get(pending.pending_action_id) is None
        assert store.get(confirmed.pending_action_id).status is PendingActionStatus.FAILED
        assert store.get(terminal.pending_action_id) is not None
        rows = await db.fetch_all(
            "SELECT status FROM pending_action WHERE status IN (?, ?)",
            ("pending_confirmation", "confirmed"),
        )
        assert rows == []
    finally:
        db.close()


def test_trace_store_clear_is_append_only(tmp_path) -> None:
    db = _db(tmp_path)
    try:
        store = TraceStore(db)
        trace_id = uuid4()
        asyncio.run(store.append(trace_id, TraceEventKind.CHAT_RECEIVED, {"message": "safe"}))
        asyncio.run(store.clear())
        assert store.get(trace_id) is not None
        assert db._conn.execute("SELECT COUNT(*) FROM trace_event").fetchone()[0] == 1
    finally:
        db.close()


@pytest.mark.asyncio
async def test_new_agent_returns_persisted_terminal_action_without_reexecuting(tmp_path) -> None:
    db = _db(tmp_path)
    action = _pending()
    result = ToolResult(
        call_id=uuid4(),
        name="write_tool",
        action="submit",
        status=ToolResultStatus.SUCCESS,
        data={"accepted": True},
        simulation=True,
    )
    terminal = action.model_copy(
        update={"status": PendingActionStatus.SUBMITTED, "submission_result": result}
    )
    trace_id = uuid4()
    try:
        await PendingActionStore(db).put(terminal, trace_id)
    finally:
        db.close()

    restarted_db = _db(tmp_path)
    try:
        knowledge = KnowledgeTool(
            type("Backend", (), {"search": lambda self, query, max_results: None})()
        )
        # The terminal branch must return before dispatch, so a minimal registry is sufficient.
        agent = MainAgent(
            LLMClient(DemoLLMAdapter(())),
            ToolRegistry([knowledge]),
            pending_actions=PendingActionStore(restarted_db),
            traces=TraceStore(restarted_db),
        )
        response = await agent.confirm_pending_action(action.pending_action_id)
        assert response.pending_action.status is PendingActionStatus.SUBMITTED
        assert response.tool_result is not None
        assert response.tool_result.data == {"accepted": True}
    finally:
        restarted_db.close()


@pytest.mark.asyncio
async def test_rejected_action_remains_forbidden_after_restart(tmp_path) -> None:
    db = _db(tmp_path)
    action = _pending()
    rejected = action.model_copy(update={"status": PendingActionStatus.REJECTED})
    try:
        await PendingActionStore(db).put(rejected, uuid4())
    finally:
        db.close()
    restarted_db = _db(tmp_path)
    try:
        agent = MainAgent(
            LLMClient(DemoLLMAdapter(())),
            ToolRegistry([KnowledgeTool(type("Backend", (), {"search": lambda self, query, max_results: None})())]),
            pending_actions=PendingActionStore(restarted_db),
            traces=TraceStore(restarted_db),
        )
        with pytest.raises(InvalidActionStateError):
            await agent.confirm_pending_action(action.pending_action_id)
    finally:
        restarted_db.close()
