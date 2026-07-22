import pytest
from fastapi.testclient import TestClient

from app import voice_api
from app.config import Settings
from app.main import app
from app.voice_contracts import (
    SynthesizedAudio,
    TranscriptionProviderOutput,
    UnavailableSynthesisProvider,
    UnavailableTranscriptionProvider,
)


class NoCallVoiceProvider:
    def start(self) -> None:
        raise AssertionError("config probe must not start providers")

    def transcribe(
        self, audio: bytes, content_type: str | None
    ) -> TranscriptionProviderOutput:
        raise AssertionError("config probe must not transcribe")

    def predict_duration_ms(self, text: str) -> int:
        raise AssertionError("config probe must not inspect provider health")

    def synthesize(self, text: str) -> SynthesizedAudio:
        raise AssertionError("config probe must not synthesize")


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


def test_config_does_not_advertise_voice_when_providers_are_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("KNOWLEDGE_DIR", "tests/fixtures/knowledge-fallback")
    monkeypatch.setenv("VOICE_ENABLED", "true")
    monkeypatch.setattr(
        voice_api, "transcription_provider", UnavailableTranscriptionProvider()
    )
    monkeypatch.setattr(voice_api, "synthesis_provider", UnavailableSynthesisProvider())

    # When
    response = client.get("/api/config")

    # Then
    assert response.status_code == 200
    assert response.json() == {"mode": "coaching", "intake_schema": False, "ui": {}}


def test_config_reports_exact_default_profiles_without_provider_calls(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    provider = NoCallVoiceProvider()
    monkeypatch.setenv("KNOWLEDGE_DIR", "tests/fixtures/knowledge-fallback")
    monkeypatch.setenv("VOICE_ENABLED", "true")
    monkeypatch.delenv("VOICE_STT_PROVIDER", raising=False)
    monkeypatch.delenv("VOICE_TTS_VOICE", raising=False)
    monkeypatch.setattr(voice_api, "transcription_provider", provider)
    monkeypatch.setattr(voice_api, "synthesis_provider", provider)

    # When
    response = client.get("/api/config")

    # Then
    assert response.status_code == 200
    assert response.json()["voice"] == {
        "enabled": True,
        "local_only": True,
        "stt": "qwen3-asr-0.6b-8bit",
        "tts": "macos-say:Yuna",
        "min_recording_ms": 800,
        "max_recording_ms": 60000,
        "silence_auto_stop": True,
    }


def test_config_reports_exact_runtime_profile_overrides(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    provider = NoCallVoiceProvider()
    monkeypatch.setenv("KNOWLEDGE_DIR", "tests/fixtures/knowledge-fallback")
    monkeypatch.setenv("VOICE_ENABLED", "true")
    monkeypatch.setenv("VOICE_STT_PROVIDER", "whisper.cpp")
    monkeypatch.setenv("VOICE_TTS_VOICE", "Kyoko")
    monkeypatch.setattr(voice_api, "transcription_provider", provider)
    monkeypatch.setattr(voice_api, "synthesis_provider", provider)

    # When
    response = client.get("/api/config")

    # Then
    assert response.status_code == 200
    assert response.json()["voice"]["stt"] == "whisper.cpp"
    assert response.json()["voice"]["tts"] == "macos-say:Kyoko"


@pytest.mark.parametrize("env_name", ["VOICE_STT_PROVIDER", "VOICE_TTS_VOICE"])
def test_config_fails_closed_when_voice_metadata_is_invalid(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, env_name: str
) -> None:
    # Given
    provider = NoCallVoiceProvider()
    monkeypatch.setenv("KNOWLEDGE_DIR", "tests/fixtures/knowledge-fallback")
    monkeypatch.setenv("VOICE_ENABLED", "true")
    monkeypatch.setenv(env_name, "   ")
    monkeypatch.setattr(voice_api, "transcription_provider", provider)
    monkeypatch.setattr(voice_api, "synthesis_provider", provider)

    # When
    response = client.get("/api/config")

    # Then
    assert response.status_code == 200
    assert response.json() == {"mode": "coaching", "intake_schema": False, "ui": {}}


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
