"""FastAPI application with a default-dark public boundary."""

import hashlib
import hmac
import ipaddress
import logging
import os
import re
import secrets
import anthropic
import psycopg
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Body, Cookie, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app import access_log, chat, cloud_store, consent, intake, ratelimit, referral, retention, review, stats, storage
from app.config import Settings
from app import portal_config

MAX_MESSAGE_LEN = 2000
MIN_STATS_TOKEN_LEN = 16
MAX_STATS_AUTH_FAILURES = 30
STATIC_DIR = "static"
logger = logging.getLogger(__name__)
_PUBLIC_TERMINAL_SAFETY_NOTICE = (
    " 위기 상황이거나 스스로를 해칠까 걱정된다면 자살예방상담전화 109, "
    "생명의전화 1588-9191 또는 119에 바로 연락해 주세요."
)
_LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_PRIVATE_TEST_HOST = "testserver"
_PRIVATE_LOCAL_UI_ENV = "PRIVATE_LOCAL_UI"
_PUBLIC_CHAT_UI_ENV = "PUBLIC_CHAT_UI"

_STATS_COOKIE_NAME = "lmwiki_stats_session"
_ADMIN_PATHS = frozenset(
    {"/stats.html", "/stats.js", "/csv.js", "/api/stats", "/api/stats/session", "/api/review", "/api/admin/links"}
)
_MANAGEMENT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,31}")
_INVALID_LINK_NOTICE = "링크가 올바르지 않아요. 센터에 다시 요청해 주세요."
# Every request is dark unless explicit private mode proves both a loopback
# Host header and a loopback transport peer.
_DARK_RESPONSE_BODY = b'{"detail":"public service disabled"}'

@asynccontextmanager
async def lifespan(_app):
    if portal_config.enabled():
        from app.portal_store import require_database_url
        require_database_url(os.environ.get("MAEUM_DATABASE_URL", ""))
        if not portal_config.cloud() and Settings.from_env().model != "fake":
            raise RuntimeError("P0-P4 portal requires MODEL=fake; external connection is not enabled")
    if os.getenv("VERCEL") == "1":
        settings = Settings.from_env()
        if not cloud_store.enabled():
            raise RuntimeError("Vercel requires MAEUM_DATABASE_URL; local disk is not durable.")
        if settings.model in {"auto", "claude-cli", "codex-cli"} or settings.model.startswith("codex-cli:"):
            raise RuntimeError("Vercel requires an API model or explicit fake test mode; CLI models are disabled.")
        if len(os.getenv("PARTICIPANT_TICKET_SECRET", "")) < 32:
            raise RuntimeError("Vercel requires a stable PARTICIPANT_TICKET_SECRET.")
        if settings.model.startswith("claude-") and not settings.anthropic_api_key:
            raise RuntimeError("Vercel requires ANTHROPIC_API_KEY for the configured Claude model.")
    settings = Settings.from_env()
    consent.load_privacy(settings.knowledge_dir, settings)
    intake.load_schema(settings.knowledge_dir)
    referral.load_map(Path(settings.knowledge_dir) / referral.MAP_FILENAME)
    yield


app = FastAPI(lifespan=lifespan)


@app.exception_handler(psycopg.Error)
async def cloud_storage_unavailable(_request, exc):
    logger.error("Cloud storage unavailable (%s)", type(exc).__name__)
    return JSONResponse(status_code=503, headers={"Retry-After": "3"},
                        content={"detail": "기록 저장소 연결이 지연되고 있습니다. 잠시 후 다시 시도해 주세요."})


@app.exception_handler(anthropic.APIError)
async def cloud_model_unavailable(_request, exc):
    logger.error("Claude API unavailable (%s)", type(exc).__name__)
    return JSONResponse(status_code=502,
                        content={"detail": "답변을 만들지 못했습니다. 잠시 후 다시 시도해 주세요." + _PUBLIC_TERMINAL_SAFETY_NOTICE})


_rate_limiter = ratelimit.RateLimiter()
_participant_secret = os.environ.get("PARTICIPANT_TICKET_SECRET", "").encode("utf-8")
if len(_participant_secret) < 32:
    _participant_secret = secrets.token_bytes(32)
_stats_auth_failures: dict[str, list[str]] = {}
_deletion_auth_failures: dict[str, list[str]] = {}


def _loopback_request(hostname: str, peer: str) -> bool:
    try:
        peer_is_loopback = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        peer_is_loopback = peer == "testclient" and hostname == _PRIVATE_TEST_HOST
    return hostname in _LOCAL_HOSTS | {_PRIVATE_TEST_HOST} and peer_is_loopback


def _private_local_request(hostname: str, peer: str) -> bool:
    return (
        os.environ.get(_PRIVATE_LOCAL_UI_ENV, "").strip().lower()
        in {"1", "true", "yes"}
        and _loopback_request(hostname, peer)
    )


def _public_chat_enabled() -> bool:
    return os.environ.get(_PUBLIC_CHAT_UI_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _sign_participant_id(participant_id: str) -> str:
    digest = hmac.new(_participant_secret, participant_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"v1.{digest}"


def _verify_participant_ticket(participant_id: str, ticket: str | None) -> bool:
    if not isinstance(ticket, str) or not ticket or not storage.valid_participant_id(participant_id):
        return False
    return hmac.compare_digest(ticket.encode("utf-8"), _sign_participant_id(participant_id).encode("utf-8"))


def _valid_management_id(value) -> bool:
    return (isinstance(value, str) and _MANAGEMENT_ID_RE.fullmatch(value) is not None
            and storage.valid_participant_id(value))


def _new_participant_id() -> str:
    return "p_" + secrets.token_hex(16)


def _failure_allowed(ip: str, failures: dict) -> bool:
    if cloud_store.enabled():
        kind = "stats" if failures is _stats_auth_failures else "deletion"
        return cloud_store.auth_failure(kind, ip, limit=MAX_STATS_AUTH_FAILURES)
    now = datetime.now(timezone.utc)
    retained = []
    for ts in failures.get(ip, []):
        try:
            if now - datetime.fromisoformat(ts) < ratelimit.WINDOW:
                retained.append(ts)
        except ValueError:
            continue
    failures[ip] = retained
    return len(retained) < MAX_STATS_AUTH_FAILURES


def _stats_failure_allowed(ip: str) -> bool:
    return _failure_allowed(ip, _stats_auth_failures)


def _record_stats_failure(ip: str) -> None:
    if cloud_store.enabled():
        cloud_store.auth_failure("stats", ip, record=True)
        return
    _stats_auth_failures.setdefault(ip, []).append(datetime.now(timezone.utc).isoformat())


@app.middleware("http")
async def default_dark_boundary(request: Request, call_next):
    """Default dark; permit private loopback or an explicitly enabled public chat surface."""
    hostname = (request.url.hostname or "").lower()
    peer = request.client.host if request.client else ""
    is_portal = request.url.path.startswith(("/portal", "/api/portal", "/api/intake-link", "/static/portal"))
    cloud_portal = portal_config.cloud() and portal_config.enabled()
    if cloud_portal:
        from urllib.parse import urlparse
        if hostname != urlparse(os.getenv('PORTAL_ORIGIN', '')).hostname:
            return Response(status_code=404)
        # Account provisioning/identity mutation is not enabled for the owner-only cloud trial.
        if request.url.path in {'/api/portal/invitations','/api/portal/auth/accept-invitation',
                               '/api/portal/auth/password','/api/portal/auth/email-challenge','/api/portal/auth/email-verify'}:
            return Response(status_code=404)
    if is_portal and (not portal_config.enabled() or (not cloud_portal and (not portal_config.local_only() or not _loopback_request(hostname, peer)))):
        return Response(status_code=404)
    if portal_config.enabled() and not cloud_portal and not _loopback_request(hostname, peer):
        return Response(status_code=404)
    if request.url.path in _ADMIN_PATHS and not _loopback_request(hostname, peer):
        return Response(
            content=_DARK_RESPONSE_BODY,
            status_code=404,
            media_type="application/json",
        )
    private_local_ui = _private_local_request(hostname, peer)
    public_chat_ui = _public_chat_enabled()
    if not private_local_ui and not public_chat_ui:
        return Response(
            content=_DARK_RESPONSE_BODY,
            status_code=404,
            media_type="application/json",
        )
    response = await call_next(request)
    if is_portal or portal_config.enabled():
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
    return response


@app.post("/api/chat")
def post_chat(request: Request, payload: dict = Body(...)):
    with cloud_store.session_scope(payload.get("session_id")):
        if portal_config.enabled():
            from app.portal_store import require_bound_session
            require_bound_session(payload.get("session_id"))
        return _post_chat(request, payload)


def _post_chat(request: Request, payload: dict):
    session_id = payload.get("session_id")
    message = payload.get("message")
    participant_id = payload.get("participant_id")
    participant_ticket = payload.get("participant_ticket")
    session_token = payload.get("session_token")

    # session_id는 파일명이 되므로 API 경계에서 화이트리스트를 강제한다 —
    # 통과 못 하면 400. 아래 storage 층 검증까지 내려가 500으로 새는 걸 막는다.
    if not isinstance(session_id, str) or not storage.valid_session_id(session_id):
        raise HTTPException(status_code=400, detail="session_id 형식이 올바르지 않습니다.")
    if not isinstance(message, str) or not message.strip():
        raise HTTPException(status_code=400, detail="message는 비어있지 않은 문자열이어야 합니다.")
    if len(message) > MAX_MESSAGE_LEN:
        raise HTTPException(status_code=400, detail=f"message는 {MAX_MESSAGE_LEN}자를 넘을 수 없습니다.")
    bound_participant_id = None
    if participant_id is not None:
        if not isinstance(participant_id, str) or not storage.valid_participant_id(participant_id):
            raise HTTPException(status_code=400, detail="participant_id 형식이 올바르지 않습니다.")
        if isinstance(participant_ticket, str) and _verify_participant_ticket(participant_id, participant_ticket):
            bound_participant_id = participant_id
        else:
            # Legacy/browser supplied ids are treated as untrusted labels, not as
            # record ownership. A new server-issued participant id is minted below.
            bound_participant_id = None
    if session_token is not None and (
        not isinstance(session_token, str) or len(session_token) > 128
    ):
        raise HTTPException(status_code=400, detail="session_token 형식이 올바르지 않습니다.")

    with storage.data_lock():
        settings = Settings.from_env()
        privacy = consent.load_privacy(settings.knowledge_dir, settings)
        session = chat._sessions.get(session_id)
        if session is not None and retention.session_retired(session):
            chat._sessions.pop(session_id, None)
            raise HTTPException(status_code=401, detail="만료되거나 삭제된 세션입니다." + _PUBLIC_TERMINAL_SAFETY_NOTICE)
        if privacy is not None and not (
            session and session.consented_at
            and session.consent_version == privacy.consent_version
            and session.consent_pack == str(Path(settings.knowledge_dir).resolve())
        ):
            raise HTTPException(status_code=409, detail="개인정보 처리 동의가 필요합니다." + _PUBLIC_TERMINAL_SAFETY_NOTICE)

        session_was_known = chat.has_session(session_id)
        if session_was_known:
            if not chat.owns_session(session_id, session_token):
                raise HTTPException(status_code=401, detail="세션 인증이 필요합니다.")
        elif storage.conversation_exists(session_id):
            raise HTTPException(status_code=401, detail="만료된 세션입니다. 새 세션으로 시작해 주세요.")

        ip = ratelimit.client_ip(request, settings.trust_proxy_hops)
        try:
            _rate_limiter.check(ip, session_id, daily_cap=settings.daily_request_cap)
        except ratelimit.RateLimitExceeded as exc:
            raise HTTPException(status_code=429, detail=str(exc) + _PUBLIC_TERMINAL_SAFETY_NOTICE) from exc

        if not session_was_known and bound_participant_id is None:
            bound_participant_id = _new_participant_id()
        result = chat.handle_message(session_id, message, participant_id=bound_participant_id)
        if not session_was_known:
            issued_participant = bound_participant_id or session_id
            result["session_token"] = chat.session_token(session_id)
            result["participant_id"] = issued_participant
            result["participant_ticket"] = _sign_participant_id(issued_participant)
        return result


@app.post("/api/consent")
def post_consent(request: Request, payload: dict = Body(...)):
    if portal_config.enabled():
        from app.portal_store import consent_scope
        from app.portal_auth import csrf
        csrf(request)
        return consent_scope(request, payload, _post_consent)
    with cloud_store.session_scope(payload.get("session_id")):
        return _post_consent(request, payload)


def _post_consent(request: Request, payload: dict):
    settings = Settings.from_env()
    privacy = consent.load_privacy(settings.knowledge_dir, settings)
    if privacy is None:
        raise HTTPException(status_code=409, detail="이 팩은 별도 동의 단계가 없습니다.")
    accepted = payload.get("accepted")
    if type(accepted) is not bool:
        raise HTTPException(status_code=400, detail="accepted는 boolean이어야 합니다.")
    if payload.get("consent_version") != privacy.consent_version:
        raise HTTPException(status_code=409, detail="고지 버전이 바뀌었습니다. 다시 읽어 주세요." + _PUBLIC_TERMINAL_SAFETY_NOTICE)
    linked_id = None
    if "management_id" in payload or "link_ticket" in payload:
        management_id, ticket = payload.get("management_id"), payload.get("link_ticket")
        if not (_valid_management_id(management_id) and isinstance(ticket, str)
                and len(ticket) <= 128 and _verify_participant_ticket(management_id, ticket)):
            raise HTTPException(status_code=400, detail=_INVALID_LINK_NOTICE + _PUBLIC_TERMINAL_SAFETY_NOTICE)
        linked_id = management_id
    if not accepted:
        return {"accepted": False, "reply": "말로 하기 어려우면 전화로도 도움을 받을 수 있어요." + _PUBLIC_TERMINAL_SAFETY_NOTICE}
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not storage.valid_session_id(session_id):
        raise HTTPException(status_code=400, detail="session_id 형식이 올바르지 않습니다.")
    with storage.data_lock():
        if chat.has_session(session_id) or storage.conversation_exists(session_id):
            raise HTTPException(status_code=409, detail="이미 사용한 세션입니다. 새 대화로 시작해 주세요.")
        ip = ratelimit.client_ip(request, settings.trust_proxy_hops)
        try:
            _rate_limiter.check(ip, session_id, daily_cap=settings.daily_request_cap)
        except ratelimit.RateLimitExceeded as exc:
            raise HTTPException(status_code=429, detail=str(exc) + _PUBLIC_TERMINAL_SAFETY_NOTICE) from exc
        schema = intake.load_schema(settings.knowledge_dir)
        intro = schema.ui.get("intro", "안녕하세요. 편한 만큼 이야기해 주세요.") if schema else "안녕하세요."
        question = schema.opening_question if schema else "어떤 도움이 필요하신가요?"
        session = chat._get_session(session_id)
        session.participant_id = linked_id or _new_participant_id()
        if schema is not None and schema.handoff_mode == "center":
            session.last_question_slot_id = "chief_complaint"
        session.consent_pack = settings.knowledge_dir
        consent.record_consent(session, privacy)
        delete_code = consent.issue_delete_code(session_id)
        return {"accepted": True, "session_token": session.session_token,
                "participant_id": session.participant_id,
                "participant_ticket": _sign_participant_id(session.participant_id),
                "delete_code": delete_code, "reply": intro + " " + question,
                "greeting": intro, "opening_question": question, "turn": 0, "limit_reached": False}


@app.post("/api/session/delete")
def post_session_delete(request: Request, payload: dict = Body(...)):
    session_id = payload.get("session_id")
    if cloud_store.enabled() and "delete_code" in payload:
        settings = Settings.from_env()
        ip = ratelimit.client_ip(request, settings.trust_proxy_hops)
        if not _failure_allowed(ip, _deletion_auth_failures):
            raise HTTPException(status_code=429, detail="삭제 인증 시도가 너무 많습니다. 잠시 후 다시 시도해 주세요.")
        session_id = consent.session_for_delete_code(payload["delete_code"])
    with cloud_store.session_scope(session_id):
        return _post_session_delete(request, payload)


def _post_session_delete(request: Request, payload: dict):
    settings = Settings.from_env()
    ip = ratelimit.client_ip(request, settings.trust_proxy_hops)
    with storage.data_lock():
        if not _failure_allowed(ip, _deletion_auth_failures):
            raise HTTPException(status_code=429, detail="삭제 인증 시도가 너무 많습니다. 잠시 후 다시 시도해 주세요.")
        if "delete_code" in payload:
            session_id = consent.session_for_delete_code(payload["delete_code"])
            via = "delete_code"
        else:
            session_id = payload.get("session_id")
            token = payload.get("session_token")
            if not (isinstance(session_id, str) and storage.valid_session_id(session_id)
                    and isinstance(token, str) and len(token) <= 128
                    and chat.owns_session(session_id, token)):
                session_id = None
            via = "session_token"
        if session_id is None:
            if cloud_store.enabled():
                cloud_store.auth_failure("deletion", ip, record=True)
            else:
                _deletion_auth_failures.setdefault(ip, []).append(datetime.now(timezone.utc).isoformat())
            raise HTTPException(status_code=401, detail="삭제 코드 또는 세션 인증이 올바르지 않습니다.")
        retention.delete_session(session_id, via)
        return {"deleted": True, "session_id": session_id, "reply": "내 기록을 지웠습니다."}


@app.get("/api/config")
def get_config():
    """스키마 프로브 + 스키마 소유 UI 문구. ui가 비면 프론트는 기본 문구를 쓴다."""
    settings = Settings.from_env()
    schema = intake.load_schema(settings.knowledge_dir)
    privacy = consent.load_privacy(settings.knowledge_dir, settings)
    config = {
        "mode": "intake" if schema is not None else "coaching",
        "intake_schema": schema is not None,
        "ui": schema.ui if schema is not None else {},
    }
    if portal_config.enabled():
        config["institution_link_required"] = True
    # Legacy packs keep their existing JSON contract, including exact-key clients.
    # Consent-specific fields belong to packs that explicitly opt in.
    if privacy is not None:
        config.update(consent_required=True, privacy=privacy.as_dict(),
                      opening_question=schema.opening_question if schema else None)
    if schema is not None and schema.handoff_mode is not None:
        config["slot_labels"] = {slot.id: slot.label for slot in schema.slots}
    return config


@app.get("/api/health")
def get_health():
    if cloud_store.enabled():
        cloud_store.get("health", "probe")
    settings = Settings.from_env()
    return {"status": "ok", "storage": "postgres" if cloud_store.enabled() else "local",
            "model_configured": bool(settings.anthropic_api_key) if settings.model.startswith("claude-") else settings.model == "fake"}


@app.get("/api/maintenance/retention")
def maintenance_retention(authorization: str | None = Header(default=None)):
    secret = os.getenv("CRON_SECRET", "")
    if len(secret) < 32 or not authorization or not secrets.compare_digest(authorization, "Bearer " + secret):
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    result = retention.purge_expired()
    return {key: result[key] for key in ("sessions", "turns")}


@app.get("/stats.html")
def get_stats_dashboard():
    """Issue an HttpOnly admin session only on the loopback-only dashboard."""
    settings = Settings.from_env()
    response = FileResponse(os.path.join(STATIC_DIR, "stats.html"))
    if settings.stats_api_token and len(settings.stats_api_token) >= MIN_STATS_TOKEN_LEN:
        response.set_cookie(
            key=_STATS_COOKIE_NAME,
            value=settings.stats_api_token,
            httponly=True,
            samesite="strict",
            secure=False,
            path="/",
        )
    return response


def _require_stats_auth(
    request: Request,
    stats_token: str | None,
    stats_session: str | None,
) -> str:
    settings = Settings.from_env()
    ip = ratelimit.client_ip(request, settings.trust_proxy_hops)
    if not _stats_failure_allowed(ip):
        raise HTTPException(status_code=429, detail="통계 API 인증 시도가 너무 많습니다.")
    if not settings.stats_api_token:
        raise HTTPException(status_code=503, detail="통계 API 토큰이 구성되지 않았습니다.")
    if len(settings.stats_api_token) < MIN_STATS_TOKEN_LEN:
        raise HTTPException(status_code=503, detail="통계 API 토큰이 너무 짧습니다.")
    supplied_token = stats_token or stats_session
    ok = False
    if supplied_token and isinstance(supplied_token, str) and len(supplied_token) <= 256:
        try:
            ok = secrets.compare_digest(
                supplied_token.encode("utf-8"), settings.stats_api_token.encode("utf-8")
            )
        except Exception:
            ok = False
    if not ok:
        _record_stats_failure(ip)
        raise HTTPException(status_code=401, detail="통계 API 인증이 필요합니다.")
    return supplied_token


def _record_access(request: Request, kind: str, token: str, **kwargs) -> None:
    settings = Settings.from_env()
    ip = ratelimit.client_ip(request, settings.trust_proxy_hops)
    try:
        access_log.record_access(kind, token, ip, **kwargs)
    except OSError as exc:
        logger.error("Access record could not be written (%s)", kind, exc_info=True)
        if kind != "stats":
            raise HTTPException(status_code=503, detail="열람·확인 기록을 저장하지 못했습니다.") from exc


@app.post("/api/admin/links")
def post_admin_link(
    request: Request,
    payload: dict = Body(...),
    stats_token: str | None = Header(default=None, alias="X-Stats-Token"),
    stats_session: str | None = Cookie(default=None, alias=_STATS_COOKIE_NAME),
):
    token = _require_stats_auth(request, stats_token, stats_session)
    management_id = payload.get("management_id")
    if not _valid_management_id(management_id):
        raise HTTPException(status_code=400, detail="관리번호는 영문·숫자로 시작하는 1~32자의 영문·숫자·하이픈이어야 하며 전화번호·주민번호는 사용할 수 없습니다.")
    ticket = _sign_participant_id(management_id)
    url = str(request.base_url) + "?" + urlencode({"management_id": management_id, "link_ticket": ticket})
    _record_access(request, "link_issue", token, management_id=management_id)
    return {"management_id": management_id, "url": url}


@app.get("/api/stats")
def get_stats(
    request: Request,
    participant_prefix: str | None = Query(default=None, max_length=64),
    session_prefix: str | None = Query(default=None, max_length=64),
    stats_token: str | None = Header(default=None, alias="X-Stats-Token"),
    stats_session: str | None = Cookie(default=None, alias=_STATS_COOKIE_NAME),
):
    """SQLite 적재 결과를 내담자 통계 대시보드용 JSON으로 반환한다."""
    token = _require_stats_auth(request, stats_token, stats_session)
    with storage.data_lock():
        stats.sync_today()
        result = stats.read_stats(participant_prefix=participant_prefix, session_prefix=session_prefix)
        _record_access(request, "stats", token,
                       filters={"participant_prefix": participant_prefix, "session_prefix": session_prefix})
        return result


@app.get("/api/stats/session")
def get_stats_session(
    request: Request,
    day: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"),
    session_id: str = Query(max_length=128),
    stats_token: str | None = Header(default=None, alias="X-Stats-Token"),
    stats_session: str | None = Cookie(default=None, alias=_STATS_COOKIE_NAME),
):
    """내부 상담자가 선택한 접수 세션의 대화 내역을 반환한다."""
    token = _require_stats_auth(request, stats_token, stats_session)
    if not storage.valid_session_id(session_id):
        raise HTTPException(status_code=400, detail="session_id 형식이 올바르지 않습니다.")
    with storage.data_lock():
        stats.sync_today()
        detail = stats.read_session_detail(day, session_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="접수 대화 내역을 찾지 못했습니다.")
        _record_access(request, "raw_view", token, session_id=session_id)
        return detail


@app.post("/api/review")
def post_review(
    request: Request,
    payload: dict = Body(...),
    stats_token: str | None = Header(default=None, alias="X-Stats-Token"),
    stats_session: str | None = Cookie(default=None, alias=_STATS_COOKIE_NAME),
):
    token = _require_stats_auth(request, stats_token, stats_session)
    try:
        day, session_id, action, note = review.validate_payload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    with storage.data_lock():
        stats.sync_today()
        if stats.read_session_detail(day, session_id) is None:
            raise HTTPException(status_code=404, detail="접수 기록을 찾지 못했습니다.")
        _record_access(request, "review", token, session_id=session_id)
        try:
            review.record_review(session_id, action, token, note)
        except OSError as exc:
            logger.error("Human confirmation could not be written", exc_info=True)
            raise HTTPException(status_code=503, detail="확인 기록을 저장하지 못했습니다.") from exc
    return {"review_status": action}


from app.portal import router as portal_router
app.include_router(portal_router)

if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
