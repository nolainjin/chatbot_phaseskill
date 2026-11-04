-- Shared local/cloud schema. Auth-provider events are linked separately in deploy.
ALTER TABLE maeum.portal_users ADD COLUMN supabase_user_id uuid UNIQUE;

-- Check the effective role as well as the login role; pooler/SET ROLE cannot
-- bypass permission-subset checks. SECURITY DEFINER changes current_user, so
-- current_setting('role') is inspected for a SET ROLE connection.
CREATE OR REPLACE FUNCTION maeum.check_member_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,maeum AS $$
DECLARE allowed text[];
BEGIN
 IF session_user='maeum_portal' OR current_setting('role',true)='maeum_portal' THEN
  SELECT permissions INTO allowed FROM maeum.memberships WHERE org_id=OLD.org_id
   AND user_id=current_setting('maeum.user',true) AND active;
  IF allowed IS NULL OR NEW.org_id<>OLD.org_id OR NEW.user_id<>OLD.user_id
     OR NOT NEW.permissions <@ allowed THEN RAISE EXCEPTION 'membership boundary'; END IF;
 END IF;
 RETURN NEW;
END $$;
