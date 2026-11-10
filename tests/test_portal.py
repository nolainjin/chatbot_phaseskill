"""P1-P4 integration evidence against a disposable real PostgreSQL database.

Run with scripts/portal_local.py test. No production credentials or DB are read.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlparse, urlunparse
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from fastapi.testclient import TestClient

from app import chat, cloud_store, portal_auth as auth, portal_store as store
from app.main import app
from scripts.portal_local import seed

pytestmark = pytest.mark.skipif(not os.getenv("PORTAL_TEST_CONFIG"), reason="requires isolated local PostgreSQL runner")
PASSWORD = "synthetic-test-password-only"
ORIGIN = "http://testserver"


@pytest.fixture
def email_env(env, monkeypatch):
    monkeypatch.setenv('PORTAL_EMAIL_LOGIN', '1')
    with psycopg.connect(env['MAEUM_DATABASE_URL']) as conn:
        conn.execute("UPDATE maeum.portal_users SET is_registrar=true WHERE id='A0'")
    return env


def email_start(c, email='a0@example.test'):
    result = post(c, '/auth/email-start', {'email': email})
    assert result.status_code == 200, result.text
    c.headers['X-CSRF-Token'] = result.json()['csrf']
    return result.json()


def email_enter(c, email='a0@example.test'):
    email_start(c, email)
    code = latest_mail(email, purpose='login')['code']
    result = post(c, '/auth/email-login-verify', {'code': code})
    assert result.status_code == 200, result.text
    c.headers['X-CSRF-Token'] = result.json()['csrf']
    return code


def test_email_only_login_rotation_and_legacy_disabled(email_env):
    c = client()
    for path in ['/portal', '/portal/', '/portal/index.html', '/portal/login']:
        html = c.get(path).text
        assert 'data-email-login="true"' in html
        assert 'id="signup-open" class="secondary" hidden' not in html
        assert 'id="password" type="password" disabled' in html
    email_start(c)
    assert c.get('/api/portal/me').status_code == 401
    assert post(c, '/auth/login', {'email': 'a0@example.test', 'password': PASSWORD}).status_code == 410
    assert post(c, '/auth/device-challenge').status_code == 410
    pending = c.cookies.get('maeum_email')
    code = latest_mail(purpose='login')['code']
    result = post(c, '/auth/email-login-verify', {'code': code})
    assert result.status_code == 200
    c.headers['X-CSRF-Token'] = result.json()['csrf']
    assert not c.cookies.get('maeum_email')
    assert c.cookies.get(auth.SESSION) != pending
    assert c.get('/api/portal/me').json()['registrar'] is True
    assert c.get('/api/portal/intakes?org_id=A').status_code == 200
    assert c.get('/api/portal/intakes?org_id=B').status_code == 403
    assert post(c, '/auth/email-login-verify', {'code': code}).status_code == 401
    assert post(c, '/auth/logout').status_code == 200
    assert c.get('/api/portal/me').status_code == 401


def test_email_registration_is_pending_until_owner_assigns_org(email_env):
    applicant = client()
    result = post(applicant, '/auth/apply', {'email': ' New.Person@example.test ', 'org_id': 'B', 'role': 'manager'})
    assert result.status_code == 200
    assert c_has_user(email_env, 'new.person@example.test') is False
    unknown = email_start(applicant, 'new.person@example.test')
    assert not list(Path(os.environ['PORTAL_MAIL_DIR']).glob('*.json'))
    assert post(applicant, '/auth/email-login-verify', {'code': '12345678'}).status_code == 400
    assert applicant.get('/api/portal/registrations').status_code == 401
    admin = client()
    email_enter(admin)
    directory = admin.get('/api/portal/registrations').json()
    assert directory['requests'][0]['email'] == 'new.person@example.test'
    assert post(admin, '/registrations', {'email': 'new.person@example.test', 'org_id': 'A', 'role': 'summary'}).status_code == 200
    with psycopg.connect(email_env['MAEUM_DATABASE_URL']) as conn:
        conn.execute('TRUNCATE maeum.portal_limits')
    known = email_start(applicant, 'new.person@example.test')
    assert known['message'] == unknown['message']
    code = latest_mail('new.person@example.test', 'login')['code']
    result = post(applicant, '/auth/email-login-verify', {'code': code})
    applicant.headers['X-CSRF-Token'] = result.json()['csrf']
    assert applicant.get('/api/portal/intakes?org_id=A').status_code == 200
    assert applicant.get('/api/portal/intakes?org_id=B').status_code == 403
    assert applicant.get('/api/portal/registrations').status_code == 403
    assert post(applicant, '/registrations', {'email': 'other@example.test', 'org_id': 'A', 'role': 'manager'}).status_code == 403
    assert post(applicant, '/registrations/reject', {'email': 'a0@example.test'}).status_code == 403


def test_email_session_persists_for_14_days_without_sliding(email_env):
    c = client()
    email_start(c)
    response = post(c, '/auth/email-login-verify', {'code': latest_mail(purpose='login')['code']})
    assert response.status_code == 200
    for name in [auth.SESSION, auth.NONCE]:
        header = next(v for v in response.headers.get_list('set-cookie') if v.startswith(name + '='))
        assert 'Max-Age=1209600' in header and 'HttpOnly' in header and 'SameSite=strict' in header
    session_hash = store.digest(c.cookies.get(auth.SESSION))
    with owner() as conn:
        created, expiry, device_expiry = conn.execute(
            'SELECT s.created_at,s.expires_at,d.expires_at FROM maeum.portal_sessions s '
            'JOIN maeum.trusted_devices d ON d.id=s.device_id WHERE s.token_hash=%s', (session_hash,)).fetchone()
        assert expiry - created == pytest.approx(14 * 86400)
        assert device_expiry == pytest.approx(expiry, abs=2, rel=0)
        # Simulate 13 days of inactivity while the fixed 14-day window remains open.
        old = time.time() - 13 * 86400
        expiry = time.time() + 86400
        conn.execute('UPDATE maeum.portal_sessions SET created_at=%s,seen_at=%s,expires_at=%s WHERE token_hash=%s',
                     (old, old, expiry, session_hash))
        conn.execute('UPDATE maeum.trusted_devices SET expires_at=%s', (expiry,))
    # A fresh HTTP client restoring the browser's persistent cookies needs no new email.
    restored = client()
    restored.cookies.update(c.cookies)
    with store.connect() as conn:
        store.context(conn, 'A0', 'A', 'report:read', session_hash)
        assert conn.execute("SELECT maeum.permitted('A','report:read') AS ok").fetchone()['ok']
    result = restored.get('/api/portal/me')
    assert result.status_code == 200 and result.json()['expires_at'] == expiry
    assert restored.get('/api/portal/intakes?org_id=A').status_code == 200
    assert restored.get('/api/portal/intakes?org_id=B').status_code == 403
    assert restored.get('/api/portal/registrations').status_code == 200
    assert len(list(Path(os.environ['PORTAL_MAIL_DIR']).glob('*.json'))) == 1
    with owner() as conn:
        assert conn.execute('SELECT expires_at FROM maeum.portal_sessions WHERE token_hash=%s', (session_hash,)).fetchone()[0] == expiry
    assert client().get('/api/portal/me').status_code == 401
    missing_nonce = client()
    missing_nonce.cookies.set(auth.SESSION, c.cookies.get(auth.SESSION))
    assert missing_nonce.get('/api/portal/me').status_code == 401


def test_email_session_absolute_14_day_expiry_requires_email_again(email_env):
    c = client()
    email_enter(c)
    with owner() as conn:
        conn.execute('UPDATE maeum.portal_sessions SET created_at=%s,expires_at=%s,seen_at=%s',
                     (time.time() - 14 * 86400 - 1, time.time() - 1, time.time()))
    assert c.get('/api/portal/me').status_code == 401
    assert c.get('/api/portal/intakes?org_id=A').status_code == 401
    with store.connect() as conn:
        with pytest.raises(auth.HTTPException) as error:
            store.context(conn, 'A0', 'A', 'report:read', store.digest(c.cookies.get(auth.SESSION)))
        assert error.value.status_code == 403


def test_email_existing_live_short_session_upgrades_from_original_login(email_env):
    c = client()
    email_enter(c)
    original_login = time.time() - 4 * 3600
    with owner() as conn:
        conn.execute('UPDATE maeum.portal_sessions SET created_at=%s,seen_at=%s,expires_at=%s',
                     (original_login, original_login, original_login + 8 * 3600))
        conn.execute('UPDATE maeum.trusted_devices SET expires_at=%s', (original_login + 8 * 3600,))
    response = c.get('/api/portal/me')
    assert response.status_code == 200
    deadline = original_login + 14 * 86400
    assert response.json()['expires_at'] == deadline
    for name in [auth.SESSION, auth.NONCE]:
        header = next(v for v in response.headers.get_list('set-cookie') if v.startswith(name + '='))
        max_age = int(header.split('Max-Age=')[1].split(';')[0])
        assert 14 * 86400 - 4 * 3600 - 30 <= max_age <= 14 * 86400 - 4 * 3600
    assert c.get('/api/portal/intakes?org_id=A').status_code == 200
    assert not c.get('/api/portal/me').headers.get_list('set-cookie')
    with owner() as conn:
        assert conn.execute('SELECT expires_at FROM maeum.trusted_devices').fetchone()[0] == deadline
    assert len(list(Path(os.environ['PORTAL_MAIL_DIR']).glob('*.json'))) == 1


def test_email_expired_short_session_is_not_revived(email_env):
    c = client()
    email_enter(c)
    with owner() as conn:
        conn.execute('UPDATE maeum.portal_sessions SET created_at=%s,seen_at=%s,expires_at=%s',
                     (time.time() - 9 * 3600, time.time() - 9 * 3600, time.time() - 3600))
    response = c.get('/api/portal/me')
    assert response.status_code == 401
    assert not response.headers.get_list('set-cookie')


@pytest.mark.parametrize('change', ['logout', 'device', 'user', 'version', 'membership', 'registrar'])
def test_email_persistent_session_still_respects_revocation(email_env, change):
    c = client()
    email_enter(c)
    if change == 'logout':
        assert post(c, '/auth/logout').status_code == 200
    elif change == 'device':
        device = c.get('/api/portal/devices').json()[0]['id']
        assert post(c, '/devices/' + device, method='DELETE').status_code == 200
    else:
        with owner() as conn:
            statements = {'user': "UPDATE maeum.portal_users SET active=false WHERE id='A0'",
                          'version': "UPDATE maeum.portal_users SET auth_version=auth_version+1 WHERE id='A0'",
                          'membership': "UPDATE maeum.memberships SET active=false WHERE user_id='A0'",
                          'registrar': "UPDATE maeum.portal_users SET is_registrar=false WHERE id='A0'"}
            conn.execute(statements[change])
    # Organization membership and the global registrar role are independent grants.
    assert c.get('/api/portal/intakes?org_id=A').status_code in ({200} if change == 'registrar' else {401, 403})
    assert c.get('/api/portal/registrations').status_code in ({200} if change == 'membership' else {401, 403})


def test_email_session_policy_caps_at_two_weeks(email_env, monkeypatch):
    from app.portal_config import Policy
    monkeypatch.setenv('PORTAL_EMAIL_SESSION_SECONDS', str(14 * 86400 + 1))
    with pytest.raises(RuntimeError, match='cannot exceed 14 days'):
        Policy.load()


def c_has_user(env, email):
    with psycopg.connect(env['MAEUM_DATABASE_URL']) as conn:
        return conn.execute('SELECT 1 FROM maeum.portal_users WHERE email=%s', (email,)).fetchone() is not None


def test_email_gmail_domain_and_sender_allowlist(email_env, monkeypatch):
    monkeypatch.setenv('PORTAL_EMAIL_DOMAINS', 'gmail.com')
    monkeypatch.setenv('PORTAL_EMAIL_SEND_ALLOWLIST', 'owner@gmail.com')
    c = client()
    for address in ['person@example.test', 'person@gmail.com.evil.test', 'person@googlemail.com']:
        assert post(c, '/auth/apply', {'email': address}).status_code == 400
        assert post(c, '/auth/email-start', {'email': address}).status_code == 400
    assert post(c, '/auth/apply', {'email': ' Applicant@GMAIL.COM '}).status_code == 200
    assert c_has_user(email_env, 'applicant@gmail.com') is False
    with psycopg.connect(email_env['MAEUM_DATABASE_URL']) as conn:
        conn.execute("UPDATE maeum.portal_users SET email='other@gmail.com' WHERE id='A0'")
    email_start(c, 'other@gmail.com')
    assert not list(Path(os.environ['PORTAL_MAIL_DIR']).glob('*.json'))
    assert post(c, '/auth/email-login-verify', {'code': '12345678'}).status_code == 400


@pytest.mark.parametrize('failure', [None, 'state', 'nonce', 'csrf', 'expiry', 'identity', 'membership', 'mode',
                                   'user', 'email', 'provider_ready', 'attempts', 'row_mode'])
def test_passwordless_link_pkce_boundaries(provider_env, monkeypatch, failure):
    c, sent, provider = provider_env
    monkeypatch.setenv('PORTAL_EMAIL_LOGIN', '1')
    monkeypatch.setenv('PORTAL_EMAIL_DELIVERY', 'link')
    result = email_start(c)
    assert result['state'] == 'email_link'
    assert c.get('/api/portal/auth/email-pending').json()['state'] == 'email_link'
    assert '이메일 로그인 링크 받기' in c.get('/portal').text
    assert c.get('/portal/email-return').status_code == 200
    assert post(c, '/auth/email-login-verify', {'code':'12345678'}).status_code == 404
    payload = {'code':'synthetic-valid-auth-code', 'state':sent['state']}
    original_session = store.digest(c.cookies.get(auth.SESSION))
    expected = 400
    if failure == 'state':
        payload['state'] = 'x' * 43
    elif failure == 'nonce':
        c.cookies.set('maeum_email', 'wrong', domain='portal.example.test', path='/')
        c.cookies.set('maeum_email_browser', 'wrong', domain='portal.example.test', path='/')
        c.headers['X-CSRF-Token'] = 'wrong'
        expected = 200
    elif failure == 'csrf':
        c.headers['Origin'] = 'https://foreign.example.test'
        expected = 403
    elif failure in ['expiry', 'identity', 'membership', 'user', 'email', 'provider_ready', 'attempts', 'row_mode']:
        with psycopg.connect(os.environ['MAEUM_DATABASE_URL']) as conn:
            statement = {'expiry':'UPDATE maeum.email_login_attempts SET expires_at=0',
                         'identity':"UPDATE maeum.portal_users SET auth_version=auth_version+1 WHERE id='A0'",
                         'membership':"UPDATE maeum.memberships SET active=false WHERE user_id='A0'",
                         'user':"UPDATE maeum.portal_users SET active=false WHERE id='A0'",
                         'email':"UPDATE maeum.portal_users SET email='changed@example.test' WHERE id='A0'",
                         'provider_ready':'UPDATE maeum.email_login_attempts SET provider_ready=false',
                         'attempts':'UPDATE maeum.email_login_attempts SET attempts=5',
                         'row_mode':"UPDATE maeum.email_login_attempts SET code_mac='code-v1:wrong'"}[failure]
            conn.execute(statement)
    elif failure == 'mode':
        monkeypatch.setenv('PORTAL_EMAIL_DELIVERY', 'code')
        assert c.get('/api/portal/auth/email-pending').status_code == 401
        assert post(c, '/auth/email-login-verify', {'code':'12345678'}).status_code == 400
        expected = 404
    response = post(c, '/auth/email-exchange', payload)
    assert response.status_code == (200 if failure is None else expected), response.text
    if response.status_code == 200:
        c.headers['X-CSRF-Token'] = response.json()['csrf']
        assert c.get('/api/portal/intakes?org_id=A').status_code == 200
        assert c.get('/api/portal/intakes?org_id=B').status_code == 403
        assert post(c, '/auth/email-exchange', payload).status_code == 400
        with psycopg.connect(os.environ['MAEUM_DATABASE_URL']) as conn:
            assert conn.execute('SELECT revoked FROM maeum.portal_sessions WHERE token_hash=%s',
                                (original_session,)).fetchone() == (True,)


@pytest.mark.parametrize('stale_cookies', [False, True])
def test_passwordless_link_other_browser(provider_env, monkeypatch, stale_cookies):
    from app import portal_email
    from app.portal_config import Policy
    c, sent, _ = provider_env
    monkeypatch.setenv('PORTAL_EMAIL_LOGIN', '1')
    monkeypatch.setenv('PORTAL_EMAIL_DELIVERY', 'link')
    c.cookies.clear()
    c.headers.pop('X-CSRF-Token')
    result = email_start(c)
    assert result['message'] == ('발송 가능한 등록 이메일이라면 로그인 링크를 보냈습니다. '
                                 '10분 안에 메일의 링크를 누르면 휴대폰 메일 앱에서도 바로 로그인됩니다.')
    other = TestClient(app, base_url=c.base_url, headers={'Origin':str(c.base_url).rstrip('/')})
    assert not other.cookies and 'X-CSRF-Token' not in other.headers
    if stale_cookies:
        for name in [portal_email.ATTEMPT, portal_email.BROWSER, auth.DEVICE]:
            other.cookies.set(name, 'stale', domain='portal.example.test', path='/')
    payload = {'code':'synthetic-valid-auth-code', 'state':sent['state']}
    response = post(other, '/auth/email-exchange', payload)
    assert response.status_code == 200, response.text
    for name in [auth.SESSION, auth.NONCE]:
        header = next(v for v in response.headers.get_list('set-cookie') if v.startswith(name + '='))
        assert f'Max-Age={Policy.load().email_session_seconds}' in header
        assert 'HttpOnly' in header and 'Secure' in header and 'SameSite=strict' in header
        assert other.cookies.get(name)
    assert all(not other.cookies.get(name) for name in [portal_email.ATTEMPT, portal_email.BROWSER, auth.DEVICE])
    assert other.get('/api/portal/intakes?org_id=A').status_code == 200
    assert other.get('/api/portal/intakes?org_id=B').status_code == 403
    assert post(other, '/auth/email-exchange', payload).status_code == 400
    assert c.get('/api/portal/me').status_code == 401
    assert c.get('/api/portal/intakes?org_id=A').status_code == 401
    with psycopg.connect(os.environ['MAEUM_DATABASE_URL']) as conn:
        assert conn.execute('SELECT attempts,consumed FROM maeum.email_login_attempts').fetchone() == (1, True)


def test_passwordless_link_first_mapping_and_single_use(provider_env, monkeypatch):
    import base64
    from urllib.parse import parse_qs
    c, _, provider = provider_env
    monkeypatch.setenv('PORTAL_EMAIL_LOGIN', '1')
    monkeypatch.setenv('PORTAL_EMAIL_DELIVERY', 'link')
    with psycopg.connect(os.environ['MAEUM_DATABASE_URL']) as conn:
        conn.execute("UPDATE maeum.portal_users SET supabase_user_id=NULL WHERE id='A0'")
    identity, sent, calls = str(uuid4()), {}, []
    def api(path, body, **kwargs):
        calls.append(path)
        if path.startswith('/otp?'):
            redirect = parse_qs(path.split('?',1)[1])['redirect_to'][0]
            assert urlparse(redirect).path == '/portal/email-return'
            assert body['create_user'] is True
            sent.update(state=parse_qs(urlparse(redirect).query)['state'][0],challenge=body['code_challenge'])
            return {}
        if path == '/token?grant_type=pkce':
            assert base64.urlsafe_b64encode(hashlib.sha256(body['code_verifier'].encode()).digest()).decode().rstrip('=') == sent['challenge']
            return {'user':{'id':identity,'email':'a0@example.test','email_confirmed_at':'2026-11-04'},'access_token':'synthetic'}
        assert path.startswith('/logout')
        return {}
    monkeypatch.setattr(provider, 'request_api', api)
    email_start(c)
    copies = [TestClient(app,base_url=c.base_url,headers={'Origin':str(c.base_url).rstrip('/')}) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda copy:post(copy,'/auth/email-exchange',{'code':'synthetic-valid-auth-code','state':sent['state']}).status_code,copies))
    assert sorted(statuses) == [200,400]
    assert calls == [calls[0], '/token?grant_type=pkce', '/logout?scope=local']
    with psycopg.connect(os.environ['MAEUM_DATABASE_URL']) as conn:
        assert str(conn.execute("SELECT supabase_user_id FROM maeum.portal_users WHERE id='A0'").fetchone()[0]) == identity


def test_passwordless_link_failed_codes_commit_attempt_limit(provider_env, monkeypatch):
    c, sent, _ = provider_env
    monkeypatch.setenv('PORTAL_EMAIL_LOGIN', '1')
    monkeypatch.setenv('PORTAL_EMAIL_DELIVERY', 'link')
    email_start(c)
    other = TestClient(app, base_url=c.base_url, headers={'Origin':str(c.base_url).rstrip('/')})
    for _ in range(5):
        assert post(other, '/auth/email-exchange', {'code':'synthetic-wrong-auth-code', 'state':sent['state']}).status_code == 400
    assert post(other, '/auth/email-exchange', {'code':'synthetic-valid-auth-code', 'state':sent['state']}).status_code == 400
    with psycopg.connect(os.environ['MAEUM_DATABASE_URL']) as conn:
        assert conn.execute('SELECT attempts,consumed FROM maeum.email_login_attempts').fetchone() == (5, True)
    assert other.get('/api/portal/me').status_code == 401


def test_email_code_wrong_nonce_csrf_attempts_and_expiry(email_env):
    c = client()
    email_start(c)
    code = latest_mail(purpose='login')['code']
    other = client()
    assert post(other, '/auth/email-login-verify', {'code': code}).status_code == 401
    saved = c.headers['X-CSRF-Token']
    c.headers['X-CSRF-Token'] = 'wrong'
    assert post(c, '/auth/email-login-verify', {'code': code}).status_code == 403
    c.headers['X-CSRF-Token'] = saved
    for _ in range(5):
        assert post(c, '/auth/email-login-verify', {'code': ('0' * 8 if code != '0' * 8 else '1' * 8)}).status_code == 400
    assert post(c, '/auth/email-login-verify', {'code': code}).status_code == 400
    with psycopg.connect(email_env['MAEUM_DATABASE_URL']) as conn:
        row = conn.execute('SELECT attempts,consumed FROM maeum.email_login_attempts WHERE email=%s', ('a0@example.test',)).fetchone()
        assert row == (5, True)
        conn.execute('TRUNCATE maeum.portal_limits')
    email_start(c)
    code = latest_mail(purpose='login')['code']
    with psycopg.connect(email_env['MAEUM_DATABASE_URL']) as conn:
        conn.execute('UPDATE maeum.email_login_attempts SET expires_at=0')
    assert post(c, '/auth/email-login-verify', {'code': code}).status_code == 400


@pytest.mark.parametrize('change', ['member', 'identity', 'user'])
def test_email_rechecks_membership_and_identity_at_verify(email_env, change):
    # Ordinary staff still require an active institution; system admins are separate.
    with psycopg.connect(email_env['MAEUM_DATABASE_URL']) as conn:
        conn.execute("UPDATE maeum.portal_users SET is_registrar=false WHERE id='A0'")
    c = client()
    email_start(c)
    code = latest_mail(purpose='login')['code']
    with psycopg.connect(email_env['MAEUM_DATABASE_URL']) as conn:
        if change == 'member':
            conn.execute("UPDATE maeum.memberships SET active=false WHERE user_id='A0'")
        elif change == 'identity':
            conn.execute("UPDATE maeum.portal_users SET auth_version=auth_version+1 WHERE id='A0'")
        else:
            conn.execute("UPDATE maeum.portal_users SET active=false WHERE id='A0'")
    assert post(c, '/auth/email-login-verify', {'code': code}).status_code == 400
    assert c.get('/api/portal/me').status_code == 401


def test_email_code_concurrent_single_success_and_cancel(email_env):
    c = client()
    email_start(c)
    code = latest_mail(purpose='login')['code']
    copies = [client(), client()]
    for copy in copies:
        copy.cookies.update(c.cookies)
        copy.headers['X-CSRF-Token'] = c.headers['X-CSRF-Token']
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda copy: post(copy, '/auth/email-login-verify', {'code': code}).status_code, copies))
    assert sorted(statuses) == [200, 400]
    with psycopg.connect(email_env['MAEUM_DATABASE_URL']) as conn:
        conn.execute('TRUNCATE maeum.portal_limits')
    email_start(c)
    code = latest_mail(purpose='login')['code']
    assert post(c, '/auth/email-cancel').status_code == 200
    assert post(c, '/auth/email-login-verify', {'code': code}).status_code == 401


def test_email_directory_reject_and_disabled_account_protection(email_env):
    c = client()
    email_enter(c)
    assert post(client(), '/auth/apply', {'email': 'declined@example.test'}).status_code == 200
    assert post(c, '/registrations/reject', {'email': 'declined@example.test'}).status_code == 200
    assert c.get('/api/portal/registrations').json()['requests'] == []
    assert post(c, '/registrations', {'email': 'valid@example.test', 'org_id': 'missing', 'role': 'summary'}).status_code == 404
    assert post(c, '/registrations', {'email': 'valid@example.test', 'org_id': 'A', 'role': 'superuser'}).status_code == 400
    with psycopg.connect(email_env['MAEUM_DATABASE_URL']) as conn:
        conn.execute("UPDATE maeum.portal_users SET active=false WHERE id='A1'")
    assert post(c, '/registrations', {'email': 'a1@example.test', 'org_id': 'A', 'role': 'manager'}).status_code == 409
    with store.connect() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('SELECT * FROM maeum.registration_requests')


def test_registrar_manages_organizations(email_env):
    c = client()
    email_enter(c)
    listed = c.get('/api/portal/organizations').json()['organizations']
    assert {o['id'] for o in listed} == {'A', 'B'} and all(o['active'] for o in listed)
    assert {o['id']: o['members'] for o in listed} == {'A': 3, 'B': 2}
    created = post(c, '/organizations', {'name': '  새 상담센터  '})
    assert created.status_code in {200, 201}, created.text
    org_id = created.json()['id']
    assert len(org_id) == 16 and org_id.startswith('org-') and org_id[4:] == org_id[4:].lower() and int(org_id[4:], 16) >= 0
    listed = c.get('/api/portal/organizations').json()['organizations']
    assert [o for o in listed if o['id'] == org_id] == [{'id': org_id, 'name': '새 상담센터', 'active': True, 'members': 0}]
    assert org_id in {o['id'] for o in c.get('/api/portal/registrations').json()['organizations']}
    # A new institution accepts a pre-registration.
    assert post(c, '/registrations', {'email': 'fresh@example.test', 'org_id': org_id, 'role': 'summary'}).status_code == 200
    assert next(o for o in c.get('/api/portal/organizations').json()['organizations'] if o['id'] == org_id)['members'] == 1
    assert post(c, f'/organizations/{org_id}', {'name': '이름 바꾼 센터', 'active': True}, 'PATCH').status_code == 200
    assert next(o for o in c.get('/api/portal/organizations').json()['organizations'] if o['id'] == org_id)['name'] == '이름 바꾼 센터'
    assert post(c, f'/organizations/{org_id}', {'name': '이름 바꾼 센터', 'active': False}, 'PATCH').status_code == 200
    assert org_id not in {o['id'] for o in c.get('/api/portal/registrations').json()['organizations']}
    assert next(o for o in c.get('/api/portal/organizations').json()['organizations'] if o['id'] == org_id)['active'] is False
    assert post(c, '/registrations', {'email': 'later@example.test', 'org_id': org_id, 'role': 'summary'}).status_code == 404
    assert post(c, f'/organizations/{org_id}', {'name': '이름 바꾼 센터', 'active': True}, 'PATCH').status_code == 200
    assert org_id in {o['id'] for o in c.get('/api/portal/registrations').json()['organizations']}
    with psycopg.connect(email_env['MAEUM_DATABASE_URL']) as conn:
        assert conn.execute("SELECT count(*) FROM maeum.audit_events WHERE org_id=%s AND action IN ('org_create','org_update')", (org_id,)).fetchone()[0] == 4


def test_organization_validation_and_authorization(email_env):
    c = client()
    email_enter(c)
    for name in ['', '   ', 'x' * 81, 5, None, 'bad\x07name']:
        assert post(c, '/organizations', {'name': name}).status_code == 400
    assert post(c, '/organizations', {'name': 'x' * 80}).status_code == 200
    assert post(c, '/organizations', {'name': '합성 a 상담기관'}).status_code == 409
    assert post(c, '/organizations', {'name': ' 합성 B 상담기관 '}).status_code == 409
    assert post(c, '/organizations/A', {'name': '합성 B 상담기관', 'active': True}, 'PATCH').status_code == 409
    assert post(c, '/organizations/A', {'name': '합성 A 상담기관', 'active': True}, 'PATCH').status_code == 200
    assert post(c, '/organizations/A', {'name': '', 'active': True}, 'PATCH').status_code == 400
    assert post(c, '/organizations/A', {'name': 'y' * 81, 'active': True}, 'PATCH').status_code == 400
    for active in ['true', 1, None]:
        assert post(c, '/organizations/A', {'name': '합성 A 상담기관', 'active': active}, 'PATCH').status_code == 400
    assert post(c, '/organizations/A', {'name': '합성 A 상담기관'}, 'PATCH').status_code == 400
    assert post(c, '/organizations/missing', {'name': '없는 기관', 'active': True}, 'PATCH').status_code == 404
    for header, value in (('Origin', 'http://evil.test'), ('X-CSRF-Token', 'wrong')):
        saved = c.headers[header]
        c.headers[header] = value
        assert post(c, '/organizations', {'name': '거절될 기관'}).status_code == 403
        assert post(c, '/organizations/A', {'name': '거절될 기관', 'active': True}, 'PATCH').status_code == 403
        c.headers[header] = saved
    staff = client()
    email_enter(staff, 'a1@example.test')
    assert staff.get('/api/portal/organizations').status_code == 403
    assert post(staff, '/organizations', {'name': '직원이 만든 기관'}).status_code == 403
    assert post(staff, '/organizations/A', {'name': '직원이 바꾼 이름', 'active': False}, 'PATCH').status_code == 403
    assert client().get('/api/portal/organizations').status_code == 401
    names = [o['name'] for o in c.get('/api/portal/organizations').json()['organizations']]
    assert '직원이 만든 기관' not in names and '직원이 바꾼 이름' not in names and '거절될 기관' not in names
    with store.connect() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT maeum.create_organization('x','y')")


def test_organization_endpoints_need_email_mode(env):
    c = verified()
    assert c.get('/api/portal/organizations').status_code == 404
    assert post(c, '/organizations', {'name': '기관'}).status_code == 404


def test_owner_cannot_revoke_own_membership_or_manage_permission(env):
    a = verified()
    full = ['report:read', 'raw:read', 'review:write', 'link:issue', 'member:manage', 'audit:read']
    assert post(a, '/members/A0', {'org_id': 'A', 'permissions': full, 'active': False}, 'PATCH').status_code == 409
    assert post(a, '/members/A0', {'org_id': 'A', 'permissions': ['report:read'], 'active': True}, 'PATCH').status_code == 409
    assert post(a, '/members/A0', {'org_id': 'A', 'permissions': ['report:read'], 'active': False}, 'PATCH').status_code == 409
    with owner() as conn:
        assert conn.execute("SELECT active,permissions FROM maeum.memberships WHERE org_id='A' AND user_id='A0'").fetchone() == (True, full)
    # Other members, and the owner's other non-management permissions, are unchanged.
    assert post(a, '/members/A1', {'org_id': 'A', 'permissions': ['report:read'], 'active': False}, 'PATCH').status_code == 200
    assert post(a, '/members/A0', {'org_id': 'A', 'permissions': full[:1] + ['member:manage'], 'active': True}, 'PATCH').status_code == 200


def test_email_provider_passwordless_boundary(provider_env, monkeypatch):
    c, _, provider = provider_env
    monkeypatch.setenv('PORTAL_EMAIL_LOGIN', '1')
    with psycopg.connect(os.environ['MAEUM_DATABASE_URL']) as conn:
        uid = str(conn.execute("SELECT supabase_user_id FROM maeum.portal_users WHERE id='A0'").fetchone()[0])
    calls = []
    def otp_api(path, body, **kwargs):
        calls.append((path, body))
        if path == '/otp':
            assert body == {'email': 'a0@example.test', 'create_user': False}
            return {}
        if path == '/verify':
            assert body['type'] == 'email' and body['email'] == 'a0@example.test'
            if body['token'] != '12345678':
                raise auth.HTTPException(401)
            return {'user': {'id': uid, 'email': 'a0@example.test', 'email_confirmed_at': '2026-11-04'}, 'access_token': 'synthetic-discard'}
        if path.startswith('/logout'):
            return {}
        raise AssertionError(path)
    monkeypatch.setattr(provider, 'request_api', otp_api)
    email_start(c)
    assert post(c, '/auth/email-login-verify', {'code': '00000000'}).status_code == 400
    result = post(c, '/auth/email-login-verify', {'code': '12345678'})
    assert result.status_code == 200, result.text
    assert any(path.startswith('/logout') for path, _ in calls)
    assert all(cookie.secure for cookie in c.cookies.jar)
    assert not any('password' in body for _, body in calls)


def test_email_provider_failure_keeps_quota_and_unknown_is_not_created(provider_env, monkeypatch):
    c, _, provider = provider_env
    monkeypatch.setenv('PORTAL_EMAIL_LOGIN', '1')
    calls = []
    def failing(path, body, **kwargs):
        calls.append(path)
        raise auth.HTTPException(503)
    monkeypatch.setattr(provider, 'request_api', failing)
    email_start(c)
    for _ in range(3):
        assert post(c, '/auth/email-start', {'email': 'a0@example.test'}).status_code == 429
    assert calls == ['/otp']
    stranger = client()
    stranger.base_url = c.base_url
    stranger.headers['Origin'] = str(c.base_url).rstrip('/')
    email_start(stranger, 'unknown@example.test')
    assert calls == ['/otp']
    assert c_has_user({'MAEUM_DATABASE_URL': os.environ['MAEUM_DATABASE_URL']}, 'unknown@example.test') is False


@pytest.mark.parametrize('failure', [429, 503, 401, 'oserror'])
def test_email_link_provider_failure_is_reported_and_keeps_quota(provider_env, monkeypatch, capsys, failure):
    c, _, provider = provider_env
    monkeypatch.setenv('PORTAL_EMAIL_LOGIN', '1')
    monkeypatch.setenv('PORTAL_EMAIL_DELIVERY', 'link')
    monkeypatch.setenv('PORTAL_EMAIL_SEND_ALLOWLIST', 'a0@example.test,unknown@example.test')
    calls = []
    def failing(path, body, **kwargs):
        calls.append(path)
        if failure == 'oserror':
            raise OSError('synthetic provider error containing private data')
        raise auth.HTTPException(failure, 'synthetic provider error containing private data')
    monkeypatch.setattr(provider, 'request_api', failing)
    response = post(c, '/auth/email-start', {'email':'a0@example.test'})
    expected = 429 if failure == 429 else 503
    assert response.status_code == expected
    assert response.json()['detail'] == ('인증 메일 발송 한도에 걸렸습니다. 잠시 후 다시 시도해 주세요.' if expected == 429
                                         else '인증 메일을 보내지 못했습니다. 잠시 후 다시 시도해 주세요.')
    with psycopg.connect(os.environ['MAEUM_DATABASE_URL']) as conn:
        assert conn.execute('SELECT provider_ready FROM maeum.email_login_attempts WHERE email=%s',
                            ('a0@example.test',)).fetchone() == (False,)
        for key in ['email-login-hour:' + store.digest('a0@example.test'),
                    'email-login-cooldown:' + store.digest('a0@example.test'), 'email-provider-project']:
            assert len(conn.execute('SELECT stamps FROM maeum.portal_limits WHERE id=%s', (key,)).fetchone()[0]) == 1
    assert post(c, '/auth/email-start', {'email':'a0@example.test'}).status_code == 429
    unknown = email_start(c, 'unknown@example.test')
    excluded = email_start(c, 'a1@example.test')
    assert unknown['message'] == excluded['message']
    assert unknown['state'] == excluded['state'] == 'email_link'
    assert len(calls) == 1
    assert c_has_user({'MAEUM_DATABASE_URL':os.environ['MAEUM_DATABASE_URL']}, 'unknown@example.test') is False
    assert capsys.readouterr().out == json.dumps({'event':'portal_email_provider_failure',
                                                'status':503 if failure == 'oserror' else failure}) + '\n'


def test_email_link_address_hourly_limit_uses_policy(provider_env, monkeypatch):
    c, _, _ = provider_env
    monkeypatch.setenv('PORTAL_EMAIL_LOGIN', '1')
    monkeypatch.setenv('PORTAL_EMAIL_DELIVERY', 'link')
    monkeypatch.setenv('PORTAL_SENDS_PER_HOUR', '5')
    monkeypatch.setenv('PORTAL_PROVIDER_EMAILS_PER_HOUR', '10')
    original_limit = auth.limit
    def without_cooldown(key, *args, **kwargs):
        if not key.startswith('email-login-cooldown:'):
            return original_limit(key, *args, **kwargs)
    monkeypatch.setattr(auth, 'limit', without_cooldown)
    for _ in range(5):
        response = post(c, '/auth/email-start', {'email':'a0@example.test'})
        assert response.status_code == 200, response.text
    assert post(c, '/auth/email-start', {'email':'a0@example.test'}).status_code == 429


@pytest.mark.parametrize('delivery', ['code', 'link'])
@pytest.mark.parametrize('mismatch', ['email', 'id', 'unconfirmed'])
def test_email_provider_rejects_identity_mismatch(provider_env, monkeypatch, mismatch, delivery):
    c, sent, provider = provider_env
    monkeypatch.setenv('PORTAL_EMAIL_LOGIN', '1')
    monkeypatch.setenv('PORTAL_EMAIL_DELIVERY', delivery)
    uid = str(uuid4())
    with psycopg.connect(os.environ['MAEUM_DATABASE_URL']) as conn:
        expected = str(conn.execute("SELECT supabase_user_id FROM maeum.portal_users WHERE id='A0'").fetchone()[0])
    original_api = provider.request_api
    def otp_api(path, body, **kwargs):
        if path.startswith('/otp?'):
            return original_api(path, body, **kwargs)
        if path == '/otp' or path.startswith('/logout'):
            return {}
        return {'access_token':'synthetic', 'user': {
            'id': uid if mismatch == 'id' else expected,
            'email': 'foreign@example.test' if mismatch == 'email' else 'a0@example.test',
            'email_confirmed_at': None if mismatch == 'unconfirmed' else '2026-11-04'}}
    monkeypatch.setattr(provider, 'request_api', otp_api)
    email_start(c)
    if delivery == 'link':
        assert post(c, '/auth/email-exchange', {'code':'synthetic-valid-auth-code', 'state':sent['state']}).status_code == 400
    else:
        assert post(c, '/auth/email-login-verify', {'code': '12345678'}).status_code == 400
    with psycopg.connect(os.environ['MAEUM_DATABASE_URL']) as conn:
        assert conn.execute('SELECT attempts,consumed FROM maeum.email_login_attempts').fetchone() == (1, False)
    assert c.get('/api/portal/me').json()['state'] == 'pending_device'


def test_email_provider_first_preregistered_identity_binding(provider_env, monkeypatch):
    c, _, provider = provider_env
    monkeypatch.setenv('PORTAL_EMAIL_LOGIN', '1')
    uid = str(uuid4())
    with psycopg.connect(os.environ['MAEUM_DATABASE_URL']) as conn:
        conn.execute("INSERT INTO maeum.portal_users(id,email) VALUES('NEW','first@example.test')")
        conn.execute("INSERT INTO maeum.memberships(org_id,user_id,permissions) VALUES('A','NEW',ARRAY['report:read'])")
    calls = []
    def otp_api(path, body, **kwargs):
        calls.append(path)
        if path == '/otp':
            assert body == {'email': 'first@example.test', 'create_user': True}
            return {}
        if path == '/verify':
            assert body == {'email': 'first@example.test', 'token': '12345678', 'type': 'email'}
            return {'user': {'id': uid, 'email': 'first@example.test', 'email_confirmed_at': '2026-11-04'}, 'access_token': 'synthetic'}
        if path.startswith('/logout'):
            return {}
        raise AssertionError(path)
    monkeypatch.setattr(provider, 'request_api', otp_api)
    email_start(c, 'first@example.test')
    result = post(c, '/auth/email-login-verify', {'code': '12345678'})
    assert result.status_code == 200, result.text
    with psycopg.connect(os.environ['MAEUM_DATABASE_URL']) as conn:
        assert str(conn.execute("SELECT supabase_user_id FROM maeum.portal_users WHERE id='NEW'").fetchone()[0]) == uid
    assert c.get('/api/portal/me').json()['organizations'][0]['id'] == 'A'
    assert c.get('/api/portal/intakes?org_id=B').status_code == 403
    assert calls == ['/otp', '/verify', '/logout?scope=local']


@pytest.fixture(scope="module")
def database():
    config = json.loads(Path(os.environ["PORTAL_TEST_CONFIG"]).read_text())
    original = urlparse(config["MAEUM_DATABASE_URL"])
    assert original.hostname == "127.0.0.1" and original.path.startswith("/maeum_test_")
    name = "maeum_test_" + uuid4().hex[:12]
    admin_url = urlunparse(original._replace(path="/postgres"))
    owner_url = urlunparse(original._replace(path="/" + name))
    runtime_url = urlunparse(urlparse(config["PORTAL_DATABASE_URL"])._replace(path="/" + name))
    auth_url = urlunparse(urlparse(config["PORTAL_AUTH_DATABASE_URL"])._replace(path="/" + name))
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    with psycopg.connect(owner_url) as conn:
        for filename in ("202611040001_cloud_store.sql", "202611040002_portal.sql", "202611040003_portal_sources_identity.sql", "202611040004_portal_runtime_boundary.sql", "202611040005_portal_cloud_identity.sql", "202611040006_email_login.sql", "202611050001_org_admin.sql", "202611050002_registrar_login.sql"):
            conn.execute((Path("supabase/migrations") / filename).read_text())
    yield config | {"MAEUM_DATABASE_URL": owner_url, "PORTAL_DATABASE_URL": runtime_url, "PORTAL_AUTH_DATABASE_URL": auth_url}
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


@pytest.fixture
def env(database, monkeypatch, tmp_path):
    for key, value in database.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("PORTAL_ORIGIN", ORIGIN)
    monkeypatch.setenv("PORTAL_MAIL_DIR", str(tmp_path / "mail"))
    with psycopg.connect(database["MAEUM_DATABASE_URL"]) as conn:
        conn.execute("TRUNCATE maeum.records,maeum.organizations,maeum.portal_users,maeum.portal_limits CASCADE")
        seed(conn, PASSWORD)
    chat._sessions.clear()
    yield database
    chat._sessions.clear()


def client():
    return TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})


def post(c, path, body=None, method="POST"):
    return c.request(method, "/api/portal" + path, json=body or {})


def login(c, email="a0@example.test"):
    r = post(c, "/auth/login", {"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    return r.json()


def latest_mail(email="a0@example.test", purpose="device"):
    messages = [json.loads(p.read_text()) for p in Path(os.environ["PORTAL_MAIL_DIR"]).glob("*.json")]
    messages = [m for m in messages if m["to"] == email and m["purpose"] == purpose]
    return max(messages, key=lambda m: m.get("created_at", 0))


@pytest.fixture
def provider_env(env, monkeypatch):
    """Real isolated DB + provider boundary stub; never sends email."""
    from app import portal_supabase as provider
    from urllib.parse import parse_qs
    import base64
    origin = 'https://portal.example.test'
    monkeypatch.setenv('PORTAL_AUTH_PROVIDER', 'supabase')
    monkeypatch.setenv('PORTAL_LOCAL_TEST', '0')
    monkeypatch.setenv('PORTAL_ORIGIN', origin)
    monkeypatch.setenv('PUBLIC_CHAT_UI', '1')
    monkeypatch.setenv('SUPABASE_URL', 'https://ojhuuipsyxewtiubujom.supabase.co')
    monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY', 'sb_publishable_synthetic')
    monkeypatch.setattr(store, 'require_database_url', lambda url: None)
    original_connect = psycopg.connect
    def local_connect(url, **kwargs):
        assert urlparse(url).hostname == '127.0.0.1'
        kwargs['sslmode'] = 'disable'
        return original_connect(url, **kwargs)
    monkeypatch.setattr(psycopg, 'connect', local_connect)
    uid = str(uuid4())
    with psycopg.connect(env['MAEUM_DATABASE_URL']) as conn:
        if conn.execute("SELECT to_regclass('auth.users') IS NOT NULL").fetchone()[0]:
            conn.execute('INSERT INTO auth.users(id,email) VALUES(%s,%s)', (uid, 'a0@example.test'))
        conn.execute('UPDATE maeum.portal_users SET supabase_user_id=%s WHERE id=%s', (uid, 'A0'))
    sent = {}
    def api(path, body, **kwargs):
        user = {'id': uid, 'email': 'a0@example.test', 'email_confirmed_at': '2026-11-04'}
        if path.startswith('/logout'):
            return {}
        if path == '/token?grant_type=password':
            if body['password'] != PASSWORD:
                raise auth.HTTPException(401)
            return {'user': user, 'access_token': 'synthetic-provider-token'}
        if path.startswith('/otp?'):
            redirect = parse_qs(path.split('?', 1)[1])['redirect_to'][0]
            sent.update(state=parse_qs(urlparse(redirect).query)['state'][0], challenge=body['code_challenge'])
            assert body['create_user'] is False
            return {}
        if path == '/token?grant_type=pkce':
            actual = base64.urlsafe_b64encode(hashlib.sha256(body['code_verifier'].encode()).digest()).decode().rstrip('=')
            if body['auth_code'] != 'synthetic-valid-auth-code' or actual != sent['challenge']:
                raise auth.HTTPException(401)
            return {'user': user, 'access_token': 'synthetic-provider-token'}
        raise AssertionError('unexpected provider request')
    monkeypatch.setattr(provider, 'request_api', api)
    c = TestClient(app, base_url=origin, headers={'Origin': origin})
    login(c)
    return c, sent, provider


@pytest.fixture
def google_env(provider_env, monkeypatch):
    """Google authorization is simulated; all database access remains loopback."""
    import base64
    c, sent, provider = provider_env
    monkeypatch.setenv('PORTAL_EMAIL_LOGIN', '1')
    monkeypatch.setenv('PORTAL_GOOGLE_LOGIN', '1')
    monkeypatch.setenv('PORTAL_EMAIL_DELIVERY', 'link')
    monkeypatch.setenv('PORTAL_EMAIL_DOMAINS', 'gmail.com')
    with owner() as conn:
        uid = conn.execute("UPDATE maeum.portal_users SET email='a0@gmail.com' WHERE id='A0' RETURNING supabase_user_id").fetchone()[0]
    identity = {'id': str(uid), 'email': 'A0@GMAIL.COM', 'email_confirmed_at': '2026-11-04'}
    calls = []

    def api(path, body, **kwargs):
        calls.append((path, body, kwargs))
        if path == '/token?grant_type=pkce':
            actual = base64.urlsafe_b64encode(hashlib.sha256(body['code_verifier'].encode()).digest()).decode().rstrip('=')
            if body['auth_code'] != 'synthetic-valid-auth-code' or actual != sent['challenge']:
                raise auth.HTTPException(401)
            return {'user': dict(identity), 'access_token': 'synthetic-google-token'}
        if path == '/logout?scope=local':
            assert kwargs == {'access_token': 'synthetic-google-token'}
            return {}
        raise AssertionError('unexpected provider request: ' + path)

    monkeypatch.setattr(provider, 'request_api', api)
    c.headers.pop('X-CSRF-Token', None)
    return c, sent, provider, identity, calls


def google_start(c, sent):
    response = post(c, '/auth/google-start')
    assert response.status_code == 200, response.text
    params = parse_qs(urlparse(response.json()['url']).query)
    sent['challenge'] = params['code_challenge'][0]
    return response, params


def assert_google_state_cleared(c, response):
    assert not c.cookies.get('maeum_google_state')
    assert any(header.startswith('maeum_google_state=') and 'Max-Age=0' in header
               for header in response.headers.get_list('set-cookie'))


@pytest.mark.parametrize('email_flag,google_flag', [(None, None), ('1', None), (None, '1'), ('0', '1'), ('1', '0')])
def test_google_disabled_flags_return_404(provider_env, monkeypatch, email_flag, google_flag):
    c, _, _ = provider_env
    for name, value in [('PORTAL_EMAIL_LOGIN', email_flag), ('PORTAL_GOOGLE_LOGIN', google_flag)]:
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    assert post(c, '/auth/google-start').status_code == 404
    assert post(c, '/auth/google-exchange', {'code': 'synthetic-valid-auth-code'}).status_code == 404
    assert c.get('/portal/google-return').status_code == 404
    assert c.get('/api/portal/me').json()['google_login'] is False
    html = c.get('/portal').text
    assert 'data-google-login="false"' in html
    assert 'id="email-login-details" open' in html
    assert 'id="google-login-options" hidden' in html


def test_google_requires_cloud(email_env, monkeypatch):
    monkeypatch.setenv('PORTAL_GOOGLE_LOGIN', '1')
    c = client()
    email_enter(c)
    assert post(c, '/auth/google-start').status_code == 404
    assert post(c, '/auth/google-exchange', {'code': 'synthetic-valid-auth-code'}).status_code == 404
    assert c.get('/portal/google-return').status_code == 404
    assert c.get('/api/portal/me').json()['google_login'] is False


def test_google_start_pkce_cookie_and_ui(google_env):
    import base64
    import hmac
    c, sent, _, _, calls = google_env
    assert c.post('/api/portal/auth/google-start', headers={'Origin': 'https://other.example.test'}).status_code == 403
    assert not c.cookies.get('maeum_google_state')
    response, params = google_start(c, sent)
    assert urlparse(response.json()['url'])._replace(query='').geturl() == os.environ['SUPABASE_URL'] + '/auth/v1/authorize'
    assert params['provider'] == ['google']
    assert params['redirect_to'] == ['https://portal.example.test/portal/google-return']
    assert params['code_challenge_method'] == ['s256']
    assert params['scopes'] == ['openid email profile']
    state = c.cookies.get('maeum_google_state')
    assert 32 <= len(state) <= 128
    expected = base64.urlsafe_b64encode(hmac.new(os.environ['PORTAL_CODE_SECRET'].encode(),
        json.dumps(['google-v1', state]).encode(), hashlib.sha256).digest()).decode().rstrip('=')
    assert sent['challenge'] == base64.urlsafe_b64encode(hashlib.sha256(expected.encode()).digest()).decode().rstrip('=')
    header = next(v for v in response.headers.get_list('set-cookie') if v.startswith('maeum_google_state='))
    assert all(part in header for part in ['Max-Age=600', 'HttpOnly', 'Secure', 'SameSite=strict', 'Path=/'])
    assert calls == []
    with owner() as conn:
        assert conn.execute('SELECT count(*) FROM maeum.email_login_attempts').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM maeum.portal_sessions').fetchone()[0] == 1
        key, stamps = conn.execute("SELECT id,stamps FROM maeum.portal_limits WHERE id LIKE 'google-start-peer:%'").fetchone()
        assert key == 'google-start-peer:' + store.digest('testclient') and len(stamps) == 1
    for path in ['/portal', '/portal/', '/portal/index.html', '/portal/login']:
        html = c.get(path).text
        assert 'data-google-login="true"' in html
        assert 'id="google-login-options" hidden' not in html
        assert 'id="email-login-details" open' not in html
        assert '<summary>이메일 링크로 로그인</summary>' in html
        assert html.index('id="google-login"') < html.index('id="login-form"')
        assert '카카오톡 등 앱 안에서 열었다면 Safari나 Chrome에서 열어 주세요.' in html
    callback = c.get('/portal/google-return')
    assert callback.status_code == 200 and callback.headers['cache-control'] == 'no-store'


def test_google_exchange_session_rotation_and_tenant_boundary(google_env, capsys):
    c, sent, _, _, calls = google_env
    old_session = c.cookies.get(auth.SESSION)
    for name in ['maeum_email', 'maeum_email_browser', auth.DEVICE]:
        c.cookies.set(name, 'old-synthetic-cookie', domain='portal.example.test', path='/')
    google_start(c, sent)
    response = post(c, '/auth/google-exchange', {'code': 'synthetic-valid-auth-code'})
    assert response.status_code == 200, response.text
    assert response.json()['state'] == 'verified'
    c.headers['X-CSRF-Token'] = response.json()['csrf']
    assert_google_state_cleared(c, response)
    assert c.cookies.get(auth.SESSION) != old_session
    for name in ['maeum_email', 'maeum_email_browser', auth.DEVICE]:
        assert not c.cookies.get(name)
    for name in [auth.SESSION, auth.NONCE]:
        header = next(v for v in response.headers.get_list('set-cookie') if v.startswith(name + '='))
        assert all(part in header for part in ['Max-Age=1209600', 'HttpOnly', 'Secure', 'SameSite=strict'])
    assert c.get('/api/portal/me').json()['google_login'] is True
    assert c.get('/api/portal/intakes?org_id=A').status_code == 200
    assert c.get('/api/portal/intakes?org_id=B').status_code == 403
    with owner() as conn:
        assert conn.execute('SELECT revoked FROM maeum.portal_sessions WHERE token_hash=%s', (store.digest(old_session),)).fetchone()[0]
        created, expiry, device_expiry = conn.execute(
            'SELECT s.created_at,s.expires_at,d.expires_at FROM maeum.portal_sessions s '
            'JOIN maeum.trusted_devices d ON d.id=s.device_id WHERE s.token_hash=%s',
            (store.digest(c.cookies.get(auth.SESSION)),)).fetchone()
        assert expiry - created == pytest.approx(14 * 86400)
        assert device_expiry == pytest.approx(expiry, abs=2, rel=0)
    assert [call[0] for call in calls] == ['/token?grant_type=pkce', '/logout?scope=local']
    assert json.loads(capsys.readouterr().out) == {'event': 'portal_google_login', 'outcome': 'ok'}
    retry = post(c, '/auth/google-exchange', {'code': 'synthetic-valid-auth-code'})
    assert retry.status_code == 400
    assert_google_state_cleared(c, retry)
    assert len(calls) == 2


@pytest.mark.parametrize('state', [None, 'x' * 31, 'x' * 129])
def test_google_exchange_requires_browser_cookie(google_env, state):
    c, _, _, _, calls = google_env
    if state is not None:
        c.cookies.set('maeum_google_state', state, domain='portal.example.test', path='/')
    response = post(c, '/auth/google-exchange', {'code': 'synthetic-valid-auth-code'})
    assert response.status_code == 400
    assert response.json()['detail'] == 'Google 로그인을 시작한 브라우저에서 다시 시도해 주세요.'
    assert_google_state_cleared(c, response)
    assert calls == []


@pytest.mark.parametrize('code', [None, 1234567890, '', 'x' * 9, 'x' * 513])
def test_google_exchange_code_validation(google_env, code):
    c, sent, _, _, calls = google_env
    google_start(c, sent)
    response = post(c, '/auth/google-exchange', {'code': code})
    assert response.status_code == 400
    assert_google_state_cleared(c, response)
    assert calls == []


def test_google_exchange_wrong_origin_clears_cookie(google_env):
    c, sent, _, _, calls = google_env
    google_start(c, sent)
    response = c.post('/api/portal/auth/google-exchange', json={'code': 'synthetic-valid-auth-code'},
                      headers={'Origin': 'https://other.example.test'})
    assert response.status_code == 403
    assert_google_state_cleared(c, response)
    assert calls == []


def test_google_exchange_rejects_changed_browser_state(google_env):
    c, sent, _, _, calls = google_env
    google_start(c, sent)
    c.cookies.set('maeum_google_state', 'x' * 43, domain='portal.example.test', path='/')
    response = post(c, '/auth/google-exchange', {'code': 'synthetic-valid-auth-code'})
    assert response.status_code == 400
    assert_google_state_cleared(c, response)
    assert [call[0] for call in calls] == ['/token?grant_type=pkce']


@pytest.mark.parametrize('endpoint,maximum', [('google-start', 30), ('google-exchange', 60)])
def test_google_peer_limits(google_env, endpoint, maximum):
    c, sent, _, _, calls = google_env
    google_start(c, sent)
    prefix = 'google-start-peer:' if endpoint == 'google-start' else 'google-verify-peer:'
    with owner() as conn:
        conn.execute('INSERT INTO maeum.portal_limits VALUES(%s,%s) ON CONFLICT(id) DO UPDATE SET stamps=excluded.stamps',
                     (prefix + store.digest('testclient'), Jsonb([time.time()] * maximum)))
    response = post(c, '/auth/' + endpoint, {'code': 'synthetic-valid-auth-code'})
    assert response.status_code == 429
    if endpoint == 'google-exchange':
        assert_google_state_cleared(c, response)
    assert calls == []


@pytest.mark.parametrize('failure', ['http', 'json', 'malformed'])
def test_google_provider_failure_discards_and_clears_cookie(google_env, monkeypatch, capsys, failure):
    c, sent, provider, _, _ = google_env
    google_start(c, sent)
    discarded = []
    def fail(path, body, **kwargs):
        if failure == 'malformed':
            return None
        if failure == 'json':
            raise ValueError('synthetic invalid JSON')
        raise auth.HTTPException(503)
    monkeypatch.setattr(provider, 'request_api', fail)
    monkeypatch.setattr(provider, 'discard_provider_session', lambda result: discarded.append(result))
    response = post(c, '/auth/google-exchange', {'code': 'synthetic-valid-auth-code'})
    assert response.status_code == 400
    assert response.json()['detail'] == 'Google 로그인을 확인하지 못했습니다. 다시 시도해 주세요.'
    assert_google_state_cleared(c, response)
    assert discarded == [{}]
    assert json.loads(capsys.readouterr().out) == {'event': 'portal_google_login', 'outcome': 'provider_error'}


@pytest.mark.parametrize('boundary,status', [
    ('unregistered', 403), ('inactive_user', 403), ('inactive_membership', 403),
    ('inactive_org', 403), ('different_uuid', 403), ('unconfirmed', 400),
    ('invalid_uuid', 400), ('foreign_domain', 400)])
def test_google_identity_and_registration_boundaries(google_env, capsys, boundary, status):
    c, sent, _, identity, calls = google_env
    with owner() as conn:
        if boundary == 'inactive_user':
            conn.execute("UPDATE maeum.portal_users SET active=false WHERE id='A0'")
        elif boundary == 'inactive_membership':
            conn.execute("UPDATE maeum.memberships SET active=false WHERE user_id='A0'")
        elif boundary == 'inactive_org':
            conn.execute("UPDATE maeum.organizations SET active=false WHERE id='A'")
    if boundary == 'unregistered':
        identity['email'] = 'unregistered@gmail.com'
    elif boundary == 'different_uuid':
        identity['id'] = str(uuid4())
    elif boundary == 'unconfirmed':
        identity.pop('email_confirmed_at')
    elif boundary == 'invalid_uuid':
        identity['id'] = 'invalid-uuid'
    elif boundary == 'foreign_domain':
        identity['email'] = 'a0@example.test'
    google_start(c, sent)
    response = post(c, '/auth/google-exchange', {'code': 'synthetic-valid-auth-code'})
    assert response.status_code == status, response.text
    if status == 403:
        assert response.json()['detail'] == '등록된 담당자 계정이 아닙니다. 가입 신청 후 관리자 승인을 받아 주세요.'
    assert_google_state_cleared(c, response)
    assert [call[0] for call in calls] == ['/token?grant_type=pkce', '/logout?scope=local']
    assert json.loads(capsys.readouterr().out) == {'event': 'portal_google_login',
        'outcome': 'denied' if status == 403 else 'provider_error'}
    with owner() as conn:
        assert conn.execute("SELECT count(*) FROM maeum.portal_sessions WHERE state='verified'").fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM maeum.trusted_devices').fetchone()[0] == 0


def test_google_first_login_binds_null_provider_id(google_env):
    c, sent, _, identity, _ = google_env
    with owner() as conn:
        conn.execute("UPDATE maeum.portal_users SET supabase_user_id=NULL WHERE id='A0'")
    google_start(c, sent)
    response = post(c, '/auth/google-exchange', {'code': 'synthetic-valid-auth-code'})
    assert response.status_code == 200, response.text
    with owner() as conn:
        assert str(conn.execute("SELECT supabase_user_id FROM maeum.portal_users WHERE id='A0'").fetchone()[0]) == identity['id']
    assert_google_state_cleared(c, response)


def test_cloud_pkce_browser_session_rotation(provider_env):
    c, sent, _ = provider_env
    assert post(c, '/auth/device-challenge').json()['verification'] == 'email_link'
    pending = c.cookies.get(auth.SESSION)
    other = TestClient(app, base_url='https://portal.example.test', headers={'Origin': 'https://portal.example.test'})
    assert post(other, '/auth/exchange', {'code': 'synthetic-valid-auth-code', 'state': sent['state']}).status_code == 401
    assert c.get('/api/portal/intakes?org_id=A').status_code == 403
    r = post(c, '/auth/exchange', {'code': 'synthetic-valid-auth-code', 'state': sent['state'], 'remember': True})
    assert r.status_code == 200
    assert c.cookies.get(auth.SESSION) != pending
    assert all(cookie.secure for cookie in c.cookies.jar)
    c.headers['X-CSRF-Token'] = r.json()['csrf']
    assert c.get('/api/portal/intakes?org_id=A').status_code == 200
    assert c.get('/api/portal/intakes?org_id=B').status_code == 403
    assert post(c, '/auth/exchange', {'code': 'synthetic-valid-auth-code', 'state': sent['state']}).status_code == 409


def test_cloud_pkce_wrong_state_and_identity(provider_env, monkeypatch):
    c, sent, provider = provider_env
    assert post(c, '/auth/device-challenge').status_code == 200
    assert post(c, '/auth/exchange', {'code': 'synthetic-valid-auth-code', 'state': 'x' * 43}).status_code == 400
    original = provider.request_api
    def wrong_user(path, body, **kwargs):
        result = original(path, body, **kwargs)
        if 'user' in result:
            result['user']['id'] = str(uuid4())
        return result
    monkeypatch.setattr(provider, 'request_api', wrong_user)
    assert post(c, '/auth/exchange', {'code': 'synthetic-valid-auth-code', 'state': sent['state']}).status_code == 400
    assert c.get('/api/portal/me').json()['state'] == 'pending_device'


def test_cloud_pkce_expiry_logout_and_csrf(provider_env):
    c, sent, _ = provider_env
    assert post(c, '/auth/device-challenge').status_code == 200
    payload = {'code': 'synthetic-valid-auth-code', 'state': sent['state']}
    csrf_token = c.headers['X-CSRF-Token']
    c.headers['X-CSRF-Token'] = 'wrong'
    assert post(c, '/auth/exchange', payload).status_code == 403
    c.headers['X-CSRF-Token'] = csrf_token
    with auth.connect() as conn:
        conn.execute('UPDATE maeum.device_challenges SET expires_at=0')
    assert post(c, '/auth/exchange', payload).status_code == 400
    assert post(c, '/auth/logout').status_code == 200
    assert post(c, '/auth/exchange', payload).status_code == 401


def test_cloud_cannot_use_local_identity_mutations(provider_env):
    c, _, _ = provider_env
    for endpoint in ['/invitations', '/auth/accept-invitation', '/auth/password', '/auth/email-challenge', '/auth/email-verify']:
        assert post(c, endpoint).status_code == 404
    assert post(c, '/auth/device-verify', {'code': '12345678'}).status_code == 400


def test_cloud_failed_mail_does_not_refund_send_budget(provider_env, monkeypatch):
    c, _, provider = provider_env
    calls = []
    def fail(path, body, **kwargs):
        calls.append(path)
        raise auth.HTTPException(503)
    monkeypatch.setattr(provider, 'request_api', fail)
    assert post(c, '/auth/device-challenge').status_code == 503
    for _ in range(5):
        assert post(c, '/auth/device-challenge').status_code == 429
    assert len(calls) == 1


def test_cloud_pkce_failed_codes_are_bounded(provider_env):
    c, sent, _ = provider_env
    assert post(c, '/auth/device-challenge').status_code == 200
    for _ in range(5):
        assert post(c, '/auth/exchange', {'code': 'wrong-auth-code', 'state': sent['state']}).status_code == 400
    assert post(c, '/auth/exchange', {'code': 'synthetic-valid-auth-code', 'state': sent['state']}).status_code == 400
    assert c.get('/api/portal/me').json()['state'] == 'pending_device'


def test_cloud_pkce_nonce_and_superseded_challenge(provider_env):
    c, sent, _ = provider_env
    assert post(c, '/auth/device-challenge').status_code == 200
    old_state = sent['state']
    nonce = c.cookies.get(auth.NONCE)
    c.cookies.set(auth.NONCE, 'wrong-nonce', domain='portal.example.test', path='/')
    assert post(c, '/auth/exchange', {'code': 'synthetic-valid-auth-code', 'state': old_state}).status_code == 401
    c.cookies.set(auth.NONCE, nonce, domain='portal.example.test', path='/')
    with auth.connect() as conn:
        conn.execute('UPDATE maeum.device_challenges SET created_at=created_at-120')
        conn.execute("UPDATE maeum.portal_limits SET stamps='[]' WHERE id LIKE 'provider-mail-%'")
    assert post(c, '/auth/device-challenge').status_code == 200
    assert post(c, '/auth/exchange', {'code': 'synthetic-valid-auth-code', 'state': old_state}).status_code == 400


def test_cloud_pkce_concurrent_single_success(provider_env):
    c, sent, _ = provider_env
    assert post(c, '/auth/device-challenge').status_code == 200
    payload = {'code': 'synthetic-valid-auth-code', 'state': sent['state']}
    peers = []
    for _ in range(2):
        peer = TestClient(app, base_url='https://portal.example.test', headers=dict(c.headers))
        peer.cookies.update(c.cookies)
        peers.append(peer)
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda peer: post(peer, '/auth/exchange', payload).status_code, peers))
    assert sorted(statuses) == [200, 401]


def test_expectation_is_not_inferred_from_cause():
    from app import intake
    schema = intake.load_schema('knowledge-maeum')
    cause = '지난달 팀이 바뀌면서 맡은 업무가 갑자기 늘어났어요.'
    _, fields = intake.extract_real('답변\n```slots\n' + json.dumps({'expectation': cause}) + '\n```',
                                     schema, {'track': '정서'}, cause, 'cause')
    assert 'expectation' not in fields


def test_opaque_identifiers_survive_cloud_redaction(env):
    sid = 'synthetic-opaque-01012345678'
    token = 'opaque-token-01012345678-do-not-redact'
    participant = 'p_e27b9e9a201012345678e1279'
    with cloud_store.session_scope(sid):
        chat._sessions[sid] = chat.ChatSession(session_id=sid, session_token=token,
                                              participant_id=participant,
                                              history=[{'role':'user', 'content':'전화 010-1234-5678'}])
    saved = cloud_store.get('session', sid)
    assert saved['session_id'] == sid and saved['session_token'] == token and saved['participant_id'] == participant
    assert '010-1234-5678' not in saved['history'][0]['content']


def test_cloud_identity_trigger_and_engine_role(env, monkeypatch):
    # Simulate provider table shape only in the disposable local database.
    with psycopg.connect(env['MAEUM_DATABASE_URL']) as conn:
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='maeum_engine'").fetchone():
            conn.execute('CREATE ROLE maeum_engine NOLOGIN NOSUPERUSER NOBYPASSRLS')
        conn.execute('CREATE SCHEMA auth')
        conn.execute('CREATE TABLE auth.users(id uuid PRIMARY KEY,email text,encrypted_password text,banned_until timestamptz,deleted_at timestamptz)')
        conn.execute(Path('deploy/portal_cloud_roles.sql').read_text())
        uid = str(uuid4())
        conn.execute('INSERT INTO auth.users(id,email,encrypted_password) VALUES(%s,%s,%s)', (uid, 'a0@example.test', 'synthetic-v1'))
        conn.execute('UPDATE maeum.portal_users SET supabase_user_id=%s WHERE id=%s', (uid, 'A0'))
    c = verified()
    with psycopg.connect(env['MAEUM_DATABASE_URL']) as conn:
        conn.execute('UPDATE auth.users SET encrypted_password=%s WHERE id=%s', ('synthetic-v2', uid))
    assert c.get('/api/portal/me').status_code == 401
    with psycopg.connect(env['MAEUM_DATABASE_URL']) as conn:
        conn.execute("UPDATE maeum.portal_users SET active=false WHERE id='A0'")
        conn.execute('UPDATE auth.users SET encrypted_password=%s WHERE id=%s', ('synthetic-v3', uid))
        assert conn.execute("SELECT active FROM maeum.portal_users WHERE id='A0'").fetchone()[0] is False
    assert post(client(), '/auth/login', {'email': 'a0@example.test', 'password': PASSWORD}).status_code == 401
    with psycopg.connect(env['MAEUM_DATABASE_URL']) as conn:
        with pytest.raises(RuntimeError, match='restricted non-owner'):
            cloud_store.require_engine_role(conn)
        conn.execute('SET LOCAL ROLE maeum_engine')
        cloud_store.require_engine_role(conn)
        conn.execute("INSERT INTO maeum.records(kind,record_key,payload) VALUES('health','synthetic','{}')")
        conn.execute("INSERT INTO maeum.intake_links(id,org_id,token_hash,management_id,expires_at) "
                     "VALUES('engine-try','A','engine-try-hash','TRY-X-000000',9999999999)")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('SELECT * FROM maeum.portal_users')
        conn.rollback()
    from app import portal_config
    original_connect = psycopg.connect
    opened = []
    def local_connect(url, **kwargs):
        kwargs['sslmode'] = 'disable'
        connection = original_connect(url, **kwargs)
        opened.append(connection)
        return connection
    monkeypatch.setattr(psycopg, 'connect', local_connect)
    monkeypatch.setattr(store, 'require_database_url', lambda url: None)
    monkeypatch.setattr(portal_config, 'cloud', lambda: True)
    with pytest.raises(RuntimeError, match='restricted non-owner'):
        cloud_store._connect()
    assert opened[-1].closed


def verified(email="a0@example.test", remember=True):
    c = client()
    login(c, email)
    assert post(c, "/auth/device-challenge").status_code == 200
    r = post(c, "/auth/device-verify", {"code": latest_mail(email)["code"], "remember": remember})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    return c


def issue(c, org="A", management="D-101"):
    r = post(c, "/links", {"org_id": org, "management_id": management})
    assert r.status_code == 200, r.text
    return r.json()


def exchange(c, link):
    return c.post("/api/intake-link/exchange", json={"token": link["url"].split("#intake=")[1]})


def intake_case(staff, org="A", text="요즘 회사 일 때문에 마음이 불안하고 잠을 잘 못 자요."):
    link = issue(staff, org)
    c = client()
    assert exchange(c, link).status_code == 200
    sid = str(uuid4())
    version = c.get("/api/config").json()["privacy"]["consent_version"]
    payload = {"session_id": sid, "accepted": True, "consent_version": version, "idempotency_key": str(uuid4())}
    r = c.post("/api/consent", json=payload)
    assert r.status_code == 200, r.text
    receipt = r.json()
    r = c.post("/api/chat", json={"session_id": sid, "session_token": receipt["session_token"], "message": text})
    assert r.status_code == 200, r.text
    return c, sid, receipt, payload, link


def owner():
    return psycopg.connect(os.environ["MAEUM_DATABASE_URL"])


def report(c, intake_id, org="A", suffix=""):
    return c.get("/api/portal/intakes/" + intake_id + suffix, params={"org_id": org})


def test_T01_T13_actual_saved_content_and_restart(env):
    a, b = verified(), verified("b0@example.test")
    _, sid_a, ra, _, _ = intake_case(a)
    _, sid_b, rb, _, _ = intake_case(b, "B", "친구와 다툰 이후 관계가 힘들어요.")
    for staff, org, sid, receipt in ((a,"A",sid_a,ra), (b,"B",sid_b,rb)):
        rows = staff.get("/api/portal/intakes", params={"org_id":org}).json()["items"]
        assert len(rows) == 1 and rows[0]["id"] == receipt["intake_id"] and rows[0]["management_id"] == "D-101"
        assert staff.get("/api/portal/summary",params={"org_id":org}).json()["total"] == 1
        detail = report(staff,receipt["intake_id"],org).json()
        with owner() as conn:
            documents = conn.execute("SELECT payload FROM maeum.records WHERE kind='conversation' AND payload->>'session_id'=%s ORDER BY record_key",(sid,)).fetchall()
        assert detail["summary"] == documents[-1][0]["intake_snapshot"]
        assert "[recorded]" not in json.dumps(detail)
        raw = report(staff,receipt["intake_id"],org,"/transcript").json()
        assert raw["documents"][0]["turns"] == documents[0][0]["turns"]
        # Read from a separate Python process with empty engine memory.
        code = "from app.portal_store import connect,context,detail; import sys,json;\nwith connect() as c:\n context(c,sys.argv[1],sys.argv[2],'report:read',sys.stdin.read()); print(json.dumps(detail(c,sys.argv[2],sys.argv[3])['summary'],sort_keys=True))"
        output = subprocess.check_output([sys.executable,"-c",code,"A0" if org=="A" else "B0",org,receipt["intake_id"]], input=store.digest(staff.cookies.get(auth.SESSION)), text=True)
        assert json.loads(output) == detail["summary"]


def test_T02_cross_institution_endpoints(env):
    a,b=verified(),verified("b0@example.test")
    _,_,rb,_,lb=intake_case(b,"B")
    for suffix in ("","/transcript"):
        assert report(a,rb["intake_id"],"A",suffix).status_code == 404
    assert post(a,"/intakes/"+rb["intake_id"]+"/review",{"org_id":"A","status":"reviewed"}).status_code == 404
    assert post(a,"/links/"+lb["id"]+"?org_id=A",method="DELETE").status_code == 404
    for path in ("/intakes","/summary","/links","/members","/audit"):
        assert a.get("/api/portal"+path,params={"org_id":"B"}).status_code == 403
    assert post(a,"/links",{"org_id":"B","management_id":"D-101"}).status_code == 403
    assert post(a,"/members/B0",{"org_id":"A","permissions":[],"active":False},method="PATCH").status_code == 404
    assert a.get("/api/portal/intakes/export?org_id=A").status_code == 404


def test_T03_pending_and_anonymous_all_protected(env):
    for c,expected in ((client(),401),(client(),403)):
        if expected==403:login(c)
        for path in ("/intakes?org_id=A","/summary?org_id=A","/intakes/missing?org_id=A",
                     "/intakes/missing/transcript?org_id=A","/devices","/links?org_id=A","/members?org_id=A","/audit?org_id=A"):
            assert c.get("/api/portal"+path).status_code==expected
        for path,payload,method in (("/links",{"org_id":"A","management_id":"D-101"},"POST"),
                                    ("/intakes/missing/review",{"org_id":"A","status":"reviewed"},"POST"),
                                    ("/devices/missing",{},"DELETE"),
                                    ("/invitations",{"org_id":"A","email":"new@example.test","permissions":[]},"POST"),
                                    ("/members/A1",{"org_id":"A","permissions":[],"active":False},"PATCH")):
            assert post(c,path,payload,method).status_code==expected


def test_T04_summary_only_no_raw(env):
    a=verified();_,_,r,_,_=intake_case(a)
    a2=verified("a2@example.test")
    assert report(a2,r["intake_id"]).status_code==200
    assert report(a2,r["intake_id"],suffix="/transcript").status_code==403
    assert post(a2,"/links",{"org_id":"A","management_id":"D-101"}).status_code==403


def test_T04_summary_only_strips_raw_provenance_and_revision_text(env):
    a=verified();_,sid,r,_,_=intake_case(a)
    sentinels={"SOURCE-TEXT-ONLY","OLD-CORRECTION-ONLY","NEW-CORRECTION-ONLY",
               "CACHED-USER-MESSAGE-ONLY","CACHED-MODEL-REPLY-ONLY"}
    with owner() as conn:
        key,payload=conn.execute(
            "SELECT record_key,payload FROM maeum.records WHERE kind='conversation' AND payload->>'session_id'=%s",
            (sid,),
        ).fetchone()
        user_turn=next(turn for turn in payload["turns"] if turn["role"]=="user")
        source={"day":key.split('/',1)[0],"seq":user_turn["seq"],"role":"user"}
        payload["intake_snapshot"] = payload["intake_snapshot"] | {
            "slot_evidence":{"cause":{"status":"answered","value":"업무 부담","source":source,
                                        "source_text":"SOURCE-TEXT-ONLY"}},
            "slot_revisions":[{"field":"cause","before":"OLD-CORRECTION-ONLY",
                               "after":"NEW-CORRECTION-ONLY","source_turn":user_turn["seq"]}],
            "request_results":{"synthetic":{"message":"CACHED-USER-MESSAGE-ONLY",
                                              "reply":"CACHED-MODEL-REPLY-ONLY"}},
        }
        conn.execute("UPDATE maeum.records SET payload=%s WHERE kind='conversation' AND record_key=%s",
                     (Jsonb(payload),key))
    store.project(sid)
    summary=report(verified("a2@example.test"),r["intake_id"]).json()["summary"]
    serialized=json.dumps(summary,ensure_ascii=False)
    assert not any(marker in serialized for marker in sentinels)
    assert summary["slot_evidence"]["cause"] == {
        "status":"answered","value":"업무 부담","source":source,
    }
    assert summary["slot_revisions"] == [{"field":"cause","source_turn":user_turn["seq"]}]


def test_report_quality_projection_is_permission_gated_and_read_only(env):
    manager = verified()
    _, sid, receipt, _, _ = intake_case(manager)
    summary_only = verified("a2@example.test")
    fixture = json.loads((Path(__file__).parent / "fixtures/report-quality-legacy.json").read_text())

    with owner() as conn:
        key, payload = conn.execute(
            "SELECT record_key,payload FROM maeum.records WHERE kind='conversation' "
            "AND payload->>'session_id'=%s ORDER BY record_key LIMIT 1", (sid,)
        ).fetchone()
        actual_day = key.split("/", 1)[0]
        fixture = json.loads(json.dumps(fixture).replace("2026-11-05", actual_day))
        payload["turns"] = fixture["documents"][0]["turns"]
        payload["intake_snapshot"] = fixture["summary"]
        conn.execute(
            "UPDATE maeum.records SET payload=%s WHERE kind='conversation' AND record_key=%s",
            (Jsonb(payload), key),
        )
        conn.execute(
            "UPDATE maeum.report_snapshots SET summary=%s,sources=%s WHERE intake_id=%s",
            (Jsonb(fixture["summary"]), Jsonb(fixture["sources"]), receipt["intake_id"]),
        )
        stored_before_reads = conn.execute(
            "SELECT version,source_revision,summary,sources FROM maeum.report_snapshots WHERE intake_id=%s",
            (receipt["intake_id"],),
        ).fetchone()

    limited = report(summary_only, receipt["intake_id"]).json()
    assert limited["summary"]["track"] == "관계"
    assert "symptom_context" not in limited["summary"]["slots"]
    assert limited["summary"]["slot_evidence"]["expectation"] == {"status": "unconfirmed"}
    assert limited["summary"]["slot_evidence"]["support"] == {"status": "unconfirmed"}

    projected = report(manager, receipt["intake_id"]).json()
    assert projected["summary"]["track"] == "정서"
    assert projected["summary"]["slots"]["symptom_context"] == (
        "한 석달전부터? 중간고사 이후부터요. / 저녁에 책상에 앉으면요"
    )
    assert projected["sources"]["symptom_context"] == [
        {"day": actual_day, "seq": 6, "role": "user"},
        {"day": actual_day, "seq": 12, "role": "user"},
    ]

    with owner() as conn:
        stored = conn.execute(
            "SELECT version,source_revision,summary,sources FROM maeum.report_snapshots WHERE intake_id=%s",
            (receipt["intake_id"],),
        ).fetchone()
    assert stored == stored_before_reads
    assert stored[2] == fixture["summary"]
    assert stored[3] == fixture["sources"]


def test_T05_T06_device_cookie_is_not_login_and_ip_no_challenge(env):
    c=verified()
    assert post(c,"/auth/logout").status_code==200
    assert c.get("/api/portal/intakes?org_id=A").status_code==401
    # Changing transport IP as well as forwarded IP, with same authenticated browser cookies.
    other=TestClient(app,base_url=ORIGIN,client=("127.0.0.2",54321),headers={"Origin":ORIGIN,"X-Forwarded-For":"203.0.113.9"})
    other.cookies.update(c.cookies)
    assert login(other)["state"]=="verified"
    assert other.get("/api/portal/intakes?org_id=A").status_code==200


def test_T07_new_browser_public_pc_other_user(env):
    c=verified(remember=False)
    post(c,"/auth/logout")
    assert login(c)["state"]=="pending_device"
    remembered=verified("b0@example.test")
    remembered.cookies.delete(auth.SESSION)
    assert login(remembered,"a1@example.test")["state"]=="pending_device"
    assert login(client())["state"]=="pending_device"


def test_T08_expiry_attempts_resend_binding(env):
    c=client();login(c);assert post(c,"/auth/device-challenge").status_code==200
    good=latest_mail()["code"]
    assert post(c,"/auth/device-challenge").status_code==429
    wrong="00000000" if good!="00000000" else "11111111"
    for _ in range(5):
        assert post(c,"/auth/device-verify",{"code":wrong}).status_code==400
    assert post(c,"/auth/device-verify",{"code":good}).status_code==400
    with owner() as conn:
        conn.execute("UPDATE maeum.device_challenges SET created_at=created_at-61")
    assert post(c,"/auth/device-challenge").status_code==200
    new=latest_mail()["code"]
    assert post(c,"/auth/device-verify",{"code":good}).status_code==400
    other=client();login(other)
    assert post(other,"/auth/device-verify",{"code":new}).status_code==400
    with owner() as conn:
        conn.execute("UPDATE maeum.device_challenges SET expires_at=0")
    assert post(c,"/auth/device-verify",{"code":new}).status_code==400


def test_T08_concurrent_one_use_and_rotation(env):
    c=client();login(c);post(c,"/auth/device-challenge");code=latest_mail()["code"]
    old=c.cookies.get(auth.SESSION)
    def attempt():
        x=client();x.cookies.update(c.cookies);x.headers["X-CSRF-Token"]=c.headers["X-CSRF-Token"]
        return post(x,"/auth/device-verify",{"code":code,"remember":True})
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:attempt(), range(2)))
    assert sorted(r.status_code for r in results)==[200,401]
    assert next(r for r in results if r.status_code==200).cookies.get(auth.SESSION)!=old
    assert c.get("/api/portal/me").status_code==401


def test_T09_revoke_device_membership_user_organization(env):
    a=verified();a1=verified("a1@example.test")
    assert post(a,"/members/A1",{"org_id":"A","permissions":["report:read"],"active":False},method="PATCH").status_code==200
    assert a1.get("/api/portal/intakes?org_id=A").status_code==403
    dev=a.get("/api/portal/devices").json()[0]["id"]
    assert post(a,"/devices/"+dev,method="DELETE").status_code==200
    assert a.get("/api/portal/me").status_code==401
    b=verified("b0@example.test")
    with owner() as conn:conn.execute("UPDATE maeum.organizations SET active=false WHERE id='B'")
    assert b.get("/api/portal/intakes?org_id=B").status_code==403
    with owner() as conn:conn.execute("UPDATE maeum.portal_users SET active=false WHERE id='B0'")
    assert b.get("/api/portal/me").status_code==401


def test_T10_csrf_origin_permission_escalation(env):
    a=verified()
    assert post(a,"/invitations",{"org_id":"A","email":"new@example.test","permissions":["platform:admin"]}).status_code==403
    for header,value in (("Origin","http://evil.test"),("X-CSRF-Token","wrong")):
        saved=a.headers[header];a.headers[header]=value
        assert post(a,"/links",{"org_id":"A","management_id":"D-101"}).status_code==403
        a.headers[header]=saved


def test_T11_actual_runtime_role_no_records_or_foreign_rows(env):
    a,b=verified(),verified("b0@example.test");_,_,ra,_,_=intake_case(a);_,_,rb,_,_=intake_case(b,"B")
    with store.connect() as conn:
        assert conn.execute("SELECT * FROM maeum.intakes").fetchall()==[]
        store.context(conn,"A0","A","report:read",store.digest(a.cookies.get(auth.SESSION)))
        assert [r["id"] for r in conn.execute("SELECT id FROM maeum.intakes").fetchall()]==[ra["intake_id"]]
        assert conn.execute("SELECT maeum.read_transcript(%s)",(rb["intake_id"],)).fetchall()==[]
        conn.commit()
        assert conn.execute("SELECT * FROM maeum.intakes").fetchall()==[]
        store.context(conn,"B0","B","report:read",store.digest(b.cookies.get(auth.SESSION)))
        assert [r["id"] for r in conn.execute("SELECT id FROM maeum.intakes").fetchall()]==[rb["intake_id"]]
    with store.connect() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT * FROM maeum.records")
    with store.connect() as conn:
        store.context(conn,"A0","A","link:issue",store.digest(a.cookies.get(auth.SESSION)))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("INSERT INTO maeum.intake_links VALUES('attack','B','attack','D-101',9999999999,false,NULL)")


def test_T12_decline_expiry_revoke_revisit_idempotency(env):
    a=verified();link=issue(a);c=client();assert exchange(c,link).status_code==200
    version=c.get("/api/config").json()["privacy"]["consent_version"]
    body={"accepted":False,"consent_version":version,"session_id":str(uuid4()),"idempotency_key":str(uuid4())}
    assert c.post("/api/consent",json=body).json()["accepted"] is False
    with owner() as conn:
        assert conn.execute("SELECT count(*) FROM maeum.intakes").fetchone()[0]==0
        assert conn.execute("SELECT count(*) FROM maeum.records WHERE kind='conversation'").fetchone()[0]==0
    body["accepted"]=True
    r=c.post("/api/consent",json=body);assert r.status_code==200
    assert c.post("/api/consent",json=body).status_code==410
    body["session_token"]=r.json()["session_token"]
    assert c.post("/api/consent",json=body).json()["resumed"]
    assert exchange(client(),link).status_code==410
    unused=issue(a)
    with owner() as conn:conn.execute("UPDATE maeum.intake_links SET expires_at=0 WHERE id=%s",(unused["id"],))
    assert exchange(client(),unused).status_code==410
    unused=issue(a);post(a,"/links/"+unused["id"]+"?org_id=A",method="DELETE")
    assert exchange(client(),unused).status_code==410


def test_T12_concurrent_consent_one_winner(env):
    a=verified();link=issue(a)
    clients=[client(),client()]
    for c in clients:assert exchange(c,link).status_code==200
    version=clients[0].get("/api/config").json()["privacy"]["consent_version"]
    def accept(c):
        return c.post("/api/consent",json={"accepted":True,"consent_version":version,"session_id":str(uuid4()),"idempotency_key":str(uuid4())})
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(accept,clients))
    assert sorted(r.status_code for r in results)==[200,410]


def shared_review_link(org="A", management="OPEN-REVIEW", seconds=3600):
    token = secrets.token_urlsafe(32)
    with owner() as conn:
        conn.execute("INSERT INTO maeum.intake_links(id,org_id,token_hash,management_id,expires_at) VALUES(%s,%s,%s,%s,%s)",
                     (str(uuid4()), org, store.digest(token), management, time.time() + seconds))
    return {"url": ORIGIN + "/#intake=" + token}


def test_shared_review_link_gives_every_visit_its_own_single_use_link(env, monkeypatch):
    a = verified()
    shared = shared_review_link()
    raw = shared["url"].split("#intake=")[1]

    def open_tab(c):
        r = exchange(c, shared)
        assert r.status_code == 200 and r.json()["reusable"] is True, r.text
        child = r.json()["link_token"]
        assert child != raw and c.cookies.get("maeum_link") == child
        return child

    def consent(c, child=None, headers=None):
        version = c.get("/api/config").json()["privacy"]["consent_version"]
        body = {"accepted": True, "consent_version": version, "session_id": str(uuid4()), "idempotency_key": str(uuid4())}
        if child:
            body["link_token"] = child
        return c.post("/api/consent", json=body, headers=headers)

    c = client()
    first = open_tab(c)
    r1 = consent(c, first)
    assert r1.status_code == 200, r1.text
    # The used per-visit link stays single-use; '새 대화' reopens the shared link and starts fresh.
    assert c.post("/api/intake-link/exchange", json={}).status_code == 410
    # Two tabs of one browser share the cookie, yet each consent consumes its own tab's link.
    tab1, tab2 = open_tab(c), open_tab(c)
    r2, r3 = consent(c, tab1), consent(c, tab2)
    assert r2.status_code == 200 and r3.status_code == 200, (r2.text, r3.text)
    other = client()
    r4 = consent(other, open_tab(other))
    assert r4.status_code == 200, r4.text
    assert len({r.json()["intake_id"] for r in (r1, r2, r3, r4)}) == 4
    with owner() as conn:
        parent = conn.execute("SELECT expires_at,consumed_intake_id FROM maeum.intake_links WHERE management_id='OPEN-REVIEW'").fetchone()
        rows = conn.execute("SELECT token_hash,expires_at,consumed_intake_id FROM maeum.intake_links WHERE management_id LIKE %s",
                            ("TRY-REVIEW-%",)).fetchall()
    consumed = {token_hash: intake for token_hash, _, intake in rows}
    assert parent[1] is None and len(rows) == 4 and all(consumed[store.digest(t)] for t in (first, tab1, tab2))
    assert all(expires <= min(parent[0], time.time() + store.REUSABLE_CHILD_SECONDS) for _, expires, _ in rows)
    # The shared link itself is never consumed, whether a tab names it or it is planted as the cookie.
    assert consent(client(), raw).status_code == 410
    assert consent(client(), headers={"Cookie": "maeum_link=" + raw}).status_code == 410
    # Staff cannot create shared links through the portal, and the per-link cap holds.
    assert post(a, "/links", {"org_id": "A", "management_id": "OPEN-STAFF"}).status_code == 400
    monkeypatch.setattr(store, "REUSABLE_CHILD_LIMIT", 4)
    assert exchange(client(), shared).status_code == 410


def test_shared_review_view_shows_only_that_links_cases(env):
    a = verified()
    shared, other = shared_review_link(), shared_review_link(management="OPEN-OTHER")
    raw = shared["url"].split("#intake=")[1]

    def chat_once(link, text):
        c = client()
        token = exchange(c, link).json()["link_token"]
        version = c.get("/api/config").json()["privacy"]["consent_version"]
        sid = str(uuid4())
        r = c.post("/api/consent", json={"accepted": True, "consent_version": version, "session_id": sid,
                                         "idempotency_key": str(uuid4()), "link_token": token})
        assert r.status_code == 200, r.text
        r = c.post("/api/chat", json={"session_id": sid, "session_token": r.json()["session_token"], "message": text})
        assert r.status_code == 200, r.text

    chat_once(shared, "요즘 회사 일 때문에 마음이 불안하고 잠을 잘 못 자요.")
    chat_once(other, "다른 공용 링크로 남긴 이야기예요.")
    intake_case(a)  # an individual-link case of the same organization stays hidden
    r = client().post("/api/intake-link/review", json={"token": raw})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [case["case"][:11] for case in body["cases"]] == ["TRY-REVIEW-"]
    turns = body["cases"][0]["turns"]
    assert any(t["role"] == "user" and "회사 일" in t["text"] for t in turns) and any(t["role"] == "assistant" for t in turns)
    assert isinstance(body["cases"][0]["summary"], dict) and body["slot_labels"] and "track" not in dict(body["slot_labels"])
    # Only the shared link itself opens the view.
    child = exchange(client(), shared).json()["link_token"]
    for token in (issue(a)["url"].split("#intake=")[1], child, ""):
        assert client().post("/api/intake-link/review", json={"token": token}).status_code == 410
    assert client().post("/api/intake-link/review", json={"token": raw}, headers={"Origin": "https://evil.example"}).status_code == 403


def test_each_tab_consents_with_the_link_it_opened(env):
    a, b = verified(), verified("b0@example.test")
    link_a, link_b = issue(a, "A"), issue(b, "B")
    c = client()
    ra, rb = exchange(c, link_a), exchange(c, link_b)  # the shared cookie now holds B's link
    assert ra.status_code == 200 and rb.status_code == 200, (ra.text, rb.text)
    assert ra.json()["link_token"] == link_a["url"].split("#intake=")[1] and "reusable" not in ra.json()
    version = c.get("/api/config").json()["privacy"]["consent_version"]
    r = c.post("/api/consent", json={"accepted": True, "consent_version": version, "session_id": str(uuid4()),
                                     "idempotency_key": str(uuid4()), "link_token": ra.json()["link_token"]})
    assert r.status_code == 200, r.text
    with owner() as conn:
        org = conn.execute("SELECT org_id FROM maeum.intakes WHERE id=%s", (r.json()["intake_id"],)).fetchone()[0]
        b_left = conn.execute("SELECT consumed_intake_id FROM maeum.intake_links WHERE id=%s", (link_b["id"],)).fetchone()[0]
    assert org == "A" and b_left is None


def test_T13_atomic_projection_failure_rollback(env,monkeypatch):
    a=verified();c,sid,r,_,_=intake_case(a)
    before=report(a,r["intake_id"]).json()
    with owner() as conn:raw_before=conn.execute("SELECT payload FROM maeum.records WHERE kind='conversation' AND payload->>'session_id'=%s",(sid,)).fetchall()
    def fail(_):raise psycopg.OperationalError("synthetic")
    monkeypatch.setattr(store,"project",fail)
    response=c.post("/api/chat",json={"session_id":sid,"session_token":r["session_token"],"message":"주말에는 쉬고 있어요."})
    assert response.status_code==503
    assert report(a,r["intake_id"]).json()==before
    with owner() as conn:assert conn.execute("SELECT payload FROM maeum.records WHERE kind='conversation' AND payload->>'session_id'=%s",(sid,)).fetchall()==raw_before


def test_T14_audit_review_and_fail_closed(env):
    a=verified();_,_,r,_,_=intake_case(a);iid=r["intake_id"]
    assert report(a,iid,suffix="/transcript").status_code==200
    assert post(a,"/intakes/"+iid+"/review",{"org_id":"A","status":"reviewed"}).status_code==200
    with owner() as conn:
        actions=[r[0] for r in conn.execute("SELECT action FROM maeum.audit_events WHERE org_id='A'").fetchall()]
        assert "raw_view" in actions and "review" in actions
        conn.execute("ALTER TABLE maeum.audit_events ADD CONSTRAINT fail_audit CHECK(action <> 'raw_view') NOT VALID")
    try:
        response=report(a,iid,suffix="/transcript")
        assert response.status_code==503
        assert "turns" not in response.text
    finally:
        with owner() as conn:conn.execute("ALTER TABLE maeum.audit_events DROP CONSTRAINT fail_audit")


@pytest.mark.parametrize("age,raw,exists",[(90,True,True),(91,False,True),(365,False,True),(366,False,False)])
def test_T15_retention_boundary(env,age,raw,exists):
    a=verified();_,sid,r,_,_=intake_case(a)
    # Retention is measured from the earliest persisted session day.  Anchor the
    # boundary to that durable value instead of the test runner's local calendar:
    # a session created just after midnight KST can still have a UTC date from the
    # previous day in created_at/consented_at.
    with owner() as conn:
        rows=conn.execute("SELECT record_key,payload FROM maeum.records WHERE kind='conversation' AND payload->>'session_id'=%s",(sid,)).fetchall()
    origin=min(
        [date.fromisoformat(key.split('/',1)[0]) for key,_ in rows]
        + [date.fromisoformat(payload[field][:10]) for _,payload in rows
           for field in ('created_at','consented_at') if payload.get(field)]
    )
    cloud_store.purge_expired(today=origin+timedelta(days=age))
    result=report(a,r["intake_id"])
    assert (result.status_code==200)==exists
    if exists:
        assert result.json()["raw_expired"] is not raw
        docs=report(a,r["intake_id"],suffix="/transcript").json()["documents"]
        assert any(t["role"]=="user" for d in docs for t in d["turns"]) is raw
    else:
        with owner() as conn:assert conn.execute("SELECT count(*) FROM maeum.records WHERE payload->>'session_id'=%s",(sid,)).fetchone()[0]==0


def test_T15_delete_no_reappearance(env):
    a=verified();c,sid,r,payload,link=intake_case(a)
    response=c.post("/api/session/delete",json={"session_id":sid,"session_token":r["session_token"]})
    assert response.status_code==200
    assert report(a,r["intake_id"]).status_code==404
    assert c.post("/api/chat",json={"session_id":sid,"session_token":r["session_token"],"message":"계속"}).status_code in (401,403)
    assert exchange(client(),link).status_code==410
    with owner() as conn:
        assert conn.execute("SELECT count(*) FROM maeum.report_snapshots").fetchone()[0]==0
        assert conn.execute("SELECT count(*) FROM maeum.portal_reviews").fetchone()[0]==0


def test_T16_mail_failure_rate_limit_and_no_secret_response(env,monkeypatch):
    c=client();login(c)
    def fail(_):raise OSError("synthetic")
    monkeypatch.setattr(auth,"capture_mail",fail)
    assert post(c,"/auth/device-challenge").status_code==503
    assert c.get("/api/portal/intakes?org_id=A").status_code==403
    with owner() as conn:assert conn.execute("SELECT count(*) FROM maeum.device_challenges").fetchone()[0]==0
    for _ in range(20):post(client(),"/auth/login",{"email":"unknown@example.test","password":"wrong"})
    assert post(client(),"/auth/login",{"email":"unknown@example.test","password":"wrong"}).status_code==429


def test_T17_remote_legacy_and_no_store(env):
    c=verified()
    for path in ("/portal","/api/portal/me","/api/portal/intakes?org_id=A"):
        assert c.get(path).headers["cache-control"]=="no-store"
    remote=TestClient(app,base_url="http://example.test",client=("203.0.113.1",1000))
    for path in ("/stats.html","/api/stats","/api/stats/session","/api/review","/csv.js","/portal","/api/portal/me","/portal/app.js"):
        assert remote.get(path).status_code==404
    post(c,"/auth/logout")
    assert c.get("/api/portal/intakes?org_id=A").status_code==401


def test_T19_password_change_and_trust_expiry(env):
    c=verified()
    assert post(c,"/auth/password",{"current_password":PASSWORD,"new_password":"changed-synthetic-password"}).status_code==200
    assert c.get("/api/portal/me").status_code==401
    r=post(c,"/auth/login",{"email":"a0@example.test","password":"changed-synthetic-password"})
    assert r.json()["state"]=="pending_device"
    b=verified("b0@example.test")
    with owner() as conn:conn.execute("UPDATE maeum.trusted_devices SET expires_at=0 WHERE user_id='B0'")
    assert b.get("/api/portal/me").status_code==401
    assert login(b,"b0@example.test")["state"]=="pending_device"


def test_invitation_accept_requires_device_and_is_once(env):
    a=verified()
    assert post(a,"/invitations",{"org_id":"A","email":"new@example.test","permissions":["report:read"]}).status_code==200
    token=latest_mail("new@example.test","invitation")["token"]
    c=client()
    assert post(c,"/auth/accept-invitation",{"token":token,"password":PASSWORD}).status_code==200
    assert post(c,"/auth/accept-invitation",{"token":token,"password":PASSWORD}).status_code==410
    assert login(c,"new@example.test")["state"]=="pending_device"


def test_unassigned_legacy_not_visible_and_composite_fk(env):
    a=verified();_,_,r,_,_=intake_case(a)
    with owner() as conn:
        conn.execute("INSERT INTO maeum.records VALUES('conversation','legacy',%s,now())",(Jsonb({"session_id":"legacy","turns":[]}),))
    assert a.get("/api/portal/summary?org_id=A").json()["total"]==1
    with owner() as conn:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute("UPDATE maeum.report_snapshots SET org_id='B' WHERE intake_id=%s",(r["intake_id"],))

def test_database_context_requires_verified_session(env):
    a=verified();_,_,r,_,_=intake_case(a)
    with store.connect() as conn:
        with pytest.raises(Exception) as error:
            store.context(conn,"A0","A","report:read")
        assert error.value.status_code==403
    pending=client();login(pending)
    with store.connect() as conn:
        with pytest.raises(Exception) as error:
            store.context(conn,"A0","A","report:read",store.digest(pending.cookies.get(auth.SESSION)))
        assert error.value.status_code==403
    for table in ("portal_users","portal_sessions","trusted_devices","records"):
        with store.connect() as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(sql.SQL("SELECT * FROM maeum.{}").format(sql.Identifier(table)))
    with auth.connect() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT * FROM maeum.report_snapshots")


def test_T19_email_owner_verification_before_change(env):
    a=verified()
    assert post(a,"/auth/email-challenge",{"email":"changed@example.test","password":PASSWORD}).status_code==200
    with owner() as conn:assert conn.execute("SELECT email FROM maeum.portal_users WHERE id='A0'").fetchone()[0]=="a0@example.test"
    token=latest_mail("changed@example.test","email_change")["token"]
    assert post(a,"/auth/email-verify",{"token":"wrong"}).status_code==400
    assert post(a,"/auth/email-verify",{"token":token}).status_code==200
    assert a.get("/api/portal/me").status_code==401
    assert login(a,"changed@example.test")["state"]=="pending_device"


def test_T16_dependency_failures_are_clean_and_fail_closed(env,monkeypatch):
    a=verified()
    def fail(*args,**kwargs):
        raise psycopg.OperationalError("SYNTHETIC_PRIVATE_DIAGNOSTIC")
    monkeypatch.setattr(auth,"password_ok",fail)
    r=post(client(),"/auth/login",{"email":"a0@example.test","password":PASSWORD})
    assert r.status_code==503 and "SYNTHETIC_PRIVATE" not in r.text
    monkeypatch.undo()
    # Restore this fixture environment after undo resets it as well.
    for k,v in env.items():monkeypatch.setenv(k,v)
    monkeypatch.setenv("PORTAL_ORIGIN",ORIGIN)
    monkeypatch.setattr(store,"connect",fail)
    r=a.get("/api/portal/intakes?org_id=A")
    assert r.status_code==503 and "SYNTHETIC_PRIVATE" not in r.text


def test_T13_source_links_and_completion(env):
    a=verified();c,sid,r,_,_=intake_case(a)
    for message in ("한 달 전부터 잠을 잘 못 자요.","업무가 바뀌어 부담이 늘었어요.","쉬거나 산책하고 있어요.","친구가 도와주고 있어요.","마음이 편해지고 싶어요.","없음, 이대로 보내기"):
        response=c.post("/api/chat",json={"session_id":sid,"session_token":r["session_token"],"message":message})
        assert response.status_code==200
    detail=report(a,r["intake_id"]).json()
    docs=report(a,r["intake_id"],suffix="/transcript").json()["documents"]
    assert detail["status"]=="complete"
    assert detail["sources"]
    for slot,refs in detail["sources"].items():
        for ref in refs:
            turns=next(d["turns"] for d in docs if d["day"]==ref["day"])
            turn=next(t for t in turns if t["seq"]==ref["seq"])
            assert turn["role"]=="user"
            evidence=detail["summary"].get("slot_evidence",{}).get(slot,{})
            if evidence.get("source"):
                assert ref==evidence["source"]
            else:
                # Legacy projections without explicit evidence use verbatim
                # value matching as their bounded fallback.
                assert detail["summary"]["slots"][slot] in turn["text"]
    with owner() as conn:
        latest=conn.execute("SELECT payload FROM maeum.records WHERE kind='conversation' AND payload->>'session_id'=%s ORDER BY record_key DESC",(sid,)).fetchone()[0]
    assert detail["summary"]==latest["intake_snapshot"]


def test_T13_center_request_source_points_to_actual_user_turn(env):
    a=verified();c,sid,r,_,_=intake_case(a)
    for message in ("정서적인 어려움이에요.","세 달 전부터 잠을 잘 못 자요.",
                    "업무가 바뀌어 부담이 늘었어요.","쉬거나 산책하고 있어요.",
                    "친구가 도와주고 있어요.","마음이 편해지고 싶어요."):
        response=c.post("/api/chat",json={"session_id":sid,"session_token":r["session_token"],"message":message})
        assert response.status_code==200, response.text
        if response.json().get("closing",{}).get("stage")=="select":
            break
    response=c.post("/api/chat",json={"session_id":sid,"session_token":r["session_token"],"message":"센터에 묻고 싶은 것"})
    assert response.json()["closing"]["stage"]=="answer"
    response=c.post("/api/chat",json={"session_id":sid,"session_token":r["session_token"],"message":"SYNTHETIC-CENTER-QUESTION 주차가 가능한가요?"})
    assert response.json()["closing"]["stage"]=="confirm"
    response=c.post("/api/chat",json={"session_id":sid,"session_token":r["session_token"],"message":"이대로 보내기"})
    assert response.status_code==200 and response.json()["conversation_ended"] is True
    detail=report(a,r["intake_id"]).json()
    refs=detail["sources"]["center_request:0"]
    assert len(refs)==1 and refs[0]["role"]=="user"
    documents=report(a,r["intake_id"],suffix="/transcript").json()["documents"]
    turns=next(document["turns"] for document in documents if document["day"]==refs[0]["day"])
    turn=next(item for item in turns if item["seq"]==refs[0]["seq"])
    assert turn["role"]=="user" and turn["text"]=="SYNTHETIC-CENTER-QUESTION 주차가 가능한가요?"


def test_T15_concurrent_delete_and_read_and_chat(env):
    a=verified();c,sid,r,_,_=intake_case(a)
    def remove():
        return c.post("/api/session/delete",json={"session_id":sid,"session_token":r["session_token"]})
    def read():
        return report(a,r["intake_id"],suffix="/transcript")
    def talk():
        return c.post("/api/chat",json={"session_id":sid,"session_token":r["session_token"],"message":"산책하고 쉬고 있어요."})
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(f) for f in (remove,read,talk)]
        results=[f.result() for f in futures]
    assert results[0].status_code==200
    assert results[1].status_code in (200,404)
    assert results[2].status_code in (200,401,403,409)
    assert report(a,r["intake_id"],suffix="/transcript").status_code==404
    with owner() as conn:
        assert conn.execute("SELECT count(*) FROM maeum.records WHERE kind='conversation' AND payload->>'session_id'=%s",(sid,)).fetchone()[0]==0


def test_T20_local_retention_endpoint_and_original_modes(env,monkeypatch):
    a=verified();_,_,r,_,_=intake_case(a)
    c=client()
    assert c.get("/api/maintenance/retention").status_code==401
    secret=secrets.token_urlsafe(40);monkeypatch.setenv("CRON_SECRET",secret)
    assert c.get("/api/maintenance/retention",headers={"Authorization":"Bearer "+secret}).status_code==200
    assert report(a,r["intake_id"]).status_code==200

def test_T16_model_failure_rolls_back_without_fake_success(env,monkeypatch):
    import anthropic
    import httpx
    a=verified();c,sid,r,_,_=intake_case(a)
    before=report(a,r["intake_id"]).json()
    def fail(*args,**kwargs):
        raise anthropic.APIConnectionError(request=httpx.Request("POST","https://synthetic.invalid"))
    monkeypatch.setattr(chat,"handle_message",fail)
    response=c.post("/api/chat",json={"session_id":sid,"session_token":r["session_token"],"message":"추가 합성 발화"})
    assert response.status_code==502
    assert report(a,r["intake_id"]).json()==before

def test_T15_raw_expiry_cleans_serialized_summary_quotes(env):
    a=verified();_,sid,r,_,_=intake_case(a)
    marker="SYNTHETIC-RAW-QUOTE-ONLY"
    with owner() as conn:
        key,payload=conn.execute("SELECT record_key,payload FROM maeum.records WHERE kind='conversation' AND payload->>'session_id'=%s",(sid,)).fetchone()
        summary=payload["intake_snapshot"] | {
            "center_requests":[{"label":"요청","text":marker}],"sources":[marker],
            "slot_evidence":{"cause":{"status":"answered","source_text":marker}},
            "slot_revisions":[{"field":"cause","before":marker,"after":"산책"}],
            "request_results":{"synthetic":{"message":marker,"reply":marker}},
        }
        payload["intake_snapshot"]=summary
        payload["turns"].append({"seq":99,"role":"intake_summary","text":json.dumps(summary)})
        conn.execute("UPDATE maeum.records SET payload=%s WHERE kind='conversation' AND record_key=%s",(Jsonb(payload),key))
    cloud_store.purge_expired(today=date.today()+timedelta(days=91))
    with owner() as conn:
        remaining=conn.execute("SELECT payload FROM maeum.records WHERE kind='conversation' AND payload->>'session_id'=%s",(sid,)).fetchall()
        assert marker not in json.dumps(remaining)
        assert conn.execute("SELECT count(*) FROM maeum.records WHERE kind='session' AND record_key=%s",(sid,)).fetchone()[0]==0
    detail=report(a,r["intake_id"]).json()
    assert detail["raw_expired"] is True
    assert detail["sources"]=={} and marker not in json.dumps(detail)
    assert "slot_evidence" not in detail["summary"]
    assert "slot_revisions" not in detail["summary"]


def test_self_device_revoke_clears_browser_and_google_can_reenter(google_env):
    c, sent, _, _, _ = google_env
    google_start(c, sent)
    first = post(c, '/auth/google-exchange', {'code': 'synthetic-valid-auth-code'})
    assert first.status_code == 200
    c.headers['X-CSRF-Token'] = first.json()['csrf']
    devices = c.get('/api/portal/devices').json()
    current = [d for d in devices if d['current']]
    assert len(current) == 1
    old_token = c.cookies.get(auth.SESSION)
    result = post(c, '/devices/' + current[0]['id'], method='DELETE')
    assert result.status_code == 200
    assert result.json()['current_revoked'] is True
    assert not c.cookies.get(auth.SESSION) and not c.cookies.get(auth.NONCE)
    assert c.get('/api/portal/me').status_code == 401
    google_start(c, sent)
    response = post(c, '/auth/google-exchange', {'code': 'synthetic-valid-auth-code'})
    assert response.status_code == 200
    c.headers['X-CSRF-Token'] = response.json()['csrf']
    assert c.cookies.get(auth.SESSION) != old_token
    assert c.get('/api/portal/me').json()['state'] == 'verified'
    devices = c.get('/api/portal/devices').json()
    assert next(d for d in devices if d['id'] == current[0]['id'])['revoked'] is True
    assert len([d for d in devices if d['current'] and not d['revoked']]) == 1


@pytest.mark.parametrize('target,expected', [('/portal/admin','/portal/admin'),('/portal','/portal'),('https://evil.test','/portal'),('//evil.test','/portal'),({},'/portal')])
def test_google_fixed_return_paths(google_env, target, expected):
    c, sent, _, _, _ = google_env
    response = post(c, '/auth/google-start', {'return_to':target})
    assert response.status_code == 200
    sent['challenge'] = parse_qs(urlparse(response.json()['url']).query)['code_challenge'][0]
    response = post(c, '/auth/google-exchange', {'code':'synthetic-valid-auth-code'})
    assert response.status_code == 200
    assert response.json()['return_to'] == expected
    assert not c.cookies.get('maeum_google_return')


def test_testbed_requires_registrar_and_tenant_permission(email_env):
    admin=client();email_enter(admin)
    result=post(admin,'/testbed',{'org_id':'A','management_id':'real-case'})
    assert result.status_code == 200, result.text
    data=result.json()
    assert data['synthetic'] is True and data['management_id'].startswith('TEST-')
    assert data['management_id'] != 'real-case'
    assert len(data['management_id']) <= 32 and '#intake=' in data['url']
    assert post(admin,'/testbed',{'org_id':'B'}).status_code == 403
    with owner() as conn:
        rows=conn.execute('SELECT management_id FROM maeum.intake_links WHERE org_id=%s',('A',)).fetchall()
    assert [row[0] for row in rows] == [data['management_id']]
    staff=client();email_enter(staff,'a1@example.test')
    assert post(staff,'/testbed',{'org_id':'A'}).status_code == 403
    assert post(client(),'/testbed',{'org_id':'A'}).status_code == 401


def test_separate_portal_mode_routes(email_env):
    c=client()
    for path in ['/portal/admin','/portal/admin/']:
        r=c.get(path)
        assert r.status_code == 200 and 'data-portal-mode="admin"' in r.text
        assert '마음 접수 · 관리자 대시보드' in r.text
        assert r.headers['cache-control'] == 'no-store'
    r=c.get('/portal')
    assert 'data-portal-mode="institution"' in r.text
    assert '마음 접수 · 기관 포털' in r.text


def test_registrar_without_membership_can_login_but_cannot_access_tenants(google_env):
    c,sent,_,_,_=google_env
    with owner() as conn:
        conn.execute("UPDATE maeum.portal_users SET is_registrar=true WHERE id='A0'")
        conn.execute("UPDATE maeum.memberships SET active=false WHERE user_id='A0'")
    google_start(c,sent)
    response=post(c,'/auth/google-exchange',{'code':'synthetic-valid-auth-code'})
    assert response.status_code == 200,response.text
    c.headers['X-CSRF-Token']=response.json()['csrf']
    me=c.get('/api/portal/me').json()
    assert me['registrar'] is True and me['organizations'] == []
    assert c.get('/api/portal/organizations').status_code == 200
    assert c.get('/api/portal/intakes?org_id=A').status_code == 403
    assert post(c,'/testbed',{'org_id':'A'}).status_code == 403
    with owner() as conn:
        conn.execute("UPDATE maeum.portal_users SET is_registrar=false WHERE id='A0'")
    google_start(c,sent)
    assert post(c,'/auth/google-exchange',{'code':'synthetic-valid-auth-code'}).status_code == 403
