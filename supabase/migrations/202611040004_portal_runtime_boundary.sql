-- Separate auth-service credentials from report-query credentials.
-- Provision maeum_auth LOGIN NOSUPERUSER NOBYPASSRLS before applying.
GRANT USAGE ON SCHEMA maeum TO maeum_auth;
GRANT SELECT,INSERT,UPDATE ON maeum.portal_users,maeum.portal_sessions,maeum.trusted_devices,maeum.device_challenges,maeum.portal_limits,maeum.email_changes TO maeum_auth;
REVOKE ALL ON maeum.portal_users,maeum.portal_sessions,maeum.trusted_devices,maeum.device_challenges,maeum.portal_limits,maeum.email_changes FROM maeum_portal;
CREATE OR REPLACE FUNCTION maeum.permitted(target_org text, permission text) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,maeum AS $$
 SELECT target_org = nullif(current_setting('maeum.org',true),'') AND EXISTS (
 SELECT 1 FROM maeum.memberships m
 JOIN maeum.organizations o ON o.id=m.org_id
 JOIN maeum.portal_users u ON u.id=m.user_id
 JOIN maeum.portal_sessions s ON s.user_id=u.id
 LEFT JOIN maeum.trusted_devices d ON d.id=s.device_id
 WHERE m.org_id=target_org AND m.user_id=nullif(current_setting('maeum.user',true),'')
 AND m.active AND o.active AND u.active AND permission=ANY(m.permissions)
 AND s.token_hash=nullif(current_setting('maeum.session',true),'') AND s.state='verified'
 AND NOT s.revoked AND s.auth_version=u.auth_version
 AND s.expires_at>extract(epoch FROM clock_timestamp())
 AND s.seen_at + coalesce(nullif(current_setting('maeum.idle_seconds',true),'')::integer,1800)>extract(epoch FROM clock_timestamp())
 AND (s.device_id IS NULL OR (NOT d.revoked AND d.expires_at>extract(epoch FROM clock_timestamp()))));
$$;
