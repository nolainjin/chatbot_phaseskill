"""Portal HTTP surface. The local runner enables it; remote deployment stays closed."""
import os
from pathlib import Path
import secrets
import time
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from app import cloud_store, intake, portal_auth as auth, portal_store as store
from app.config import Settings
from app.portal_config import Policy
from app import portal_config, portal_email, portal_google, portal_orgs

router = APIRouter()


@router.get("/portal/admin")
@router.get("/portal/admin/")
@router.get("/portal")
@router.get("/portal/")
@router.get("/portal/index.html")
@router.get("/portal/login")
def portal_page(request: Request):
    html = (Path(__file__).resolve().parents[1] / "static/portal/index.html").read_text()
    mode = 'admin' if request.url.path.rstrip('/') == '/portal/admin' else 'institution'
    html = html.replace('data-portal-mode="institution"', 'data-portal-mode="' + mode + '"')
    if mode == 'admin':
        html = html.replace('마음 접수 · 기관 포털', '마음 접수 · 관리자 대시보드')
    if portal_config.cloud():
        html = html.replace('<details><summary>초대 수락</summary>',
                            '<details hidden><summary>초대 수락</summary>')
        html = html.replace('로컬 합성 시험 환경 · 실제 상담 자료와 실제 이메일 발송을 사용하지 않습니다.',
                            '합성 접수 시험 환경 · 등록된 담당자 이메일로 기기를 확인합니다.')
    if portal_email.enabled():
        html = html.replace('data-email-login="false"', 'data-email-login="true"')
        html = html.replace('<div id="password-fields">', '<div id="password-fields" hidden>')
        html = html.replace('id="password" type="password"', 'id="password" type="password" disabled')
        html = html.replace('<button id="login-submit">로그인</button>', '<button id="login-submit">인증번호 받기</button>')
        html = html.replace('id="signup-open" class="secondary" hidden', 'id="signup-open" class="secondary"')
        html = html.replace('id="email-session-hint" class="hint" hidden', 'id="email-session-hint" class="hint"')
        html = html.replace('로그인 상태는 이 브라우저에 유지됩니다.',
                            f'이 브라우저에서 최대 {Policy.load().email_session_seconds / 86400:g}일간 로그인 상태를 유지합니다.')
        html = html.replace('<details><summary>초대 수락</summary>', '<details hidden><summary>초대 수락</summary>')
        html = html.replace('등록된 담당자 이메일로 기기를 확인합니다.', '등록된 담당자는 이메일 인증번호로 로그인합니다.')
        if portal_email.link_delivery():
            html = html.replace('인증번호 받기</button>', '이메일 로그인 링크 받기</button>')
            html = html.replace('등록된 이메일로 인증번호를 보내드립니다.', '등록된 Gmail로 로그인 링크를 보내드립니다.')
            html = html.replace('등록된 담당자는 이메일 인증번호로 로그인합니다.', 'Gmail 이메일 링크 로그인 · 현재 지정된 시험계정만 인증 메일을 받을 수 있습니다.')
            html = html.replace('등록한 뒤 코드로 로그인할 수 있습니다.', '등록합니다. 현재 지정된 Gmail 시험계정 외의 인증 메일 발송은 준비 중입니다.')
            html = html.replace('신청 이메일의 실제 소유 여부는 코드 로그인 때 확인합니다.', '이메일 소유는 로그인 때 확인합니다. 현재 지정된 Gmail 시험계정 외의 인증 메일은 발송하지 않습니다.')
    if portal_google.enabled():
        html = html.replace('data-google-login="false"', 'data-google-login="true"')
        html = html.replace('id="google-login-options" hidden', 'id="google-login-options"')
        html = html.replace('id="email-login-details" open', 'id="email-login-details"')
        html = html.replace('<summary hidden>이메일 링크로 로그인</summary>', '<summary>이메일 링크로 로그인</summary>')
        html = html.replace('Gmail 이메일 링크 로그인 · 현재 지정된 시험계정만 인증 메일을 받을 수 있습니다.',
                            '등록된 Gmail 담당자는 Google 계정으로 로그인합니다.')
        html = html.replace('등록합니다. 현재 지정된 Gmail 시험계정 외의 인증 메일 발송은 준비 중입니다.',
                            '등록한 뒤 Google 계정으로 로그인할 수 있습니다.')
    return HTMLResponse(html)


@router.get("/portal/app.js")
def portal_js():
    return FileResponse(Path(__file__).resolve().parents[1] / "static/portal/app.js", media_type="application/javascript")


@router.get('/portal/auth-return')
def auth_return():
    return FileResponse(Path(__file__).resolve().parents[1] / 'static/portal/auth-return.html')


@router.post('/api/portal/auth/exchange')
def auth_exchange(request: Request, response: Response, payload: dict = Body(...)):
    if not portal_config.cloud() or portal_email.enabled():
        raise HTTPException(404)
    from app.portal_supabase import exchange
    return exchange(request, response, payload)


@router.post("/api/portal/auth/login")
def login(request: Request, response: Response, payload: dict = Body(...)):
    if portal_email.enabled():
        raise HTTPException(410, '이메일 인증번호 로그인을 이용해 주세요.')
    return auth.login(request, response, payload)


@router.post("/api/portal/auth/device-challenge")
def challenge(request: Request):
    if portal_email.enabled():
        raise HTTPException(410, '이메일 인증번호 로그인을 이용해 주세요.')
    return auth.challenge(request)


@router.post("/api/portal/auth/device-verify")
def verify(request: Request, response: Response, payload: dict = Body(...)):
    if portal_email.enabled():
        raise HTTPException(410, '이메일 인증번호 로그인을 이용해 주세요.')
    return auth.verify(request, response, payload)


def email_mode():
    if not portal_email.enabled():
        raise HTTPException(404)


def google_mode():
    if not portal_google.enabled():
        raise HTTPException(404)


@router.post('/api/portal/auth/google-start')
def google_start(request: Request, response: Response, payload: dict = Body(default={})):
    google_mode()
    return portal_google.start(request, response, payload)


@router.get('/portal/google-return')
def google_return():
    google_mode()
    return FileResponse(Path(__file__).resolve().parents[1] / 'static/portal/google-return.html')


@router.post('/api/portal/auth/google-exchange')
def google_exchange(request: Request, response: Response, payload: dict = Body(default={})):
    google_mode()
    return portal_google.exchange(request, response, payload)


@router.post('/api/portal/auth/email-start')
def email_start(request: Request, response: Response, payload: dict = Body(...)):
    email_mode()
    return portal_email.start(request, response, payload)


@router.get('/api/portal/auth/email-pending')
def email_pending(request: Request):
    email_mode()
    return portal_email.pending(request)


@router.post('/api/portal/auth/email-login-verify')
def email_verify(request: Request, response: Response, payload: dict = Body(...)):
    email_mode()
    return portal_email.verify(request, response, payload)


@router.get('/portal/email-return')
def email_return():
    email_mode()
    if not portal_email.link_delivery():
        raise HTTPException(404)
    return FileResponse(Path(__file__).resolve().parents[1] / 'static/portal/email-return.html')


@router.post('/api/portal/auth/email-exchange')
def email_exchange(request: Request, response: Response, payload: dict = Body(...)):
    email_mode()
    if not portal_email.link_delivery():
        raise HTTPException(404)
    return portal_email.verify(request, response, payload, link=True)


@router.post('/api/portal/auth/email-cancel')
def email_cancel(request: Request, response: Response):
    email_mode()
    with auth.connect() as conn:
        row = portal_email.attempt(conn, request)
        auth.csrf(request, row)
        conn.execute('UPDATE maeum.email_login_attempts SET consumed=true WHERE token_hash=%s', (row['token_hash'],))
    response.delete_cookie(portal_email.ATTEMPT, path='/')
    response.delete_cookie(portal_email.BROWSER, path='/')
    return {'cancelled': True}


@router.post('/api/portal/auth/apply')
def signup_apply(request: Request, payload: dict = Body(...)):
    email_mode()
    return portal_email.apply(request, payload)


@router.get('/api/portal/registrations')
def registration_directory(request: Request):
    email_mode()
    return portal_email.directory(request)


@router.post('/api/portal/registrations')
def preregister_email(request: Request, payload: dict = Body(...)):
    email_mode()
    return portal_email.register(request, payload)


@router.post('/api/portal/registrations/reject')
def registration_reject(request: Request, payload: dict = Body(...)):
    email_mode()
    return portal_email.reject(request, payload)


@router.get('/api/portal/organizations')
def organization_directory(request: Request):
    email_mode()
    return portal_orgs.directory(request)


@router.post('/api/portal/organizations')
def organization_create(request: Request, payload: dict = Body(...)):
    email_mode()
    return portal_orgs.create(request, payload)


@router.patch('/api/portal/organizations/{org_id}')
def organization_update(org_id: str, request: Request, payload: dict = Body(...)):
    email_mode()
    return portal_orgs.update(request, org_id, payload)


@router.get("/api/portal/me")
def me(request: Request, response: Response):
    with store.connect() as conn:
        s = auth.session(conn, request, verified=False, response=response)
        orgs = []
        if s["state"] == "verified":
            orgs = conn.execute("SELECT o.id,o.name,m.permissions FROM maeum.memberships m JOIN maeum.organizations o ON o.id=m.org_id WHERE m.user_id=%s AND m.active AND o.active ORDER BY o.id", (s["user_id"],)).fetchall()
        registrar = False
        if portal_email.enabled() and s['state'] == 'verified':
            with auth.connect() as auth_conn:
                registrar = auth_conn.execute('SELECT maeum.registrar_valid(%s) AS ok', (s['token_hash'],)).fetchone()['ok']
        return {"state": s["state"], "csrf": s["csrf"], "organizations": orgs,
                "email": s["email"], "expires_at": s["expires_at"],
                "verification": "email_link" if portal_config.cloud() else "code",
                "account_changes": not portal_config.cloud() and not portal_email.enabled(),
                "registrar": registrar, "google_login": portal_google.enabled()}


@router.post("/api/portal/auth/logout")
def logout(request: Request, response: Response):
    with auth.connect() as conn:
        s = auth.session(conn, request, verified=False)
        auth.csrf(request, s)
        conn.execute("UPDATE maeum.portal_sessions SET revoked=true WHERE token_hash=%s", (s["token_hash"],))
        if portal_email.enabled():
            conn.execute('UPDATE maeum.email_login_attempts SET consumed=true WHERE token_hash=%s',
                         (store.digest(request.cookies.get(portal_email.ATTEMPT, '')),))
    response.delete_cookie(auth.SESSION, path="/")
    response.delete_cookie(auth.NONCE, path="/")
    response.delete_cookie(portal_email.ATTEMPT, path='/')
    response.delete_cookie(portal_email.BROWSER, path='/')
    return {"logged_out": True}


def tenant(conn, request, org_id, permission):
    s = auth.session(conn, request)
    if request.method not in {"GET", "HEAD"}:
        auth.csrf(request, s)
    store.context(conn, s["user_id"], org_id, permission, s["token_hash"])
    return s


@router.get("/api/portal/devices")
def devices(request: Request):
    with auth.connect() as conn:
        s = auth.session(conn, request)
        return conn.execute("SELECT id,created_at,expires_at,revoked,(id=%s) AS current FROM maeum.trusted_devices WHERE user_id=%s ORDER BY created_at DESC", (s["device_id"], s["user_id"])).fetchall()


@router.delete("/api/portal/devices/{device_id}")
def revoke_device(device_id: str, request: Request, response: Response):
    with auth.connect() as conn:
        s = auth.session(conn, request)
        auth.csrf(request, s)
        row = conn.execute("UPDATE maeum.trusted_devices SET revoked=true WHERE id=%s AND user_id=%s RETURNING id", (device_id, s["user_id"])).fetchone()
        if not row:
            raise HTTPException(404, "기기를 찾을 수 없습니다.")
        conn.execute("UPDATE maeum.portal_sessions SET revoked=true WHERE device_id=%s AND user_id=%s", (device_id, s["user_id"]))
    current_revoked = str(s['device_id']) == device_id
    if current_revoked:
        for name in [auth.SESSION, auth.NONCE, auth.DEVICE, portal_email.ATTEMPT, portal_email.BROWSER]:
            response.delete_cookie(name, path='/')
    return {"revoked": True, "current_revoked": current_revoked}


@router.post("/api/portal/links")
def issue_link(request: Request, payload: dict = Body(...)):
    from app.main import _valid_management_id
    management = payload.get("management_id")
    if not _valid_management_id(management):
        raise HTTPException(400, "관리번호는 개인정보 없이 영문·숫자·하이픈 1~32자로 입력해 주세요.")
    if management.startswith(store.RESERVED_PREFIXES):
        raise HTTPException(400, "OPEN-·TRY-로 시작하는 관리번호는 여러 사람이 함께 쓰는 시험 링크용이라 쓸 수 없습니다.")
    org_id = payload.get("org_id", "")
    token, link_id = secrets.token_urlsafe(32), str(uuid4())
    with store.connect() as conn:
        s = tenant(conn, request, org_id, "link:issue")
        conn.execute("INSERT INTO maeum.intake_links(id,org_id,token_hash,management_id,expires_at) VALUES(%s,%s,%s,%s,%s)",
                     (link_id, org_id, store.digest(token), management, time.time() + Policy.load().link_seconds))
        store.audit(conn, org_id, s["user_id"], "link_issue", link_id)
    # Fragment is never sent to the HTTP server/access log or referrer.
    return {"id": link_id, "url": os.environ["PORTAL_ORIGIN"] + "/#intake=" + token}


@router.post('/api/portal/testbed')
def testbed(request: Request, payload: dict = Body(...)):
    # The registrar role never grants access to an institution by itself.
    with auth.connect() as conn:
        portal_email.registrar(conn, request)
    return _issue_testbed_link(request, payload)


@router.post('/api/portal/institutions/testbed')
def institution_testbed(request: Request, payload: dict = Body(...)):
    # Institution staff already authorized to issue links may create synthetic
    # links; this does not confer global registration/organization privileges.
    return _issue_testbed_link(request, payload)


def _issue_testbed_link(request: Request, payload: dict):
    org_id = payload.get('org_id')
    if not isinstance(org_id, str) or not org_id or len(org_id) > 128:
        raise HTTPException(400, '테스트할 소속 기관을 선택해 주세요.')
    management = 'TEST-' + secrets.token_hex(6).upper()
    result = issue_link(request, {'org_id': org_id, 'management_id': management})
    return {**result, 'management_id': management, 'synthetic': True}


@router.get("/api/portal/links")
def links(request: Request, org_id: str):
    with store.connect() as conn:
        tenant(conn, request, org_id, "link:issue")
        return conn.execute("SELECT id,management_id,expires_at,revoked,consumed_intake_id IS NOT NULL AS consumed FROM maeum.intake_links WHERE org_id=%s ORDER BY expires_at DESC LIMIT 100", (org_id,)).fetchall()


@router.delete("/api/portal/links/{link_id}")
def revoke_link(link_id: str, request: Request, org_id: str):
    with store.connect() as conn:
        s = tenant(conn, request, org_id, "link:issue")
        if not conn.execute("UPDATE maeum.intake_links SET revoked=true WHERE org_id=%s AND id=%s RETURNING id", (org_id, link_id)).fetchone():
            raise HTTPException(404, "링크를 찾을 수 없습니다.")
        store.audit(conn, org_id, s["user_id"], "link_revoke", link_id)
    return {"revoked": True}


@router.post("/api/intake-link/exchange")
def exchange(request: Request, response: Response, payload: dict = Body(...)):
    auth.csrf(request)
    auth.limit("exchange:" + store.digest(request.client.host), count=120)
    token = payload.get("token", request.cookies.get("maeum_link", ""))
    link_id, org_id, management, _ = store.link_for_token(token)
    shared = store.reusable(management)
    if shared:
        # A shared review link hands this visit its own single-use link; only that one goes in the cookie.
        token = store.issue_reusable_child(link_id, org_id, management, Policy.load().link_seconds)
    with cloud_store.connection() as conn:
        name = conn.execute("SELECT name FROM maeum.organizations WHERE id=%s", (org_id,)).fetchone()[0]
    auth.cookie(response, "maeum_link", token, Policy.load().link_seconds)
    # The tab pins the link it exchanged (for a shared review link, its own per-visit link) and
    # consents with it, so another tab's cookie cannot change which organization receives this case.
    result = {"organization": name, "purpose": "상담 접수 내용과 요약을 이 기관 담당자에게 전달합니다.", "link_token": token}
    if shared:
        result["reusable"] = True
    return result


@router.post("/api/intake-link/review")
def shared_review(request: Request, payload: dict = Body(...)):
    """Saved cases of one shared review link, report and conversation, for anyone holding that link."""
    from app import ratelimit
    auth.csrf(request)
    ip = ratelimit.client_ip(request, Settings.from_env().trust_proxy_hops)
    auth.limit("shared-review:" + store.digest(ip), count=120)
    link_id, org_id, management, _ = store.link_for_token(payload.get("token", ""))
    if not store.reusable(management):
        raise HTTPException(410, "함께 쓰는 시험 링크로만 볼 수 있습니다.")
    auth.limit("shared-review-link:" + link_id, count=600)
    schema = intake.load_schema(Settings.from_env().knowledge_dir)
    return {"slot_labels": [[slot.id, slot.label] for slot in schema.slots if slot.id != "track"],
            "cases": store.shared_review_cases(org_id, link_id, management)}


@router.get("/api/portal/intakes")
def intakes(request: Request, org_id: str, search: str = Query("", max_length=32),
            offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    with store.connect() as conn:
        s = tenant(conn, request, org_id, "report:read")
        rows = conn.execute("SELECT i.id,i.management_id,i.created_at,r.status,r.version,r.updated_at,"
                            "coalesce((SELECT status FROM maeum.portal_reviews v WHERE v.intake_id=i.id AND v.org_id=i.org_id ORDER BY v.created_at DESC,v.id DESC LIMIT 1),'unreviewed') AS review_status "
                            "FROM maeum.intakes i JOIN maeum.report_snapshots r ON r.intake_id=i.id AND r.org_id=i.org_id "
                            "WHERE i.org_id=%s AND i.management_id LIKE %s ORDER BY i.created_at DESC,i.id LIMIT %s OFFSET %s",
                            (org_id, "%" + search.replace("%", "\\%").replace("_", "\\_") + "%", limit, offset)).fetchall()
        store.audit(conn, org_id, s["user_id"], "list_view", org_id)
        return {"items": rows, "offset": offset, "limit": limit}


@router.get("/api/portal/summary")
def summary(request: Request, org_id: str):
    with store.connect() as conn:
        s = tenant(conn, request, org_id, "report:read")
        row = conn.execute("SELECT count(*) AS total,count(*) FILTER(WHERE r.status='complete') AS complete,"
                           "count(*) FILTER(WHERE NOT EXISTS(SELECT 1 FROM maeum.portal_reviews v WHERE v.org_id=i.org_id AND v.intake_id=i.id)) AS unreviewed "
                           "FROM maeum.intakes i JOIN maeum.report_snapshots r ON r.intake_id=i.id AND r.org_id=i.org_id WHERE i.org_id=%s", (org_id,)).fetchone()
        store.audit(conn, org_id, s["user_id"], "summary_view", org_id)
        return row


@router.get("/api/portal/intakes/{intake_id}")
def report(intake_id: str, request: Request, org_id: str):
    with store.connect() as conn:
        s = tenant(conn, request, org_id, "report:read")
        result = store.detail(conn, org_id, intake_id)
        schema = intake.load_schema(Settings.from_env().knowledge_dir)
        result["slot_labels"] = {slot.id: slot.label for slot in schema.slots}
        store.audit(conn, org_id, s["user_id"], "report_view", intake_id)
        return result


@router.get("/api/portal/intakes/{intake_id}/transcript")
def transcript(intake_id: str, request: Request, org_id: str):
    with store.connect() as conn:
        tenant(conn, request, org_id, "raw:read")
        # Same generic not-found response for foreign and absent IDs.
        store.detail(conn, org_id, intake_id)
        rows = conn.execute("SELECT maeum.read_transcript(%s) AS document", (intake_id,)).fetchall()
        return {"documents": [r["document"] for r in rows]}


@router.post("/api/portal/intakes/{intake_id}/review")
def review(intake_id: str, request: Request, payload: dict = Body(...)):
    if payload.get("status") not in {"reviewed", "needs_followup"}:
        raise HTTPException(400, "확인 상태를 선택해 주세요.")
    org_id = payload.get("org_id", "")
    with store.connect() as conn:
        s = tenant(conn, request, org_id, "review:write")
        store.detail(conn, org_id, intake_id)
        conn.execute("INSERT INTO maeum.portal_reviews(id,org_id,intake_id,actor_id,status) VALUES(%s,%s,%s,%s,%s)",
                     (str(uuid4()), org_id, intake_id, s["user_id"], payload["status"]))
        store.audit(conn, org_id, s["user_id"], "review", intake_id)
    return {"status": payload["status"]}


@router.get("/api/portal/members")
def members(request: Request, org_id: str):
    with store.connect() as conn:
        tenant(conn, request, org_id, "member:manage")
        return conn.execute("SELECT user_id,permissions,active FROM maeum.memberships WHERE org_id=%s ORDER BY user_id", (org_id,)).fetchall()


@router.patch("/api/portal/members/{user_id}")
def update_member(user_id: str, request: Request, payload: dict = Body(...)):
    org_id = payload.get("org_id", "")
    permissions = payload.get("permissions")
    if not isinstance(permissions, list) or not all(isinstance(v, str) for v in permissions) or type(payload.get("active")) is not bool:
        raise HTTPException(400, "권한과 활성 상태를 확인해 주세요.")
    with store.connect() as conn:
        s = tenant(conn, request, org_id, "member:manage")
        if user_id == s["user_id"] and (not payload["active"] or "member:manage" not in permissions):
            raise HTTPException(409, "본인 소속과 관리 권한은 여기서 바꿀 수 없습니다.")
        own = conn.execute("SELECT permissions FROM maeum.memberships WHERE org_id=%s AND user_id=%s", (org_id, s["user_id"])).fetchone()
        if not set(permissions) <= set(own["permissions"]):
            raise HTTPException(403, "자신이 가진 권한만 부여할 수 있습니다.")
        if not conn.execute("UPDATE maeum.memberships SET permissions=%s,active=%s WHERE org_id=%s AND user_id=%s RETURNING user_id", (permissions, payload["active"], org_id, user_id)).fetchone():
            raise HTTPException(404, "담당자를 찾을 수 없습니다.")
        store.audit(conn, org_id, s["user_id"], "member_update", user_id)
    return {"updated": True}


@router.get("/api/portal/audit")
def audit(request: Request, org_id: str):
    with store.connect() as conn:
        tenant(conn, request, org_id, "audit:read")
        return conn.execute("SELECT actor_id,action,target_hash,outcome,created_at FROM maeum.audit_events WHERE org_id=%s ORDER BY id DESC LIMIT 100", (org_id,)).fetchall()


@router.post("/api/portal/invitations")
def invite(request: Request, payload: dict = Body(...)):
    email, permissions, org_id = payload.get("email", ""), payload.get("permissions"), payload.get("org_id", "")
    # Local-only synthetic addresses. Real mail is impossible through this adapter.
    if not isinstance(email, str) or not email.endswith("@example.test") or len(email) > 254 or not isinstance(permissions, list):
        raise HTTPException(400, "로컬 시험 이메일과 권한을 확인해 주세요.")
    if not all(isinstance(p, str) for p in permissions):
        raise HTTPException(400, "권한을 확인해 주세요.")
    with store.connect() as conn:
        s = tenant(conn, request, org_id, "member:manage")
        own = conn.execute("SELECT permissions FROM maeum.memberships WHERE org_id=%s AND user_id=%s", (org_id, s["user_id"])).fetchone()
        if not set(permissions) <= set(own["permissions"]):
            raise HTTPException(403, "자신이 가진 권한만 초대할 수 있습니다.")
        token, invitation_id = secrets.token_urlsafe(32), str(uuid4())
        conn.execute("INSERT INTO maeum.invitations VALUES(%s,%s,%s,%s,%s,%s,false)",
                     (invitation_id, org_id, email.lower(), permissions, store.digest(token), time.time() + Policy.load().link_seconds))
        try:
            auth.capture_mail({"purpose": "invitation", "to": email.lower(), "token": token})
        except OSError as exc:
            raise HTTPException(503, "초대 메일을 준비하지 못했습니다.") from exc
        store.audit(conn, org_id, s["user_id"], "invite", invitation_id)
    return {"id": invitation_id, "capture_only": True}


@router.post("/api/portal/auth/accept-invitation")
def accept_invitation(request: Request, payload: dict = Body(...)):
    auth.csrf(request)
    auth.limit("invitation:" + store.digest(request.client.host))
    token, password = payload.get("token"), payload.get("password")
    if not isinstance(token, str) or len(token) > 128 or not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise HTTPException(400, "초대 코드와 12자 이상 비밀번호가 필요합니다.")
    # Onboarding service is separate from the RLS portal read role.
    with cloud_store.connection() as conn:
        row = conn.execute("SELECT i.id,i.org_id,i.email,i.permissions FROM maeum.invitations i JOIN maeum.organizations o ON o.id=i.org_id WHERE i.token_hash=%s AND NOT i.accepted AND i.expires_at>%s AND o.active FOR UPDATE OF i", (store.digest(token), time.time())).fetchone()
        if not row or conn.execute("SELECT 1 FROM maeum.portal_users WHERE email=%s", (row[2],)).fetchone():
            raise HTTPException(410, "초대를 사용할 수 없습니다.")
        uid = str(uuid4())
        conn.execute("INSERT INTO maeum.portal_users(id,email,password_hash) VALUES(%s,%s,%s)", (uid, row[2], auth.hash_password(password)))
        conn.execute("INSERT INTO maeum.memberships(org_id,user_id,permissions) VALUES(%s,%s,%s)", (row[1], uid, row[3]))
        conn.execute("UPDATE maeum.invitations SET accepted=true WHERE id=%s", (row[0],))
    return {"accepted": True, "next": "login_and_device_verification"}


@router.post("/api/portal/auth/password")
def change_password(request: Request, payload: dict = Body(...)):
    current, new = payload.get("current_password"), payload.get("new_password")
    if not isinstance(current, str) or len(current) > 1024 or not isinstance(new, str) or not 12 <= len(new) <= 128:
        raise HTTPException(400, "현재 비밀번호와 12자 이상 새 비밀번호가 필요합니다.")
    with auth.connect() as conn:
        s = auth.session(conn, request)
        auth.csrf(request, s)
        user = conn.execute("SELECT password_hash FROM maeum.portal_users WHERE id=%s", (s["user_id"],)).fetchone()
        if not auth.password_ok(current, user["password_hash"]):
            raise HTTPException(401, "비밀번호를 확인해 주세요.")
        conn.execute("UPDATE maeum.portal_users SET password_hash=%s WHERE id=%s", (auth.hash_password(new), s["user_id"]))
    return {"changed": True, "next": "login_and_device_verification"}

@router.post("/api/portal/auth/email-challenge")
def email_challenge(request: Request, payload: dict = Body(...)):
    email, password = payload.get("email"), payload.get("password")
    if (not isinstance(email, str) or not email.endswith("@example.test") or len(email) > 254
            or not isinstance(password, str) or len(password) > 1024):
        raise HTTPException(400, "로컬 시험 이메일과 비밀번호를 확인해 주세요.")
    with auth.connect() as conn:
        s = auth.session(conn, request)
        auth.csrf(request, s)
        auth.limit("email-change:" + s["user_id"], count=5)
        user = conn.execute("SELECT password_hash FROM maeum.portal_users WHERE id=%s", (s["user_id"],)).fetchone()
        if not auth.password_ok(password, user["password_hash"]):
            raise HTTPException(401, "비밀번호를 확인해 주세요.")
        if conn.execute("SELECT 1 FROM maeum.portal_users WHERE email=%s", (email.lower(),)).fetchone():
            raise HTTPException(400, "이 이메일로 변경할 수 없습니다.")
        conn.execute("UPDATE maeum.email_changes SET consumed=true WHERE user_id=%s", (s["user_id"],))
        token = secrets.token_urlsafe(32)
        conn.execute("INSERT INTO maeum.email_changes VALUES(%s,%s,%s,%s,%s,false)",
                     (str(uuid4()), s["user_id"], email.lower(), store.digest(token), time.time()+Policy.load().code_seconds))
        try:
            auth.capture_mail({"purpose": "email_change", "to": email.lower(), "token": token})
        except OSError as exc:
            raise HTTPException(503, "확인 메일을 준비하지 못했습니다.") from exc
    return {"sent": True, "capture_only": True}


@router.post("/api/portal/auth/email-verify")
def email_verify(request: Request, payload: dict = Body(...)):
    token = payload.get("token")
    if not isinstance(token, str) or len(token)>128:
        raise HTTPException(400, "이메일 확인 코드가 필요합니다.")
    with auth.connect() as conn:
        s = auth.session(conn, request)
        auth.csrf(request, s)
        change = conn.execute("SELECT * FROM maeum.email_changes WHERE user_id=%s AND token_hash=%s AND NOT consumed AND expires_at>%s FOR UPDATE",
                              (s["user_id"], store.digest(token), time.time())).fetchone()
        if not change:
            raise HTTPException(400, "이메일 확인 코드가 올바르지 않거나 만료되었습니다.")
        if conn.execute("SELECT 1 FROM maeum.portal_users WHERE email=%s", (change["new_email"],)).fetchone():
            raise HTTPException(409, "이 이메일로 변경할 수 없습니다.")
        conn.execute("UPDATE maeum.email_changes SET consumed=true WHERE id=%s", (change["id"],))
        conn.execute("UPDATE maeum.portal_users SET email=%s WHERE id=%s", (change["new_email"], s["user_id"]))
    return {"changed": True, "next": "login_and_device_verification"}
