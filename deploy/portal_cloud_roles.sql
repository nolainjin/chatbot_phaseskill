-- Cloud-only post-migration grants. maeum_engine is a dedicated application role,
-- never the postgres/schema-owner credential in the deployed application.
GRANT USAGE ON SCHEMA maeum TO maeum_engine;
GRANT SELECT,INSERT,UPDATE,DELETE ON maeum.records TO maeum_engine;
CREATE POLICY engine_records ON maeum.records TO maeum_engine USING(true) WITH CHECK(true);
GRANT SELECT ON maeum.organizations TO maeum_engine;
-- INSERT: opening a shared review link (OPEN-…) mints one single-use TRY-… link per visit.
GRANT SELECT,INSERT,UPDATE ON maeum.intake_links TO maeum_engine;
GRANT SELECT,INSERT,UPDATE,DELETE ON maeum.intakes,maeum.report_snapshots TO maeum_engine;
CREATE POLICY engine_links ON maeum.intake_links TO maeum_engine USING(true) WITH CHECK(true);
CREATE POLICY engine_intakes ON maeum.intakes TO maeum_engine USING(true) WITH CHECK(true);
CREATE POLICY engine_reports ON maeum.report_snapshots TO maeum_engine USING(true) WITH CHECK(true);

ALTER TABLE maeum.portal_users ADD CONSTRAINT supabase_identity_fk
 FOREIGN KEY(supabase_user_id) REFERENCES auth.users(id) ON DELETE SET NULL;

CREATE FUNCTION maeum.sync_auth_identity() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path=pg_catalog,maeum AS $$
DECLARE uid uuid;
BEGIN
 uid := OLD.id;
 IF TG_OP='DELETE' THEN
  UPDATE maeum.portal_users SET active=false WHERE supabase_user_id=uid;
  RETURN OLD;
 END IF;
 IF NEW.encrypted_password IS DISTINCT FROM OLD.encrypted_password
 OR NEW.email IS DISTINCT FROM OLD.email
 OR NEW.banned_until IS DISTINCT FROM OLD.banned_until
 OR NEW.deleted_at IS DISTINCT FROM OLD.deleted_at THEN
  UPDATE maeum.portal_users SET email=lower(NEW.email),
   active=(active AND NEW.deleted_at IS NULL AND (NEW.banned_until IS NULL OR NEW.banned_until<=now())),
   auth_version=auth_version+1 WHERE supabase_user_id=uid;
  UPDATE maeum.portal_sessions SET revoked=true WHERE user_id IN
   (SELECT id FROM maeum.portal_users WHERE supabase_user_id=uid);
  UPDATE maeum.trusted_devices SET revoked=true WHERE user_id IN
   (SELECT id FROM maeum.portal_users WHERE supabase_user_id=uid);
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION maeum.sync_auth_identity() FROM PUBLIC;
CREATE TRIGGER maeum_auth_identity_update AFTER UPDATE ON auth.users
 FOR EACH ROW EXECUTE FUNCTION maeum.sync_auth_identity();
CREATE TRIGGER maeum_auth_identity_delete BEFORE DELETE ON auth.users
 FOR EACH ROW EXECUTE FUNCTION maeum.sync_auth_identity();

-- No anonymous browser role receives access to the private app schema.
REVOKE ALL ON SCHEMA maeum FROM PUBLIC,anon,authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA maeum FROM PUBLIC,anon,authenticated;
