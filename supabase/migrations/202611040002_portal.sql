-- Additive candidate for isolated local DB only; no startup migrations.
CREATE TABLE maeum.organizations (id text PRIMARY KEY, name text NOT NULL, active boolean NOT NULL DEFAULT true);
CREATE TABLE maeum.portal_users (id text PRIMARY KEY, email text UNIQUE NOT NULL, password_hash text, active boolean NOT NULL DEFAULT true, auth_version integer NOT NULL DEFAULT 1);
CREATE TABLE maeum.memberships (org_id text REFERENCES maeum.organizations, user_id text REFERENCES maeum.portal_users, permissions text[] NOT NULL, active boolean NOT NULL DEFAULT true, PRIMARY KEY(org_id,user_id));
CREATE TABLE maeum.trusted_devices (id text PRIMARY KEY, user_id text REFERENCES maeum.portal_users, token_hash text UNIQUE NOT NULL, expires_at double precision NOT NULL, revoked boolean NOT NULL DEFAULT false, created_at double precision NOT NULL);
CREATE TABLE maeum.portal_sessions (token_hash text PRIMARY KEY, user_id text REFERENCES maeum.portal_users, auth_version integer NOT NULL, state text NOT NULL CHECK(state IN ('pending_device','verified')), device_id text REFERENCES maeum.trusted_devices, nonce_hash text NOT NULL, csrf text NOT NULL, created_at double precision NOT NULL, seen_at double precision NOT NULL, expires_at double precision NOT NULL, revoked boolean NOT NULL DEFAULT false);
CREATE TABLE maeum.device_challenges (id text PRIMARY KEY, session_hash text REFERENCES maeum.portal_sessions, user_id text REFERENCES maeum.portal_users, code_mac text NOT NULL, created_at double precision NOT NULL, expires_at double precision NOT NULL, attempts integer NOT NULL DEFAULT 0, consumed boolean NOT NULL DEFAULT false);
CREATE INDEX ON maeum.device_challenges(user_id,created_at);
CREATE TABLE maeum.portal_limits (id text PRIMARY KEY, stamps jsonb NOT NULL);
CREATE TABLE maeum.intake_links (id text PRIMARY KEY, org_id text NOT NULL REFERENCES maeum.organizations, token_hash text UNIQUE NOT NULL, management_id text NOT NULL, expires_at double precision NOT NULL, revoked boolean NOT NULL DEFAULT false, consumed_intake_id text, UNIQUE(org_id,id));
CREATE TABLE maeum.intakes (id text PRIMARY KEY, org_id text NOT NULL REFERENCES maeum.organizations, link_id text NOT NULL UNIQUE, session_id text UNIQUE NOT NULL, management_id text NOT NULL, consent_version text NOT NULL, idempotency_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(org_id,id), FOREIGN KEY(org_id,link_id) REFERENCES maeum.intake_links(org_id,id));
ALTER TABLE maeum.intake_links ADD CONSTRAINT consumed_same_org FOREIGN KEY(org_id,consumed_intake_id) REFERENCES maeum.intakes(org_id,id) DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE maeum.report_snapshots (org_id text NOT NULL, intake_id text PRIMARY KEY, version integer NOT NULL, source_revision text NOT NULL, summary jsonb NOT NULL, status text NOT NULL, raw_expired boolean NOT NULL DEFAULT false, updated_at timestamptz NOT NULL DEFAULT now(), FOREIGN KEY(org_id,intake_id) REFERENCES maeum.intakes(org_id,id) ON DELETE CASCADE);
CREATE TABLE maeum.portal_reviews (id text PRIMARY KEY, org_id text NOT NULL, intake_id text NOT NULL, actor_id text NOT NULL, status text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), FOREIGN KEY(org_id,intake_id) REFERENCES maeum.intakes(org_id,id) ON DELETE CASCADE);
CREATE TABLE maeum.audit_events (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, org_id text NOT NULL, actor_id text NOT NULL, action text NOT NULL, target_hash text NOT NULL, outcome text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE maeum.invitations (id text PRIMARY KEY, org_id text NOT NULL REFERENCES maeum.organizations, email text NOT NULL, permissions text[] NOT NULL, token_hash text UNIQUE NOT NULL, expires_at double precision NOT NULL, accepted boolean NOT NULL DEFAULT false);
CREATE INDEX ON maeum.intakes(org_id,created_at,id);
CREATE INDEX ON maeum.records ((payload->>'session_id')) WHERE kind='conversation';
CREATE FUNCTION maeum.permitted(target_org text, permission text) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,maeum AS $$
 SELECT target_org = nullif(current_setting('maeum.org',true),'') AND EXISTS (
 SELECT 1 FROM maeum.memberships m JOIN maeum.organizations o ON o.id=m.org_id JOIN maeum.portal_users u ON u.id=m.user_id
 WHERE m.org_id=target_org AND m.user_id=nullif(current_setting('maeum.user',true),'') AND m.active AND o.active AND u.active AND permission=ANY(m.permissions));
$$;
REVOKE ALL ON FUNCTION maeum.permitted(text,text) FROM PUBLIC;
GRANT USAGE ON SCHEMA maeum TO maeum_portal;
GRANT EXECUTE ON FUNCTION maeum.permitted(text,text) TO maeum_portal;
GRANT SELECT ON maeum.organizations,maeum.memberships TO maeum_portal;
GRANT SELECT,INSERT,UPDATE ON maeum.portal_users,maeum.portal_sessions,maeum.trusted_devices,maeum.device_challenges,maeum.portal_limits TO maeum_portal;
GRANT SELECT,INSERT,UPDATE ON maeum.intake_links,maeum.invitations TO maeum_portal;
GRANT SELECT ON maeum.intakes,maeum.report_snapshots TO maeum_portal;
GRANT SELECT,INSERT ON maeum.portal_reviews,maeum.audit_events TO maeum_portal;
GRANT USAGE ON SEQUENCE maeum.audit_events_id_seq TO maeum_portal;
ALTER TABLE maeum.intakes ENABLE ROW LEVEL SECURITY;
ALTER TABLE maeum.report_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE maeum.intake_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE maeum.portal_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE maeum.audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE maeum.invitations ENABLE ROW LEVEL SECURITY;
CREATE POLICY intake_read ON maeum.intakes FOR SELECT TO maeum_portal USING(maeum.permitted(org_id,'report:read'));
CREATE POLICY report_read ON maeum.report_snapshots FOR SELECT TO maeum_portal USING(maeum.permitted(org_id,'report:read'));
CREATE POLICY link_manage ON maeum.intake_links TO maeum_portal USING(maeum.permitted(org_id,'link:issue')) WITH CHECK(maeum.permitted(org_id,'link:issue'));
CREATE POLICY review_read ON maeum.portal_reviews FOR SELECT TO maeum_portal USING(maeum.permitted(org_id,'report:read'));
CREATE POLICY review_write ON maeum.portal_reviews FOR INSERT TO maeum_portal WITH CHECK(maeum.permitted(org_id,'review:write') AND actor_id=current_setting('maeum.user',true));
CREATE POLICY audit_write ON maeum.audit_events FOR INSERT TO maeum_portal WITH CHECK(org_id=current_setting('maeum.org',true) AND actor_id=current_setting('maeum.user',true));
CREATE POLICY audit_read ON maeum.audit_events FOR SELECT TO maeum_portal USING(maeum.permitted(org_id,'audit:read'));
CREATE POLICY invitation_manage ON maeum.invitations TO maeum_portal USING(maeum.permitted(org_id,'member:manage')) WITH CHECK(maeum.permitted(org_id,'member:manage'));
-- Narrow definer: portal role cannot use legacy records get/put or whole-store stats.
CREATE FUNCTION maeum.read_transcript(target text) RETURNS SETOF jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,maeum AS $$
DECLARE sid text; tenant text;
BEGIN
 SELECT session_id,org_id INTO sid,tenant FROM maeum.intakes WHERE id=target;
 IF sid IS NULL OR NOT coalesce(maeum.permitted(tenant,'raw:read'),false) THEN RETURN; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(sid,0));
 IF NOT EXISTS(SELECT 1 FROM maeum.intakes WHERE id=target) THEN RETURN; END IF;
 INSERT INTO maeum.audit_events(org_id,actor_id,action,target_hash,outcome) VALUES(tenant,current_setting('maeum.user'),'raw_view',md5(target),'allowed');
 RETURN QUERY SELECT jsonb_build_object('day',split_part(record_key,'/',1),'turns',payload->'turns','raw_purged_at',payload->'raw_purged_at') FROM maeum.records WHERE kind='conversation' AND payload->>'session_id'=sid ORDER BY record_key;
END $$;
REVOKE ALL ON FUNCTION maeum.read_transcript(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION maeum.read_transcript(text) TO maeum_portal;
REVOKE ALL ON ALL TABLES IN SCHEMA maeum FROM PUBLIC;

-- Membership mutations remain tenant-scoped and cannot grant privileges the actor lacks.
GRANT UPDATE ON maeum.memberships TO maeum_portal;
ALTER TABLE maeum.memberships ENABLE ROW LEVEL SECURITY;
CREATE POLICY membership_read ON maeum.memberships FOR SELECT TO maeum_portal USING(user_id=current_setting('maeum.user',true) OR maeum.permitted(org_id,'member:manage'));
CREATE POLICY membership_write ON maeum.memberships FOR UPDATE TO maeum_portal USING(maeum.permitted(org_id,'member:manage')) WITH CHECK(maeum.permitted(org_id,'member:manage'));
CREATE FUNCTION maeum.check_member_change() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,maeum AS $$
DECLARE allowed text[];
BEGIN
 IF session_user='maeum_portal' THEN
  SELECT permissions INTO allowed FROM maeum.memberships WHERE org_id=OLD.org_id AND user_id=current_setting('maeum.user',true) AND active;
  IF NEW.org_id<>OLD.org_id OR NEW.user_id<>OLD.user_id OR NOT NEW.permissions <@ allowed THEN RAISE EXCEPTION 'membership boundary'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER member_change BEFORE UPDATE ON maeum.memberships FOR EACH ROW EXECUTE FUNCTION maeum.check_member_change();
CREATE FUNCTION maeum.invalidate_identity() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,maeum AS $$
BEGIN
 IF NEW.password_hash IS DISTINCT FROM OLD.password_hash OR NEW.email IS DISTINCT FROM OLD.email OR NEW.active IS DISTINCT FROM OLD.active THEN
  NEW.auth_version := OLD.auth_version+1;
  UPDATE maeum.portal_sessions SET revoked=true WHERE user_id=OLD.id;
  UPDATE maeum.trusted_devices SET revoked=true WHERE user_id=OLD.id;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER identity_change BEFORE UPDATE ON maeum.portal_users FOR EACH ROW EXECUTE FUNCTION maeum.invalidate_identity();
REVOKE ALL ON FUNCTION maeum.check_member_change(),maeum.invalidate_identity() FROM PUBLIC;
