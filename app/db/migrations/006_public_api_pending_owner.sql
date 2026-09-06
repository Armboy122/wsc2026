-- P8: preserve API-key ownership for durable pending actions across restarts.
ALTER TABLE pending_action ADD COLUMN api_key_id TEXT REFERENCES api_key(id);

CREATE INDEX pending_action_api_key_idx
    ON pending_action (api_key_id);
