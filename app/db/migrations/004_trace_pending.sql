-- P7: persist audit traces and pending actions across process restart.
-- Retention/archival is intentionally deferred to T3.4; this table is append-only for now.
-- prepared_input/summary/idempotency_key/submission_result/data contain Fernet tokens,
-- never plaintext customer or action payloads.

CREATE TABLE trace_event (
    event_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    tool_slug TEXT,
    action TEXT,
    config_version INTEGER,
    policy TEXT,
    channel TEXT,
    data TEXT NOT NULL,
    UNIQUE (trace_id, sequence)
);

CREATE TABLE pending_action (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    tool_slug TEXT NOT NULL,
    prepare_action TEXT NOT NULL,
    submit_action TEXT NOT NULL,
    prepared_input TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('pending_confirmation', 'confirmed', 'submitted', 'rejected', 'failed')
    ),
    idempotency_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    submission_result TEXT,
    trace_id TEXT NOT NULL
);

CREATE INDEX pending_action_conversation_idx
    ON pending_action (conversation_id);
