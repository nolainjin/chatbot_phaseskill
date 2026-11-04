"""Browser-bound Google PKCE login for pre-registered portal users."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app import portal_auth as auth, portal_config, portal_email, portal_supabase
from app.portal_config import Policy
from app.portal_store import digest

STATE = 'maeum_google_state'
PROVIDER_ERROR = 'Google 로그인을 확인하지 못했습니다. 다시 시도해 주세요.'
DENIED = '등록된 담당자 계정이 아닙니다. 가입 신청 후 관리자 승인을 받아 주세요.'


def enabled():
    return portal_email.enabled() and os.getenv('PORTAL_GOOGLE_LOGIN') == '1' and portal_config.cloud()


def verifier(state):
    message = json.dumps(['google-v1', state]).encode()
    value = hmac.new(os.environ['PORTAL_CODE_SECRET'].encode(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def start(request, response):
    auth.csrf(request)
    auth.limit('google-start-peer:' + digest(request.client.host), 30)
    state = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier(state).encode()).digest()).decode().rstrip('=')
    auth.cookie(response, STATE, state, Policy.load().code_seconds)
    return {'url': os.environ['SUPABASE_URL'] + '/auth/v1/authorize?' + urlencode({
        'provider': 'google', 'redirect_to': os.environ['PORTAL_ORIGIN'] + '/portal/google-return',
        'code_challenge': challenge, 'code_challenge_method': 's256', 'scopes': 'openid email profile'})}


def exchange(request, response, payload):
    outcome = 'denied'
    try:
        auth.csrf(request)
        auth.limit('google-verify-peer:' + digest(request.client.host), 60)
        code = payload.get('code')
        if not isinstance(code, str) or not 10 <= len(code) <= 512:
            raise HTTPException(400, PROVIDER_ERROR)
        state = request.cookies.get(STATE, '')
        if not 32 <= len(state) <= 128:
            raise HTTPException(400, 'Google 로그인을 시작한 브라우저에서 다시 시도해 주세요.')

        outcome, result = 'provider_error', {}
        try:
            try:
                result = portal_supabase.request_api('/token?grant_type=pkce', {
                    'auth_code': code, 'code_verifier': verifier(state)})
                identity = result.get('user', {})
                provider_id = str(UUID(identity.get('id', '')))
                email = portal_email.normalize(identity.get('email'))
                if not identity.get('email_confirmed_at'):
                    raise ValueError('Unconfirmed provider email')
            finally:
                # Discard tokens even when identity validation fails.
                portal_supabase.discard_provider_session(result if isinstance(result, dict) else {})
        except (HTTPException, ValueError, TypeError, AttributeError, OSError) as exc:
            raise HTTPException(400, PROVIDER_ERROR) from exc

        outcome = 'denied'
        with auth.connect() as conn:
            user = conn.execute('SELECT * FROM maeum.portal_users WHERE email=%s FOR UPDATE', (email,)).fetchone()
            if (not user or not user['active'] or not conn.execute(
                    'SELECT maeum.email_login_eligible(%s) AS ok', (user['id'],)).fetchone()['ok']
                    or (user['supabase_user_id'] and str(user['supabase_user_id']) != provider_id)):
                raise HTTPException(403, DENIED)
            if not user['supabase_user_id']:
                conn.execute('UPDATE maeum.portal_users SET supabase_user_id=%s WHERE id=%s', (provider_id, user['id']))
            if request.cookies.get(auth.SESSION):
                conn.execute('UPDATE maeum.portal_sessions SET revoked=true WHERE token_hash=%s',
                             (digest(request.cookies[auth.SESSION]),))
            policy, now = Policy.load(), time.time()
            device_id, device_token, nonce = str(uuid4()), secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            conn.execute('INSERT INTO maeum.trusted_devices VALUES(%s,%s,%s,%s,false,%s)',
                         (device_id, user['id'], digest(device_token), now + policy.email_session_seconds, now))
            token, csrf = auth.new_session(conn, user, nonce, 'verified', device_id,
                                           lifetime=policy.email_session_seconds)
        auth.cookie(response, auth.SESSION, token, policy.email_session_seconds)
        auth.cookie(response, auth.NONCE, nonce, policy.email_session_seconds)
        for name in [portal_email.ATTEMPT, portal_email.BROWSER, auth.DEVICE]:
            response.delete_cookie(name, path='/')
        outcome = 'ok'
        return {'state': 'verified', 'csrf': csrf}
    except HTTPException as exc:
        # FastAPI discards the injected Response when an exception is raised.
        # Return the error response explicitly so the one-use cookie is cleared.
        response = JSONResponse({'detail': exc.detail}, status_code=exc.status_code, headers=exc.headers)
        return response
    finally:
        response.delete_cookie(STATE, path='/')
        print(json.dumps({'event': 'portal_google_login', 'outcome': outcome}), flush=True)
