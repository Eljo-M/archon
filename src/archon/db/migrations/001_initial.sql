BEGIN;
CREATE TABLE IF NOT EXISTS archon_schema_versions (
    version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS archon_runs (
    run_id UUID PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
    request_hash TEXT NOT NULL, issue JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')),
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
    lease_token UUID, lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS archon_events (
    run_id UUID NOT NULL REFERENCES archon_runs(run_id), sequence BIGINT NOT NULL,
    payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, sequence)
);
CREATE TABLE IF NOT EXISTS archon_executions (
    execution_id TEXT PRIMARY KEY, run_id UUID NOT NULL REFERENCES archon_runs(run_id),
    attempt INTEGER NOT NULL CHECK (attempt >= 0), result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS archon_outbox (
    id BIGSERIAL PRIMARY KEY, run_id UUID NOT NULL REFERENCES archon_runs(run_id),
    payload JSONB NOT NULL, published_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS archon_outbox_pending ON archon_outbox(id) WHERE published_at IS NULL;
CREATE INDEX IF NOT EXISTS archon_runs_lease ON archon_runs(lease_expires_at) WHERE status = 'RUNNING';
INSERT INTO archon_schema_versions(version) VALUES (1) ON CONFLICT DO NOTHING;
COMMIT;
