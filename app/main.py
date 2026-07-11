"""FastAPI 앱: POST /api/chat + static 파일 서빙."""

import os

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles

from app import chat, ratelimit
from app.config import Settings

MAX_MESSAGE_LEN = 2000
STATIC_DIR = "static"

app = FastAPI()
_rate_limiter = ratelimit.RateLimiter()


@app.post("/api/chat")
def post_chat(request: Request, payload: dict = Body(...)):
    session_id = payload.get("session_id")
    message = payload.get("message")

    if not isinstance(session_id, str) or not session_id:
        raise HTTPException(status_code=400, detail="session_id는 비어있지 않은 문자열이어야 합니다.")
    if not isinstance(message, str) or not message.strip():
        raise HTTPException(status_code=400, detail="message는 비어있지 않은 문자열이어야 합니다.")
    if len(message) > MAX_MESSAGE_LEN:
        raise HTTPException(status_code=400, detail=f"message는 {MAX_MESSAGE_LEN}자를 넘을 수 없습니다.")

    settings = Settings.from_env()
    ip = ratelimit.client_ip(request, settings.trust_proxy_hops)
    try:
        _rate_limiter.check(ip, session_id, daily_cap=settings.daily_request_cap)
    except ratelimit.RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    return chat.handle_message(session_id, message)


# static/은 Phase 5가 채운다 — 아직 없을 수 있으니 존재할 때만 마운트해서
# 이 phase 시점에도 앱이 정상 부팅되게 한다. html=True로 "/" 요청 시
# static/index.html을 서빙한다.
if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
