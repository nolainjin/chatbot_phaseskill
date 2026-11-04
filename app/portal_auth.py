"""Local password and capture-mail adapters plus server-side device verification.

External Auth/SMTP are deliberately unconfigured in P0-P4. Only the local runner
may enable these adapters. Authentication material is never placed in URLs/logs.
"""
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time
from uuid import uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from app.portal_config import Policy, cloud, session_idle_seconds
from app.portal_store import connect as database_connect, digest


def connect():
    return database_connect(authentication=True)

SESSION = "maeum_portal"
DEVICE = "maeum_device"
NONCE = "maeum_browser"


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return salt + ":" + value


def password_ok(password, encoded):
    salt = (encoded or "local-dummy:").split(":")[0]
    computed = hash_password(password, salt)
    return bool(encoded and hmac.compare_digest(computed, encoded))


def capture_mail(message):
    """Private local spool only. No SMTP/network fallback."""
    path = Path(os.environ["PORTAL_MAIL_DIR"])
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    target = path / (str(uuid4()) + ".json")
    with open(target, "x", opener=lambda p, f: os.open(p, f, 0o600)) as f:
        json.dump(message, f, ensure_ascii=False)


def cookie(response, name, value, max_age):
    # Insecure cookies are allowed only on the hard-gated loopback test server.
    response.set_cookie(name, value, httponly=True, samesite="strict",
                        secure=cloud(), path="/", max_age=max_age)


def session(conn, request, *, verified=True, response=None):
    if conn.execute('SELECT current_user AS role').fetchone()['role'] == "maeum_portal":
        with connect() as auth_conn:
            row = session(auth_conn, request, verified=verified, response=response)
        conn.execute("SELECT set_config('maeum.user',%s,true)", (row["user_id"],))
        return row
    token = request.cookies.get(SESSION, "")
    row = conn.execute("SELECT s.*,u.email,u.active,u.auth_version AS current_version "
                       "FROM maeum.portal_sessions s JOIN maeum.portal_users u ON u.id=s.user_id "
                       "WHERE s.token_hash=%s FOR UPDATE OF s", (digest(token),)).fetchone()
    now = time.time()
    if (not row or row["revoked"] or not row["active"] or row["auth_version"] != row["current_version"]
            or row["expires_at"] <= now or row["seen_at"] + session_idle_seconds() <= now
            or row["nonce_hash"] != digest(request.cookies.get(NONCE, ""))):
        raise HTTPException(401, "다시 로그인해 주세요.")
    if row["device_id"]:
        device = conn.execute("SELECT revoked,expires_at FROM maeum.trusted_devices WHERE id=%s AND user_id=%s", (row["device_id"], row["user_id"])).fetchone()
        if not device or device["revoked"] or device["expires_at"] <= now:
            raise HTTPException(401, "기기 확인이 필요합니다.")
    if verified and row["state"] != "verified":
        raise HTTPException(403, "이메일 기기 확인이 필요합니다.")
    if response is not None and os.getenv('PORTAL_EMAIL_LOGIN') == '1' and row['state'] == 'verified':
        deadline = row['created_at'] + Policy.load().email_session_seconds
        # Upgrade an existing live 8-hour login once. Never revive an expired or
        # revoked session, and never move the deadline beyond its original login.
        if row['expires_at'] < deadline - 1:
            conn.execute('UPDATE maeum.portal_sessions SET expires_at=%s WHERE token_hash=%s',
                         (deadline, row['token_hash']))
            if row['device_id']:
                conn.execute('UPDATE maeum.trusted_devices SET expires_at=greatest(expires_at,%s) WHERE id=%s AND user_id=%s',
                             (deadline, row['device_id'], row['user_id']))
            row['expires_at'] = deadline
            remaining = max(1, int(deadline - now))
            cookie(response, SESSION, token, remaining)
            cookie(response, NONCE, request.cookies[NONCE], remaining)
    conn.execute("UPDATE maeum.portal_sessions SET seen_at=%s WHERE token_hash=%s", (now, row["token_hash"]))
    conn.execute("SELECT set_config('maeum.user',%s,true)", (row["user_id"],))
    return row


def csrf(request, row=None):
    expected = os.environ["PORTAL_ORIGIN"]
    if request.headers.get("origin") != expected:
        raise HTTPException(403, "요청 출처가 올바르지 않습니다.")
    if row is not None and not hmac.compare_digest(request.headers.get("x-csrf-token", ""), row["csrf"]):
        raise HTTPException(403, "화면을 새로 열고 다시 시도해 주세요.")


def limit(key, count=20, seconds=3600):
    """Durable admission; committed separately even when subsequent auth fails."""
    now = time.time()
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("portal-limit:" + key,))
        row = conn.execute("SELECT stamps FROM maeum.portal_limits WHERE id=%s", (key,)).fetchone()
        stamps = [v for v in (row["stamps"] if row else []) if v > now - seconds]
        denied = len(stamps) >= count
        if not denied:
            stamps.append(now)
        conn.execute("INSERT INTO maeum.portal_limits VALUES(%s,%s) ON CONFLICT(id) DO UPDATE SET stamps=excluded.stamps", (key, Jsonb(stamps)))
    if denied:
        raise HTTPException(429, "잠시 후 다시 시도해 주세요.")


def new_session(conn, user, nonce, state, device_id=None, *, lifetime=None):
    now, policy = time.time(), Policy.load()
    token, csrf_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    conn.execute("INSERT INTO maeum.portal_sessions(token_hash,user_id,auth_version,state,device_id,nonce_hash,csrf,created_at,seen_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                 (digest(token), user["id"], user["auth_version"], state, device_id, digest(nonce), csrf_token, now, now, now + (lifetime if lifetime is not None else policy.session_seconds)))
    return token, csrf_token


def login(request, response, payload):
    csrf(request)
    email, password = payload.get("email"), payload.get("password")
    if not isinstance(email, str) or not isinstance(password, str) or len(email) > 254 or len(password) > 1024:
        raise HTTPException(400, "로그인 정보를 확인해 주세요.")
    email = email.strip().lower()
    limit("login-email:" + digest(email))
    limit("login-peer:" + digest(request.client.host), count=60)
    with connect() as conn:
        user = conn.execute("SELECT * FROM maeum.portal_users WHERE email=%s", (email,)).fetchone()
        if cloud():
            from app.portal_supabase import password_login
            valid = password_login(email, password, user)
        else:
            valid = password_ok(password, user["password_hash"] if user else None)
        if not valid or not user["active"]:
            raise HTTPException(401, "로그인 정보를 확인해 주세요.")
        device = conn.execute("SELECT id FROM maeum.trusted_devices WHERE token_hash=%s AND user_id=%s AND NOT revoked AND expires_at>%s",
                              (digest(request.cookies.get(DEVICE, "")), user["id"], time.time())).fetchone()
        state = "verified" if device else "pending_device"
        nonce = secrets.token_urlsafe(32)
        token, csrf_token = new_session(conn, user, nonce, state, device["id"] if device else None)
        # A new login revokes the old browser session; trust cookie alone never logs in.
        conn.execute("UPDATE maeum.portal_sessions SET revoked=true WHERE token_hash=%s", (digest(request.cookies.get(SESSION, "")),))
    cookie(response, SESSION, token, Policy.load().session_seconds)
    cookie(response, NONCE, nonce, Policy.load().session_seconds)
    return {"state": state, "csrf": csrf_token}


def code_mac(row, code):
    key = os.environ["PORTAL_CODE_SECRET"]
    if len(key) < 32:
        raise RuntimeError("Portal code MAC key must be configured")
    data = json.dumps(["device", row["user_id"], row["email"], row["token_hash"], row["nonce_hash"], code])
    return hmac.new(key.encode(), data.encode(), hashlib.sha256).hexdigest()


def challenge(request):
    if cloud():
        from app.portal_supabase import challenge as cloud_challenge
        return cloud_challenge(request)
    with connect() as conn:
        row = session(conn, request, verified=False)
        csrf(request, row)
        if row["state"] != "pending_device":
            raise HTTPException(409, "이미 확인된 기기입니다.")
        # Serialize sends across pending sessions for the same user.
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("mail:" + row["user_id"],))
        now, policy = time.time(), Policy.load()
        recent = conn.execute("SELECT created_at FROM maeum.device_challenges WHERE user_id=%s AND created_at>%s ORDER BY created_at DESC", (row["user_id"], now - 3600)).fetchall()
        if len(recent) >= policy.sends_per_hour or (recent and recent[0]["created_at"] + policy.resend_seconds > now):
            raise HTTPException(429, "인증번호 재전송 대기 시간이 남아 있습니다.")
        conn.execute("UPDATE maeum.device_challenges SET consumed=true WHERE session_hash=%s", (row["token_hash"],))
        code = f"{secrets.randbelow(100000000):08d}"
        conn.execute("INSERT INTO maeum.device_challenges(id,session_hash,user_id,code_mac,created_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s)",
                     (str(uuid4()), row["token_hash"], row["user_id"], code_mac(row, code), now, now + policy.code_seconds))
        try:
            capture_mail({"purpose": "device", "to": row["email"], "code": code, "created_at": now})
        except OSError as exc:
            raise HTTPException(503, "인증 메일을 준비하지 못했습니다. 다시 시도해 주세요.") from exc
    return {"sent": True, "capture_only": True, "retry_after": policy.resend_seconds}


def verify(request, response, payload):
    if cloud():
        raise HTTPException(400, '이메일의 확인 링크를 같은 브라우저에서 열어 주세요.')
    code = payload.get("code")
    if not isinstance(code, str) or len(code) != 8 or not code.isascii() or not code.isdigit():
        raise HTTPException(400, "8자리 인증번호를 입력해 주세요.")
    if type(payload.get("remember", False)) is not bool:
        raise HTTPException(400, "기기 기억 여부를 확인해 주세요.")
    failure = False
    with connect() as conn:
        row = session(conn, request, verified=False)
        csrf(request, row)
        if row["state"] != "pending_device":
            raise HTTPException(409, "이미 확인된 기기입니다.")
        c = conn.execute("SELECT * FROM maeum.device_challenges WHERE session_hash=%s AND NOT consumed ORDER BY created_at DESC LIMIT 1 FOR UPDATE", (row["token_hash"],)).fetchone()
        now, policy = time.time(), Policy.load()
        if not c or c["expires_at"] <= now or c["attempts"] >= policy.code_attempts:
            failure = True
        elif not hmac.compare_digest(c["code_mac"], code_mac(row, code)):
            conn.execute("UPDATE maeum.device_challenges SET attempts=attempts+1,consumed=(attempts+1 >= %s) WHERE id=%s", (policy.code_attempts, c["id"]))
            failure = True
        else:
            conn.execute("UPDATE maeum.device_challenges SET consumed=true WHERE id=%s", (c["id"],))
            conn.execute("UPDATE maeum.portal_sessions SET revoked=true WHERE token_hash=%s", (row["token_hash"],))
            device_id = str(uuid4())
            device_token = secrets.token_urlsafe(32)
            # Even an unremembered session has a revocable device record.
            expiry = now + (policy.device_seconds if payload.get("remember") else policy.session_seconds)
            conn.execute("INSERT INTO maeum.trusted_devices VALUES(%s,%s,%s,%s,false,%s)",
                         (device_id, row["user_id"], digest(device_token), expiry, now))
            nonce = secrets.token_urlsafe(32)
            token, csrf_token = new_session(conn, {"id": row["user_id"], "auth_version": row["auth_version"]}, nonce, "verified", device_id)
    if failure:
        raise HTTPException(400, "인증번호가 올바르지 않거나 만료되었습니다.")
    cookie(response, SESSION, token, policy.session_seconds)
    cookie(response, NONCE, nonce, policy.session_seconds)
    if payload.get("remember"):
        cookie(response, DEVICE, device_token, policy.device_seconds)
    else:
        response.delete_cookie(DEVICE, path="/")
    return {"state": "verified", "csrf": csrf_token}
