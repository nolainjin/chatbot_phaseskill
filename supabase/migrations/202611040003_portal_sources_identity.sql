CREATE TABLE maeum.email_changes (id text PRIMARY KEY, user_id text NOT NULL REFERENCES maeum.portal_users, new_email text NOT NULL, token_hash text UNIQUE NOT NULL, expires_at double precision NOT NULL, consumed boolean NOT NULL DEFAULT false);
GRANT SELECT,INSERT,UPDATE ON maeum.email_changes TO maeum_portal;
ALTER TABLE maeum.report_snapshots ADD COLUMN sources jsonb NOT NULL DEFAULT '{}';
