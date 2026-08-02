"""FastAPI application with a default-dark public boundary."""

import ipaddress
import os
import secrets

from fastapi import Body, Cookie, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app import chat, intake, ratelimit, stats, storage
from app.config import Settings

MAX_MESSAGE_LEN = 2000
MIN_STATS_TOKEN_LEN = 16
STATIC_DIR = "static"
_LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_PRIVATE_TEST_HOST = "testserver"
_PRIVATE_LOCAL_UI_ENV = "PRIVATE_LOCAL_UI"
_PUBLIC_CHAT_UI_ENV = "PUBLIC_CHAT_UI"

_STATS_COOKIE_NAME = "lmwiki_stats_session"
_ADMIN_PATHS = frozenset(
    {"/stats.html", "/stats.js", "/csv.js", "/api/stats", "/api/stats/session"}
)
# Every request is dark unless explicit private mode proves both a loopback
# Host header and a loopback transport peer.
_DARK_RESPONSE_BODY = b'{"detail":"public service disabled"}'

app = FastAPI()
_rate_limiter = ratelimit.RateLimiter()


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


@app.middleware("http")
async def default_dark_boundary(request: Request, call_next):
    """Default dark; permit private loopback or an explicitly enabled public chat surface."""
    hostname = (request.url.hostname or "").lower()
    peer = request.client.host if request.client else ""
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
    return await call_next(request)


@app.post("/api/chat")
def post_chat(request: Request, payload: dict = Body(...)):
    session_id = payload.get("session_id")
    message = payload.get("message")
    participant_id = payload.get("participant_id")
    session_token = payload.get("session_token")

    # session_id는 파일명이 되므로 API 경계에서 화이트리스트를 강제한다 —
    # 통과 못 하면 400. 아래 storage 층 검증까지 내려가 500으로 새는 걸 막는다.
    if not isinstance(session_id, str) or not storage.valid_session_id(session_id):
        raise HTTPException(status_code=400, detail="session_id 형식이 올바르지 않습니다.")
    if not isinstance(message, str) or not message.strip():
        raise HTTPException(status_code=400, detail="message는 비어있지 않은 문자열이어야 합니다.")
    if len(message) > MAX_MESSAGE_LEN:
        raise HTTPException(status_code=400, detail=f"message는 {MAX_MESSAGE_LEN}자를 넘을 수 없습니다.")
    if participant_id is not None and (
        not isinstance(participant_id, str) or not storage.valid_participant_id(participant_id)
    ):
        raise HTTPException(status_code=400, detail="participant_id 형식이 올바르지 않습니다.")
    if session_token is not None and (
        not isinstance(session_token, str) or len(session_token) > 128
    ):
        raise HTTPException(status_code=400, detail="session_token 형식이 올바르지 않습니다.")

    session_was_known = chat.has_session(session_id)
    if session_was_known:
        if not chat.owns_session(session_id, session_token):
            raise HTTPException(status_code=401, detail="세션 인증이 필요합니다.")
    elif storage.conversation_exists(session_id):
        raise HTTPException(status_code=401, detail="만료된 세션입니다. 새 세션으로 시작해 주세요.")

    settings = Settings.from_env()
    ip = ratelimit.client_ip(request, settings.trust_proxy_hops)
    try:
        _rate_limiter.check(ip, session_id, daily_cap=settings.daily_request_cap)
    except ratelimit.RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    result = chat.handle_message(session_id, message, participant_id=participant_id)
    if not session_was_known:
        result["session_token"] = chat.session_token(session_id)
    return result


@app.get("/api/config")
def get_config():
    """스키마 프로브 + 스키마 소유 UI 문구. ui가 비면 프론트는 기본 문구를 쓴다."""
    settings = Settings.from_env()
    schema = intake.load_schema(settings.knowledge_dir)
    return {
        "mode": "intake" if schema is not None else "coaching",
        "intake_schema": schema is not None,
        "ui": schema.ui if schema is not None else {},
    }


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
    stats_token: str | None,
    stats_session: str | None,
) -> None:
    settings = Settings.from_env()
    if not settings.stats_api_token:
        raise HTTPException(status_code=503, detail="통계 API 토큰이 구성되지 않았습니다.")
    if len(settings.stats_api_token) < MIN_STATS_TOKEN_LEN:
        raise HTTPException(status_code=503, detail="통계 API 토큰이 너무 짧습니다.")
    supplied_token = stats_token or stats_session
    if not supplied_token or not secrets.compare_digest(
        supplied_token, settings.stats_api_token
    ):
        raise HTTPException(status_code=401, detail="통계 API 인증이 필요합니다.")


@app.get("/api/stats")
def get_stats(
    participant_prefix: str | None = Query(default=None, max_length=64),
    session_prefix: str | None = Query(default=None, max_length=64),
    stats_token: str | None = Header(default=None, alias="X-Stats-Token"),
    stats_session: str | None = Cookie(default=None, alias=_STATS_COOKIE_NAME),
):
    """SQLite 적재 결과를 내담자 통계 대시보드용 JSON으로 반환한다."""
    _require_stats_auth(stats_token, stats_session)
    stats.sync_today()
    return stats.read_stats(
        participant_prefix=participant_prefix,
        session_prefix=session_prefix,
    )


@app.get("/api/stats/session")
def get_stats_session(
    day: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"),
    session_id: str = Query(max_length=128),
    stats_token: str | None = Header(default=None, alias="X-Stats-Token"),
    stats_session: str | None = Cookie(default=None, alias=_STATS_COOKIE_NAME),
):
    """내부 상담자가 선택한 접수 세션의 대화 내역을 반환한다."""
    _require_stats_auth(stats_token, stats_session)
    if not storage.valid_session_id(session_id):
        raise HTTPException(status_code=400, detail="session_id 형식이 올바르지 않습니다.")
    stats.sync_today()
    detail = stats.read_session_detail(day, session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="접수 대화 내역을 찾지 못했습니다.")
    return detail


if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
