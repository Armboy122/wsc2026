-- P8: Public API keys are independently revocable and store only a one-way digest.
CREATE TABLE api_key (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL DEFAULT 'default' CHECK (tenant_id = 'default'),
    created_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE INDEX api_key_active_hash_idx ON api_key (key_hash, revoked_at);
