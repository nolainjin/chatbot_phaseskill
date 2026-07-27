import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """TestClient 피크스처."""
    return TestClient(app)


def test_config_with_schema(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_DIR", "knowledge")
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {"mode": "intake", "intake_schema": True, "ui": {}}


def test_config_with_starter_pack_schema(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_DIR", "knowledge-alt")
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {"mode": "intake", "intake_schema": True, "ui": {}}


def test_config_without_schema_fixture(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_DIR", "tests/fixtures/knowledge-fallback")
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {"mode": "coaching", "intake_schema": False, "ui": {}}


def test_config_with_math_pack_exposes_coaching_mode(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_DIR", "knowledge-math")
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert data == {"mode": "coaching", "intake_schema": False, "ui": {}}


def test_config_never_advertises_voice(client, monkeypatch):
    """음성 모드는 제거됐다 — /api/config는 voice 키를 절대 내려주지 않는다."""
    monkeypatch.setenv("KNOWLEDGE_DIR", "knowledge")
    response = client.get("/api/config")
    assert response.status_code == 200
    assert "voice" not in response.json()


def test_missing_knowledge_dir_does_not_break_text_routes(client, monkeypatch, tmp_path):
    """지식 폴더가 없어도 정적 서빙과 /api/chat은 살아 있어야 한다."""
    monkeypatch.setenv("KNOWLEDGE_DIR", str(tmp_path / "missing-knowledge"))
    monkeypatch.setenv("MODEL", "fake")
    (tmp_path / "static" / "index.html").parent.mkdir()
    (tmp_path / "static" / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    root_response = client.get("/")
    chat_response = client.post(
        "/api/chat",
        json={"session_id": "knowledge-absent", "message": "텍스트로 시작할게요."},
    )

    assert root_response.status_code == 200
    assert chat_response.status_code == 200
    assert chat_response.json()["turn"] == 1
