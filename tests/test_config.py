import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app


@pytest.fixture
def client():
    """TestClient 피크스처."""
    return TestClient(app)


def test_config_with_schema(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_DIR", "knowledge")
    monkeypatch.setenv("VOICE_ENABLED", "false")
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {"mode": "intake", "intake_schema": True, "ui": {}}


def test_config_with_starter_pack_schema(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_DIR", "knowledge-alt")
    monkeypatch.setenv("VOICE_ENABLED", "false")
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {"mode": "intake", "intake_schema": True, "ui": {}}


def test_config_without_schema_fixture(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_DIR", "tests/fixtures/knowledge-fallback")
    monkeypatch.setenv("VOICE_ENABLED", "false")
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {"mode": "coaching", "intake_schema": False, "ui": {}}


def test_config_with_math_pack_exposes_coaching_mode(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_DIR", "knowledge-math")
    monkeypatch.setenv("VOICE_ENABLED", "false")
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert data == {"mode": "coaching", "intake_schema": False, "ui": {}}


def test_settings_voice_gate_defaults_disabled(monkeypatch):
    monkeypatch.delenv("VOICE_ENABLED", raising=False)

    settings = Settings.from_env()

    assert settings.voice_enabled is False


def test_config_enabled_exposes_local_voice_gate_when_provider_is_absent(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_DIR", "tests/fixtures/knowledge-fallback")
    monkeypatch.setenv("VOICE_ENABLED", "true")
    monkeypatch.setenv("PROVIDER_BIN", "/nonexistent")

    response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "coaching",
        "intake_schema": False,
        "ui": {},
        "voice": {
            "enabled": True,
            "local_only": True,
            "stt": "qwen3-asr-0.6b-8bit",
            "tts": "supertonic-3",
            "min_recording_ms": 800,
            "max_recording_ms": 60000,
            "silence_auto_stop": False,
        },
    }


def test_missing_voice_provider_does_not_break_text_routes(client, monkeypatch, tmp_path):
    monkeypatch.setenv("KNOWLEDGE_DIR", str(tmp_path / "missing-knowledge"))
    monkeypatch.setenv("MODEL", "fake")
    monkeypatch.setenv("VOICE_ENABLED", "true")
    monkeypatch.setenv("PROVIDER_BIN", "/nonexistent")
    (tmp_path / "static" / "index.html").parent.mkdir()
    (tmp_path / "static" / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    root_response = client.get("/")
    chat_response = client.post(
        "/api/chat",
        json={"session_id": "voice-provider-absent", "message": "텍스트로 시작할게요."},
    )

    assert root_response.status_code == 200
    assert chat_response.status_code == 200
    assert chat_response.json()["turn"] == 1


def test_invalid_voice_enabled_value_fails_closed(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_DIR", "tests/fixtures/knowledge-fallback")
    monkeypatch.setenv("VOICE_ENABLED", "definitely-not-a-boolean")

    response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json() == {"mode": "coaching", "intake_schema": False, "ui": {}}
