"""Phase 7 보안 경계 테스트 — 입력 검증이 신뢰 경계에서 실제로 동작하는지 고정.

docs/security-review.md의 점검 항목 중 코드로 검증 가능한 것(입력 검증·
session_id 화이트리스트)을 회귀 방지용으로 못 박는다.
"""

from fastapi.testclient import TestClient

from app import storage
from app import chat
from app.main import MAX_MESSAGE_LEN, app

client = TestClient(app, raise_server_exceptions=False)


# --- 입력 길이 상한 -------------------------------------------------------------


def test_over_length_message_is_rejected(monkeypatch):
    monkeypatch.setenv("MODEL", "fake")
    response = client.post(
        "/api/chat",
        json={"session_id": "sec-len", "message": "가" * (MAX_MESSAGE_LEN + 1)},
    )
    assert response.status_code == 400


def test_message_at_limit_is_accepted(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL", "fake")
    monkeypatch.chdir(tmp_path)
    response = client.post(
        "/api/chat",
        json={"session_id": "sec-len-ok", "message": "가" * MAX_MESSAGE_LEN},
    )
    assert response.status_code == 200


def test_oversized_model_reply_is_not_persisted(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MODEL", "codex-cli")
    oversized = "응답" * (chat.MAX_REPLY_CHARS // 2 + 1)
    monkeypatch.setattr(chat.llm, "ask", lambda **_kwargs: oversized)

    result = chat.handle_message("sec-output-bound", "안녕하세요")

    assert len(result["reply"]) <= chat.MAX_REPLY_CHARS
    assert result["reply"] != oversized
    assistant_entries = [
        entry for entry in chat._sessions["sec-output-bound"].history if entry["role"] == "assistant"
    ]
    assert assistant_entries[-1]["content"] == result["reply"]


# --- 비 JSON content-type 거부 --------------------------------------------------


def test_form_urlencoded_content_type_is_rejected():
    response = client.post(
        "/api/chat",
        content="session_id=x&message=hi",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 422


def test_text_plain_body_is_rejected():
    # 본문이 JSON처럼 보여도 content-type이 application/json이 아니면 거부한다.
    response = client.post(
        "/api/chat",
        content='{"session_id":"x","message":"hi"}',
        headers={"content-type": "text/plain"},
    )
    assert response.status_code == 422


# --- session_id 화이트리스트 (경로 구분자·과길이 → 400, 500 아님) ----------------


def test_session_id_with_path_separator_is_rejected_with_400():
    response = client.post(
        "/api/chat", json={"session_id": "../../etc/passwd", "message": "hi"}
    )
    assert response.status_code == 400


def test_over_length_session_id_is_rejected_with_400():
    response = client.post(
        "/api/chat", json={"session_id": "a" * 200, "message": "hi"}
    )
    assert response.status_code == 400


def test_valid_session_id_helper_matches_whitelist():
    assert storage.valid_session_id("Abc-1_2.3")
    assert not storage.valid_session_id("a/b")
    assert not storage.valid_session_id("")
    assert not storage.valid_session_id("a" * 129)


def test_api_chat_requires_session_token_after_session_creation(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL", "fake")
    monkeypatch.chdir(tmp_path)
    session_id = "sec-token-boundary"

    created = client.post("/api/chat", json={"session_id": session_id, "message": "첫 발화"})
    assert created.status_code == 200
    session_token = created.json()["session_token"]

    stolen = client.post("/api/chat", json={"session_id": session_id, "message": "탈취 발화"})
    assert stolen.status_code == 401

    owned = client.post(
        "/api/chat",
        json={"session_id": session_id, "session_token": session_token, "message": "정상 발화"},
    )
    assert owned.status_code == 200
