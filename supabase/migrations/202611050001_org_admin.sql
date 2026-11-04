-- Registrar-managed institutions. Additive: functions and grants only.
CREATE FUNCTION maeum.org_directory(token text) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,maeum AS $$
BEGIN
 IF NOT maeum.registrar_valid(token) THEN RAISE EXCEPTION 'registrar required'; END IF;
 RETURN coalesce((SELECT jsonb_agg(jsonb_build_object('id',o.id,'name',o.name,'active',o.active,
   'members',(SELECT count(*) FROM maeum.memberships m WHERE m.org_id=o.id AND m.active)) ORDER BY o.name,o.id)
   FROM maeum.organizations o),'[]'::jsonb);
END $$;

CREATE FUNCTION maeum.create_organization(token text, org_name text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,maeum AS $$
DECLARE clean text; new_id text; actor text;
BEGIN
 IF NOT maeum.registrar_valid(token) THEN RAISE EXCEPTION 'registrar required'; END IF;
 clean := btrim(org_name, E' \t\r\n');
 IF clean IS NULL OR length(clean) NOT BETWEEN 1 AND 80 OR clean ~ '[[:cntrl:]]' THEN RAISE EXCEPTION 'invalid organization name'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('maeum-org-name',0));
 IF EXISTS(SELECT 1 FROM maeum.organizations WHERE active AND lower(name)=lower(clean)) THEN RAISE EXCEPTION 'duplicate organization'; END IF;
 SELECT user_id INTO actor FROM maeum.portal_sessions WHERE token_hash=token;
 new_id := 'org-' || substr(replace(gen_random_uuid()::text,'-',''),1,12);
 INSERT INTO maeum.organizations(id,name,active) VALUES(new_id,clean,true);
 INSERT INTO maeum.audit_events(org_id,actor_id,action,target_hash,outcome)
 VALUES(new_id,actor,'org_create',md5(new_id),'allowed');
 RETURN new_id;
END $$;

CREATE FUNCTION maeum.update_organization(token text, org_id text, org_name text, org_active boolean) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,maeum AS $$
DECLARE clean text; actor text;
BEGIN
 IF NOT maeum.registrar_valid(token) THEN RAISE EXCEPTION 'registrar required'; END IF;
 clean := btrim(org_name, E' \t\r\n');
 IF clean IS NULL OR length(clean) NOT BETWEEN 1 AND 80 OR clean ~ '[[:cntrl:]]' OR org_active IS NULL THEN RAISE EXCEPTION 'invalid organization name'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('maeum-org-name',0));
 IF NOT EXISTS(SELECT 1 FROM maeum.organizations o WHERE o.id=update_organization.org_id FOR UPDATE) THEN RAISE EXCEPTION 'organization not found'; END IF;
 IF EXISTS(SELECT 1 FROM maeum.organizations o WHERE o.active AND o.id<>update_organization.org_id AND lower(o.name)=lower(clean)) THEN RAISE EXCEPTION 'duplicate organization'; END IF;
 SELECT user_id INTO actor FROM maeum.portal_sessions WHERE token_hash=token;
 UPDATE maeum.organizations o SET name=clean,active=org_active WHERE o.id=update_organization.org_id;
 INSERT INTO maeum.audit_events(org_id,actor_id,action,target_hash,outcome)
 VALUES(update_organization.org_id,actor,'org_update',md5(update_organization.org_id),'allowed');
END $$;

REVOKE ALL ON FUNCTION maeum.org_directory(text),maeum.create_organization(text,text),maeum.update_organization(text,text,text,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION maeum.org_directory(text),maeum.create_organization(text,text),maeum.update_organization(text,text,text,boolean) TO maeum_auth;
