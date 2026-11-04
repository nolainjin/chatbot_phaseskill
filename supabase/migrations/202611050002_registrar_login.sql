-- System administrators may sign in independently of institution membership.
-- This only controls authentication eligibility; tenant RLS is unchanged.
CREATE OR REPLACE FUNCTION maeum.email_login_eligible(target_user text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,maeum AS $$
 SELECT EXISTS(SELECT 1 FROM maeum.portal_users u WHERE u.id=target_user AND u.active
 AND (u.is_registrar OR EXISTS(SELECT 1 FROM maeum.memberships m
 JOIN maeum.organizations o ON o.id=m.org_id
 WHERE m.user_id=u.id AND m.active AND o.active)));
$$;
REVOKE ALL ON FUNCTION maeum.email_login_eligible(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION maeum.email_login_eligible(text) TO maeum_auth;
