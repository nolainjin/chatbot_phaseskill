-- Email-only authentication and owner-managed registration. Additive migration.
ALTER TABLE maeum.portal_users ADD COLUMN is_registrar boolean NOT NULL DEFAULT false;
CREATE TABLE maeum.email_login_attempts (
 token_hash text PRIMARY KEY, nonce_hash text NOT NULL, csrf text NOT NULL,
 email text NOT NULL, user_id text REFERENCES maeum.portal_users ON DELETE CASCADE,
 auth_version integer, code_mac text, provider_ready boolean NOT NULL DEFAULT false,
 created_at double precision NOT NULL, expires_at double precision NOT NULL,
 attempts integer NOT NULL DEFAULT 0, consumed boolean NOT NULL DEFAULT false
);
CREATE INDEX ON maeum.email_login_attempts(email,created_at);
CREATE TABLE maeum.registration_requests (
 email text PRIMARY KEY, status text NOT NULL DEFAULT 'pending'
 CHECK(status IN ('pending','approved','rejected')),
 requested_at double precision NOT NULL, decided_at double precision,
 decided_by text REFERENCES maeum.portal_users
);
GRANT SELECT,INSERT,UPDATE,DELETE ON maeum.email_login_attempts TO maeum_auth;
GRANT SELECT,INSERT,UPDATE,DELETE ON maeum.registration_requests TO maeum_auth;
GRANT SELECT ON maeum.organizations TO maeum_auth;
REVOKE ALL ON maeum.email_login_attempts,maeum.registration_requests FROM PUBLIC,maeum_portal;

-- The authentication service may check eligibility, without exposing the directory
-- or granting it direct unrestricted access to the tenant membership table.
CREATE FUNCTION maeum.email_login_eligible(target_user text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,maeum AS $$
 SELECT EXISTS(SELECT 1 FROM maeum.portal_users u JOIN maeum.memberships m ON m.user_id=u.id
 JOIN maeum.organizations o ON o.id=m.org_id
 WHERE u.id=target_user AND u.active AND m.active AND o.active);
$$;
CREATE FUNCTION maeum.registrar_valid(actor_session text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,maeum AS $$
 SELECT EXISTS(SELECT 1 FROM maeum.portal_sessions s JOIN maeum.portal_users u ON u.id=s.user_id
 LEFT JOIN maeum.trusted_devices d ON d.id=s.device_id
 WHERE s.token_hash=actor_session AND u.is_registrar AND u.active AND NOT s.revoked
 AND s.state='verified' AND s.auth_version=u.auth_version
 AND s.expires_at>extract(epoch FROM clock_timestamp())
 AND s.seen_at+coalesce(nullif(current_setting('maeum.idle_seconds',true),'')::integer,1800)>extract(epoch FROM clock_timestamp())
 AND (s.device_id IS NULL OR (NOT d.revoked AND d.expires_at>extract(epoch FROM clock_timestamp()))));
$$;
CREATE FUNCTION maeum.register_email(actor_session text, target_email text, target_org text, target_permissions text[])
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,maeum AS $$
DECLARE uid text; actor text;
BEGIN
 IF NOT maeum.registrar_valid(actor_session) THEN RAISE EXCEPTION 'registrar required'; END IF;
 IF target_email<>lower(trim(target_email)) OR length(target_email)>254 OR position('@' IN target_email)<2
 OR NOT target_permissions <@ ARRAY['report:read','raw:read','review:write','link:issue','member:manage','audit:read']::text[]
 OR cardinality(target_permissions)=0 THEN RAISE EXCEPTION 'invalid registration'; END IF;
 IF NOT EXISTS(SELECT 1 FROM maeum.organizations WHERE id=target_org AND active) THEN RAISE EXCEPTION 'organization unavailable'; END IF;
 SELECT user_id INTO actor FROM maeum.portal_sessions WHERE token_hash=actor_session;
 -- A stopped account must be restored separately, never by accepting an application.
 SELECT id INTO uid FROM maeum.portal_users WHERE email=target_email FOR UPDATE;
 IF uid IS NOT NULL AND NOT (SELECT active FROM maeum.portal_users WHERE id=uid) THEN RAISE EXCEPTION 'inactive identity'; END IF;
 IF uid IS NULL THEN
  uid := gen_random_uuid()::text;
  INSERT INTO maeum.portal_users(id,email) VALUES(uid,target_email);
 END IF;
 INSERT INTO maeum.memberships(org_id,user_id,permissions) VALUES(target_org,uid,target_permissions)
 ON CONFLICT(org_id,user_id) DO NOTHING;
 INSERT INTO maeum.registration_requests(email,status,requested_at,decided_at,decided_by)
 VALUES(target_email,'approved',extract(epoch FROM clock_timestamp()),extract(epoch FROM clock_timestamp()),actor)
 ON CONFLICT(email) DO UPDATE SET status='approved',decided_at=excluded.decided_at,decided_by=excluded.decided_by;
 INSERT INTO maeum.audit_events(org_id,actor_id,action,target_hash,outcome)
 VALUES(target_org,actor,'email_preregister',md5(target_email),'allowed');
 RETURN uid;
END $$;
CREATE FUNCTION maeum.email_directory(actor_session text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,maeum AS $$
BEGIN
 IF NOT maeum.registrar_valid(actor_session) THEN RAISE EXCEPTION 'registrar required'; END IF;
 RETURN jsonb_build_object(
  'organizations',coalesce((SELECT jsonb_agg(jsonb_build_object('id',id,'name',name) ORDER BY name) FROM maeum.organizations WHERE active),'[]'::jsonb),
  'requests',coalesce((SELECT jsonb_agg(to_jsonb(r)) FROM (SELECT email,status,requested_at FROM maeum.registration_requests WHERE status='pending' ORDER BY requested_at LIMIT 100) r),'[]'::jsonb),
  'registered',coalesce((SELECT jsonb_agg(to_jsonb(r)) FROM (SELECT u.email,m.org_id,m.permissions,(u.active AND m.active) AS active FROM maeum.portal_users u JOIN maeum.memberships m ON m.user_id=u.id ORDER BY u.email,m.org_id LIMIT 200) r),'[]'::jsonb));
END $$;
REVOKE ALL ON FUNCTION maeum.email_login_eligible(text),maeum.registrar_valid(text),maeum.register_email(text,text,text,text[]),maeum.email_directory(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION maeum.email_login_eligible(text),maeum.registrar_valid(text),maeum.register_email(text,text,text,text[]),maeum.email_directory(text) TO maeum_auth;
