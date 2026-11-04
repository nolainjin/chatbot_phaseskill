"""Email-only login. Public applications never create an authorized identity.

The server binds each OTP attempt to an HttpOnly browser cookie and CSRF token.
Only a pre-registered, active identity can trigger a provider email or gain access.
Unknown addresses receive the same pending response and cannot inspect the directory.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from uuid import UUID, uuid4

from fastapi import HTTPException

from app import portal_auth as auth, portal_config
from app.portal_config import Policy
from app.portal_store import digest

ATTEMPT = 'maeum_email'
BROWSER = 'maeum_email_browser'
PUBLIC_MESSAGE = '등록된 이메일이라면 인증번호를 보냈습니다. 미등록 주소는 회원가입/신청을 이용해 주세요.'


def enabled():
    return os.getenv('PORTAL_EMAIL_LOGIN') == '1'


def normalize(value):
    if not isinstance(value, str):
        raise HTTPException(400, '이메일 주소를 확인해 주세요.')
    value = value.strip().lower()
    if (not 3 <= len(value) <= 254 or not value.isascii()
            or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", value)
            or len(value.split('@')[0]) > 64 or '..' in value):
        raise HTTPException(400, '이메일 주소를 확인해 주세요.')
    return value


def local_mac(row, code):
    message = json.dumps([row['token_hash'], row['nonce_hash'], row['email'], code]).encode()
    return hmac.new(os.environ['PORTAL_CODE_SECRET'].encode(), message, hashlib.sha256).hexdigest()


def start(request, response, payload):
    auth.csrf(request)
    email = normalize(payload.get('email'))
    policy, now = Policy.load(), time.time()
    # Admissions persist even if provider delivery or a later database write fails.
    auth.limit('email-login-cooldown:' + digest(email), 1, policy.resend_seconds)
    auth.limit('email-login-hour:' + digest(email), min(2, policy.sends_per_hour))
    auth.limit('email-login-peer:' + digest(request.client.host), 30)
    token, nonce, csrf = (secrets.token_urlsafe(32) for _ in range(3))
    row = {'token_hash': digest(token), 'nonce_hash': digest(nonce), 'email': email}
    code = f'{secrets.randbelow(100000000):08d}'
    with auth.connect() as conn:
        conn.execute('DELETE FROM maeum.email_login_attempts WHERE expires_at<%s', (now - 86400,))
        user = conn.execute('SELECT * FROM maeum.portal_users WHERE email=%s', (email,)).fetchone()
        eligible = bool(user and user['active'] and conn.execute(
            'SELECT maeum.email_login_eligible(%s) AS ok', (user['id'],)).fetchone()['ok'])
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('email-login:' + email,))
        conn.execute('UPDATE maeum.email_login_attempts SET consumed=true WHERE email=%s', (email,))
        conn.execute('INSERT INTO maeum.email_login_attempts(token_hash,nonce_hash,csrf,email,user_id,auth_version,code_mac,created_at,expires_at) '
                     'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                     (row['token_hash'], row['nonce_hash'], csrf, email, user['id'] if eligible else None,
                      user['auth_version'] if eligible else None, local_mac(row, code) if eligible and not portal_config.cloud() else None,
                      now, now + policy.code_seconds))
    ready = False
    if eligible:
        try:
            if portal_config.cloud():
                from app.portal_supabase import request_api
                auth.limit('email-provider-project', int(os.getenv('PORTAL_PROVIDER_EMAILS_PER_HOUR', '2')))
                request_api('/otp', {'email': email, 'create_user': not bool(user.get('supabase_user_id'))})
            else:
                auth.capture_mail({'purpose': 'login', 'to': email, 'code': code, 'created_at': now})
            ready = True
        except (HTTPException, OSError):
            # A provider failure must neither reveal registration nor refund quota.
            pass
    with auth.connect() as conn:
        conn.execute('UPDATE maeum.email_login_attempts SET provider_ready=%s WHERE token_hash=%s', (ready, row['token_hash']))
    auth.cookie(response, ATTEMPT, token, policy.code_seconds)
    auth.cookie(response, BROWSER, nonce, policy.code_seconds)
    return {'state': 'email_code', 'csrf': csrf, 'message': PUBLIC_MESSAGE, 'retry_after': policy.resend_seconds}


def attempt(conn, request):
    row = conn.execute('SELECT * FROM maeum.email_login_attempts WHERE token_hash=%s FOR UPDATE',
                       (digest(request.cookies.get(ATTEMPT, '')),)).fetchone()
    if not row or row['nonce_hash'] != digest(request.cookies.get(BROWSER, '')):
        raise HTTPException(401, '이메일을 입력해 인증번호를 다시 받아 주세요.')
    return row


def pending(request):
    with auth.connect() as conn:
        row = attempt(conn, request)
        if row['consumed'] or row['expires_at'] <= time.time():
            raise HTTPException(401, '이메일을 입력해 인증번호를 다시 받아 주세요.')
        return {'state': 'email_code', 'csrf': row['csrf'], 'email': row['email'], 'message': PUBLIC_MESSAGE}


def verify(request, response, payload):
    code = payload.get('code')
    if not isinstance(code, str) or not re.fullmatch(r'[0-9]{6,10}', code):
        raise HTTPException(400, '이메일에 표시된 숫자 인증번호를 입력해 주세요.')
    auth.csrf(request)
    auth.limit('email-verify-peer:' + digest(request.client.host), 60)
    policy, now, success = Policy.load(), time.time(), False
    with auth.connect() as conn:
        row = attempt(conn, request)
        auth.csrf(request, row)
        if not row['consumed'] and row['expires_at'] > now and row['attempts'] < policy.code_attempts:
            # Increment and commit even when the provider rejects an OTP.
            conn.execute('UPDATE maeum.email_login_attempts SET attempts=attempts+1 WHERE token_hash=%s', (row['token_hash'],))
            user = conn.execute('SELECT * FROM maeum.portal_users WHERE id=%s FOR UPDATE', (row['user_id'],)).fetchone()
            valid = bool(row['provider_ready'] and user and user['active'] and user['email'] == row['email']
                         and user['auth_version'] == row['auth_version'] and conn.execute(
                             'SELECT maeum.email_login_eligible(%s) AS ok', (user['id'],)).fetchone()['ok'])
            if valid and portal_config.cloud():
                from app.portal_supabase import request_api, discard_provider_session
                result = {}
                try:
                    result = request_api('/verify', {'email': row['email'], 'token': code, 'type': 'email'})
                    identity = result.get('user', {})
                    provider_id = str(UUID(identity.get('id', '')))
                    valid = (identity.get('email', '').lower() == row['email'] and bool(identity.get('email_confirmed_at'))
                             and (not user['supabase_user_id'] or str(user['supabase_user_id']) == provider_id))
                    if valid and not user['supabase_user_id']:
                        conn.execute('UPDATE maeum.portal_users SET supabase_user_id=%s WHERE id=%s', (provider_id, user['id']))
                except (HTTPException, ValueError, TypeError, AttributeError):
                    valid = False
                finally:
                    discard_provider_session(result)
            elif valid:
                valid = bool(row['code_mac'] and hmac.compare_digest(row['code_mac'], local_mac(row, code)))
            if valid:
                conn.execute('UPDATE maeum.email_login_attempts SET consumed=true WHERE token_hash=%s', (row['token_hash'],))
                conn.execute('UPDATE maeum.portal_sessions SET revoked=true WHERE token_hash=%s', (digest(request.cookies.get(auth.SESSION, '')),))
                device_id, device_token, nonce = str(uuid4()), secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                conn.execute('INSERT INTO maeum.trusted_devices VALUES(%s,%s,%s,%s,false,%s)',
                             (device_id, user['id'], digest(device_token), now + policy.session_seconds, now))
                token, csrf = auth.new_session(conn, user, nonce, 'verified', device_id)
                success = True
            else:
                conn.execute('UPDATE maeum.email_login_attempts SET consumed=(attempts >= %s) WHERE token_hash=%s',
                             (policy.code_attempts, row['token_hash']))
    if not success:
        raise HTTPException(400, '인증번호가 올바르지 않거나 만료되었습니다. 등록된 이메일인지 확인해 주세요.')
    auth.cookie(response, auth.SESSION, token, policy.session_seconds)
    auth.cookie(response, auth.NONCE, nonce, policy.session_seconds)
    for name in [ATTEMPT, BROWSER, auth.DEVICE]:
        response.delete_cookie(name, path='/')
    return {'state': 'verified', 'csrf': csrf}


def apply(request, payload):
    auth.csrf(request)
    email = normalize(payload.get('email'))
    auth.limit('registration-email:' + digest(email), 3, 86400)
    auth.limit('registration-peer:' + digest(request.client.host), 20)
    with auth.connect() as conn:
        now = time.time()
        conn.execute('DELETE FROM maeum.registration_requests WHERE status<>%s AND requested_at<%s', ('approved', now - 30 * 86400))
        conn.execute('INSERT INTO maeum.registration_requests(email,requested_at) VALUES(%s,%s) ON CONFLICT(email) DO NOTHING', (email, now))
    return {'received': True, 'message': '신청을 접수했습니다. 관리자가 이메일과 소속 기관을 확인해 등록하면 코드로 로그인할 수 있습니다.'}


def registrar(conn, request):
    row = auth.session(conn, request)
    if request.method != 'GET':
        auth.csrf(request, row)
    conn.execute("SELECT set_config('maeum.idle_seconds',%s,true)", (str(Policy.load().idle_seconds),))
    if not conn.execute('SELECT maeum.registrar_valid(%s) AS ok', (row['token_hash'],)).fetchone()['ok']:
        raise HTTPException(403, '이메일 등록 관리자만 이용할 수 있습니다.')
    return row


def directory(request):
    with auth.connect() as conn:
        row = registrar(conn, request)
        return conn.execute('SELECT maeum.email_directory(%s) AS document', (row['token_hash'],)).fetchone()['document']


def register(request, payload):
    email, org = normalize(payload.get('email')), payload.get('org_id')
    roles = {'summary': ['report:read'], 'counselor': ['report:read', 'raw:read', 'review:write'],
             'manager': ['report:read', 'raw:read', 'review:write', 'link:issue', 'member:manage', 'audit:read']}
    permissions = roles.get(payload.get('role'))
    if not isinstance(org, str) or not 1 <= len(org) <= 128 or not permissions:
        raise HTTPException(400, '소속 기관과 권한을 선택해 주세요.')
    with auth.connect() as conn:
        row = registrar(conn, request)
        # Serialize creation and approval of the same address across requests.
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('register:' + email,))
        existing = conn.execute('SELECT active FROM maeum.portal_users WHERE email=%s', (email,)).fetchone()
        if existing and not existing['active']:
            raise HTTPException(409, '정지된 계정입니다. 별도로 상태를 확인해 주세요.')
        if not conn.execute('SELECT 1 FROM maeum.organizations WHERE id=%s AND active', (org,)).fetchone():
            raise HTTPException(404, '기관을 찾을 수 없습니다.')
        uid = conn.execute('SELECT maeum.register_email(%s,%s,%s,%s) AS id', (row['token_hash'], email, org, permissions)).fetchone()['id']
    return {'registered': True, 'id': uid, 'message': '이메일을 등록했습니다. 해당 사용자가 이메일 코드로 로그인할 수 있습니다.'}


def reject(request, payload):
    email = normalize(payload.get('email'))
    with auth.connect() as conn:
        row = registrar(conn, request)
        conn.execute("UPDATE maeum.registration_requests SET status='rejected',decided_at=%s,decided_by=%s WHERE email=%s AND status='pending'",
                     (time.time(), row['user_id'], email))
    return {'updated': True}
