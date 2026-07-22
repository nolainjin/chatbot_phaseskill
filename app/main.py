"""FastAPI 앱: POST /api/chat + static 파일 서빙."""

import os
import secrets

from fastapi import Body, FastAPI, Header, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles

from app import chat, intake, ratelimit, stats, storage
from app.config import (
    VOICE_MAX_RECORDING_MS,
    VOICE_MIN_RECORDING_MS,
    VOICE_SILENCE_AUTO_STOP,
    Settings,
)
from app.voice_api import providers_configured, router as voice_router

MAX_MESSAGE_LEN = 2000
STATIC_DIR = "static"

app = FastAPI()
_rate_limiter = ratelimit.RateLimiter()
app.include_router(voice_router)


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
    config = {
        "mode": "intake" if schema is not None else "coaching",
        "intake_schema": schema is not None,
        "ui": schema.ui if schema is not None else {},
    }
    if (
        settings.voice_enabled
        and settings.voice_stt_model is not None
        and settings.voice_tts_model is not None
        and providers_configured()
    ):
        config["voice"] = {
            "enabled": True,
            "local_only": True,
            "stt": settings.voice_stt_model,
            "tts": settings.voice_tts_model,
            "min_recording_ms": VOICE_MIN_RECORDING_MS,
            "max_recording_ms": VOICE_MAX_RECORDING_MS,
            "silence_auto_stop": VOICE_SILENCE_AUTO_STOP,
        }
    return config


@app.get("/api/stats")
def get_stats(
    participant_prefix: str | None = Query(default=None, max_length=64),
    session_prefix: str | None = Query(default=None, max_length=64),
    stats_token: str | None = Header(default=None, alias="X-Stats-Token"),
):
    """SQLite 적재 결과를 내담자 통계 대시보드용 JSON으로 반환한다."""
    settings = Settings.from_env()
    if not settings.stats_api_token:
        raise HTTPException(status_code=503, detail="통계 API 토큰이 구성되지 않았습니다.")
    if not stats_token or not secrets.compare_digest(stats_token, settings.stats_api_token):
        raise HTTPException(status_code=401, detail="통계 API 인증이 필요합니다.")
    return stats.read_stats(
        participant_prefix=participant_prefix,
        session_prefix=session_prefix,
    )


# static/은 Phase 5가 채운다 — 아직 없을 수 있으니 존재할 때만 마운트해서
# 이 phase 시점에도 앱이 정상 부팅되게 한다. html=True로 "/" 요청 시
# static/index.html을 서빙한다.
if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
