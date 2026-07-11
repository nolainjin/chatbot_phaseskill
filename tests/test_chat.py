from pathlib import Path

from fastapi.testclient import TestClient

from app import chat
from app.config import Settings
from app.main import app

REPO_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = str(REPO_ROOT / "knowledge")

FAKE_SETTINGS = Settings(
    anthropic_api_key="",
    knowledge_dir=KNOWLEDGE_DIR,
    model="fake",
    trust_proxy_hops=0,
    daily_request_cap=500,
)

client = TestClient(app)


def test_handle_message_returns_reply_citing_searched_docs():
    result = chat.handle_message("session-basic", "라포 형성 방법이 궁금해요", FAKE_SETTINGS)
    assert result["limit_reached"] is False
    assert result["turn"] == 1
    assert "라포" in result["reply"]


def test_handle_message_with_no_matching_docs_still_replies():
    result = chat.handle_message("session-no-match", "zzz qqq 없는 단어", FAKE_SETTINGS)
    assert result["limit_reached"] is False
    assert "찾지 못했습니다" in result["reply"]


def test_11th_message_is_rejected():
    session_id = "session-cap"
    for i in range(chat.MAX_TURNS):
        result = chat.handle_message(session_id, f"질문 {i}", FAKE_SETTINGS)
        assert result["limit_reached"] is False
        assert result["turn"] == i + 1

    eleventh = chat.handle_message(session_id, "열한번째 질문", FAKE_SETTINGS)
    assert eleventh["limit_reached"] is True
    assert eleventh["turn"] == chat.MAX_TURNS


def test_api_chat_endpoint_happy_path(monkeypatch):
    monkeypatch.setenv("MODEL", "fake")
    monkeypatch.setenv("KNOWLEDGE_DIR", KNOWLEDGE_DIR)
    response = client.post(
        "/api/chat", json={"session_id": "api-basic", "message": "라포 형성 방법이 궁금해요"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["turn"] == 1
    assert body["limit_reached"] is False
    assert "reply" in body


def test_api_chat_rejects_empty_message(monkeypatch):
    monkeypatch.setenv("MODEL", "fake")
    response = client.post("/api/chat", json={"session_id": "api-empty", "message": ""})
    assert response.status_code == 400


def test_api_chat_rejects_non_string_message(monkeypatch):
    monkeypatch.setenv("MODEL", "fake")
    response = client.post("/api/chat", json={"session_id": "api-bad-type", "message": 12345})
    assert response.status_code == 400


def test_api_chat_rejects_message_over_2000_chars(monkeypatch):
    monkeypatch.setenv("MODEL", "fake")
    response = client.post(
        "/api/chat", json={"session_id": "api-too-long", "message": "가" * 2001}
    )
    assert response.status_code == 400


def test_api_chat_rejects_missing_session_id(monkeypatch):
    monkeypatch.setenv("MODEL", "fake")
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 400
