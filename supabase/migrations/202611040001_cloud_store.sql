-- Server-only store. This schema is not exposed through the Supabase Data API.
CREATE SCHEMA IF NOT EXISTS maeum;
REVOKE ALL ON SCHEMA maeum FROM PUBLIC, anon, authenticated;

CREATE TABLE IF NOT EXISTS maeum.records (
    kind text NOT NULL,
    record_key text NOT NULL,
    payload jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, record_key)
);
ALTER TABLE maeum.records ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON maeum.records FROM PUBLIC, anon, authenticated;
