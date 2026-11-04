"""Password authentication + browser-bound PKCE email verification.

The publishable key is used here, never the service/admin key. Provider tokens
are discarded/revoked; the existing app session remains the authorization gate.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import HTTPException
from app import portal_auth as auth
from app.portal_config import Policy
from app.portal_store import digest


def request_api(path, body, *, access_token=None):
    headers = {'apikey': os.environ['SUPABASE_PUBLISHABLE_KEY']}
    if access_token:
        headers['Authorization'] = 'Bearer ' + access_token
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            r = client.post(os.environ['SUPABASE_URL'] + '/auth/v1' + path,
                            headers=headers, json=body)
        if r.status_code >= 400:
            if r.status_code == 429:
                raise HTTPException(429, '인증 서비스의 발송 제한입니다. 잠시 후 다시 시도해 주세요.')
            raise HTTPException(401 if r.status_code in (400, 401, 403, 422) else 503,
                                '인증을 완료하지 못했습니다. 입력과 이메일 링크를 확인해 주세요.')
        return r.json() if r.content else {}
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, '인증 서비스에 연결하지 못했습니다.') from exc


def discard_provider_session(result):
    token = result.get('access_token')
    if token:
        try:
            request_api('/logout?scope=local', {}, access_token=token)
        except HTTPException:
            # No provider token is ever granted to the browser or persisted.
            pass


def password_login(email, password, local_user):
    # Owner-only trial: only provisioned identities can cause provider requests.
    if not local_user or not local_user['active'] or not local_user.get('supabase_user_id'):
        return False
    try:
        result = request_api('/token?grant_type=password', {'email': email, 'password': password})
    except HTTPException as exc:
        if exc.status_code == 401:
            return False
        raise
    try:
        user = result.get('user', {})
        return (user.get('id') == str(local_user['supabase_user_id'])
                and user.get('email', '').lower() == email and bool(user.get('email_confirmed_at')))
    finally:
        discard_provider_session(result)


def verifier(row, challenge_id):
    # Derive instead of persisting a recoverable PKCE verifier in the database.
    message = json.dumps(['pkce-v1', challenge_id, row['token_hash'], row['nonce_hash']]).encode()
    value = hmac.new(os.environ['PORTAL_CODE_SECRET'].encode(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def challenge(request):
    with auth.connect() as conn:
        row = auth.session(conn, request, verified=False)
        auth.csrf(request, row)
        if row['state'] != 'pending_device':
            raise HTTPException(409, '이미 확인된 기기입니다.')
        # Admission commits independently: provider errors/timeouts must not
        # refund the send budget or allow repeated requests to the provider.
        auth.limit('provider-mail-cooldown:' + row['user_id'], count=1, seconds=Policy.load().resend_seconds)
        auth.limit('provider-mail-hour:' + row['user_id'], count=min(2, Policy.load().sends_per_hour))
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ('mail:' + row['user_id'],))
        now, policy = time.time(), Policy.load()
        recent = conn.execute('SELECT created_at FROM maeum.device_challenges WHERE user_id=%s AND created_at>%s ORDER BY created_at DESC',
                              (row['user_id'], now - 3600)).fetchall()
        if len(recent) >= policy.sends_per_hour or (recent and recent[0]['created_at'] + policy.resend_seconds > now):
            raise HTTPException(429, '인증 메일 재전송 대기 시간이 남아 있습니다.')
        challenge_id, state = str(uuid4()), secrets.token_urlsafe(32)
        code_challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier(row, challenge_id).encode()).digest()).decode().rstrip('=')
        conn.execute('UPDATE maeum.device_challenges SET consumed=true WHERE user_id=%s', (row['user_id'],))
        conn.execute('INSERT INTO maeum.device_challenges(id,session_hash,user_id,code_mac,created_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s)',
                     (challenge_id, row['token_hash'], row['user_id'], digest(state), now, now + policy.code_seconds))
        redirect = os.environ['PORTAL_ORIGIN'] + '/portal/auth-return?' + urlencode({'state': state})
        request_api('/otp?' + urlencode({'redirect_to': redirect}),
                    {'email': row['email'], 'create_user': False,
                     'code_challenge': code_challenge, 'code_challenge_method': 's256'})
    return {'sent': True, 'verification': 'email_link', 'retry_after': policy.resend_seconds}


def exchange(request, response, payload):
    code, state = payload.get('code'), payload.get('state')
    if (not isinstance(code, str) or not 10 <= len(code) <= 512 or not isinstance(state, str)
            or not 32 <= len(state) <= 128 or type(payload.get('remember', False)) is not bool):
        raise HTTPException(400, '이메일 확인 링크를 다시 열어 주세요.')
    failure = False
    with auth.connect() as conn:
        row = auth.session(conn, request, verified=False)
        auth.csrf(request, row)
        if row['state'] != 'pending_device':
            raise HTTPException(409, '이미 확인되었거나 사용할 수 없는 요청입니다.')
        c = conn.execute('SELECT * FROM maeum.device_challenges WHERE session_hash=%s AND NOT consumed ORDER BY created_at DESC LIMIT 1 FOR UPDATE',
                         (row['token_hash'],)).fetchone()
        now, policy = time.time(), Policy.load()
        if not c or c['expires_at'] <= now or c['attempts'] >= policy.code_attempts or not hmac.compare_digest(c['code_mac'], digest(state)):
            raise HTTPException(400, '인증 링크가 올바르지 않거나 만료되었습니다.')
        try:
            result = request_api('/token?grant_type=pkce', {'auth_code': code, 'code_verifier': verifier(row, c['id'])})
            user = result.get('user', {})
            mapped = conn.execute('SELECT supabase_user_id FROM maeum.portal_users WHERE id=%s', (row['user_id'],)).fetchone()
            valid = (user.get('id') == str(mapped['supabase_user_id']) and user.get('email', '').lower() == row['email']
                     and bool(user.get('email_confirmed_at')))
            discard_provider_session(result)
        except HTTPException:
            valid = False
        if not valid:
            conn.execute('UPDATE maeum.device_challenges SET attempts=attempts+1,consumed=(attempts+1 >= %s) WHERE id=%s', (policy.code_attempts, c['id']))
            failure = True
        else:
            conn.execute('UPDATE maeum.device_challenges SET consumed=true WHERE id=%s', (c['id'],))
            conn.execute('UPDATE maeum.portal_sessions SET revoked=true WHERE token_hash=%s', (row['token_hash'],))
            device_id, device_token, nonce = str(uuid4()), secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            expiry = now + (policy.device_seconds if payload.get('remember') else policy.session_seconds)
            conn.execute('INSERT INTO maeum.trusted_devices VALUES(%s,%s,%s,%s,false,%s)',
                         (device_id, row['user_id'], digest(device_token), expiry, now))
            token, csrf_token = auth.new_session(conn, {'id': row['user_id'], 'auth_version': row['auth_version']}, nonce, 'verified', device_id)
    if failure:
        raise HTTPException(400, '인증 링크를 확인하지 못했습니다. 같은 브라우저에서 다시 시도해 주세요.')
    auth.cookie(response, auth.SESSION, token, policy.session_seconds)
    auth.cookie(response, auth.NONCE, nonce, policy.session_seconds)
    if payload.get('remember'):
        auth.cookie(response, auth.DEVICE, device_token, policy.device_seconds)
    else:
        response.delete_cookie(auth.DEVICE, path='/')
    return {'state': 'verified', 'csrf': csrf_token}
