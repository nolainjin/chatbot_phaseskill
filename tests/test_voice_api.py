import io
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import chat, voice_api
from app.main import app
from app.voice_contracts import (
    SynthesizedAudio,
    TranscriptionProviderOutput,
    VoiceLocalOnlyViolation,
    VoiceProviderTimeout,
    VoiceProviderUnavailable,
)


client = TestClient(app, raise_server_exceptions=False)


def make_wav(duration_ms: int, sample_rate: int = 16_000) -> bytes:
    frames = round(sample_rate * duration_ms / 1000)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\0\0" * frames)
    return buffer.getvalue()


class FakeTranscriber:
    def __init__(
        self,
        result: TranscriptionProviderOutput | None = None,
        error: Exception | None = None,
    ):
        self.result = result or TranscriptionProviderOutput(
            text="첫 음성 전사", language="ko", model="fake-stt", provider="fake-local"
        )
        self.error = error

    def transcribe(self, audio: bytes, content_type: str | None) -> TranscriptionProviderOutput:
        if self.error is not None:
            raise self.error
        return self.result


class FakeSynthesizer:
    def __init__(self, predicted_duration_ms: int = 1000, error: Exception | None = None):
        self.predicted_duration_ms = predicted_duration_ms
        self.error = error

    def predict_duration_ms(self, text: str) -> int:
        return self.predicted_duration_ms

    def synthesize(self, text: str) -> SynthesizedAudio:
        if self.error is not None:
            raise self.error
        return SynthesizedAudio(
            content=b"RIFFfake-wav",
            media_type="audio/wav",
            duration_ms=self.predicted_duration_ms,
            sample_rate=16_000,
            channels=1,
        )


class MalformedTranscriber:
    def transcribe(self, audio: bytes, content_type: str | None) -> str:
        return "not a provider result"


@pytest.fixture
def fake_providers(monkeypatch):
    monkeypatch.setattr(voice_api, "transcription_provider", FakeTranscriber())
    monkeypatch.setattr(voice_api, "synthesis_provider", FakeSynthesizer())


def post_transcribe(session_id: str, audio: bytes, token: str | None = None):
    data = {"session_id": session_id}
    if token is not None:
        data["session_token"] = token
    return client.post(
        "/api/voice/transcribe",
        data=data,
        files={"audio": ("sample.wav", audio, "audio/wav")},
    )


def test_transcribe_disabled_returns_stable_error_code(monkeypatch):
    monkeypatch.setenv("VOICE_ENABLED", "false")

    response = post_transcribe("voice-disabled", make_wav(1000))

    assert response.status_code == 503
    assert response.json()["error_code"] == "voice_disabled"


def test_synthesize_disabled_returns_stable_error_code(monkeypatch):
    monkeypatch.setenv("VOICE_ENABLED", "false")

    response = client.post("/api/voice/synthesize", json={"text": "안녕하세요"})

    assert response.status_code == 503
    assert response.json()["error_code"] == "voice_disabled"


@pytest.mark.parametrize(
    ("field", "value"),
    [("session_id", "../escape"), ("participant_id", "../person")],
)
def test_transcribe_rejects_malformed_ids(monkeypatch, field, value):
    monkeypatch.setenv("VOICE_ENABLED", "true")
    data = {"session_id": "voice-invalid"}
    data[field] = value

    response = client.post(
        "/api/voice/transcribe",
        data=data,
        files={"audio": ("sample.wav", make_wav(1000), "audio/wav")},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_request"


def test_first_turn_transcribe_is_ephemeral(monkeypatch, tmp_path, fake_providers):
    monkeypatch.setenv("VOICE_ENABLED", "true")
    monkeypatch.chdir(tmp_path)
    session_id = "voice-ephemeral"
    chat._sessions.pop(session_id, None)
    conversation_dir = Path("data/conversations")

    response = post_transcribe(session_id, make_wav(1000))

    assert response.status_code == 200
    assert response.json()["text"] == "첫 음성 전사"
    assert response.json()["duration_ms"] == 1000
    assert not chat.has_session(session_id)
    assert not conversation_dir.exists()
    assert not list(tmp_path.rglob("*.wav"))


def test_known_session_transcribe_requires_token(monkeypatch, tmp_path, fake_providers):
    monkeypatch.setenv("MODEL", "fake")
    monkeypatch.setenv("VOICE_ENABLED", "true")
    monkeypatch.chdir(tmp_path)
    session_id = "voice-known"
    created = client.post("/api/chat", json={"session_id": session_id, "message": "첫 발화"})
    assert created.status_code == 200

    response = post_transcribe(session_id, make_wav(1000))

    assert response.status_code == 401
    assert response.json()["error_code"] == "session_auth_required"


def test_transcribe_rejects_empty_audio(monkeypatch, fake_providers):
    monkeypatch.setenv("VOICE_ENABLED", "true")

    response = post_transcribe("voice-empty", b"")

    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_audio"


def test_transcribe_rejects_malformed_provider_output(monkeypatch, fake_providers):
    monkeypatch.setenv("VOICE_ENABLED", "true")
    monkeypatch.setattr(voice_api, "transcription_provider", MalformedTranscriber())

    response = post_transcribe("voice-bad-provider", make_wav(1000))

    assert response.status_code == 503
    assert response.json()["error_code"] == "provider_unavailable"


def test_transcribe_rejects_oversized_audio(monkeypatch, fake_providers):
    monkeypatch.setenv("VOICE_ENABLED", "true")

    response = post_transcribe("voice-large", b"x" * (10 * 1024 * 1024 + 1))

    assert response.status_code == 413
    assert response.json()["error_code"] == "audio_too_large"


@pytest.mark.parametrize(
    ("duration_ms", "code"),
    [(799, "audio_too_short"), (60_001, "audio_too_long")],
)
def test_transcribe_rejects_decoded_duration_outside_limits(
    monkeypatch, fake_providers, duration_ms, code
):
    monkeypatch.setenv("VOICE_ENABLED", "true")

    response = post_transcribe(f"voice-{code}", make_wav(duration_ms))

    assert response.status_code == 400
    assert response.json()["error_code"] == code


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (VoiceProviderUnavailable(), "provider_unavailable"),
        (VoiceProviderTimeout(), "provider_timeout"),
        (VoiceLocalOnlyViolation(), "local_only_violation"),
    ],
)
def test_transcribe_maps_provider_failures(monkeypatch, fake_providers, error, code):
    monkeypatch.setenv("VOICE_ENABLED", "true")
    fake = FakeTranscriber(error=error)
    monkeypatch.setattr(voice_api, "transcription_provider", fake)

    response = post_transcribe(f"voice-{code}", make_wav(1000))

    assert response.status_code == 503
    assert response.json()["error_code"] == code


@pytest.mark.parametrize("text", ["", "   ", "가" * 1201])
def test_synthesize_rejects_text_outside_limits(monkeypatch, fake_providers, text):
    monkeypatch.setenv("VOICE_ENABLED", "true")

    response = client.post("/api/voice/synthesize", json={"text": text})

    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_text"


def test_synthesize_rejects_predicted_output_over_60_seconds(monkeypatch, fake_providers):
    monkeypatch.setenv("VOICE_ENABLED", "true")
    monkeypatch.setattr(
        voice_api, "synthesis_provider", FakeSynthesizer(predicted_duration_ms=60_001)
    )

    response = client.post("/api/voice/synthesize", json={"text": "긴 응답"})

    assert response.status_code == 400
    assert response.json()["error_code"] == "audio_too_long"


def test_known_session_synthesize_requires_token(monkeypatch, tmp_path, fake_providers):
    monkeypatch.setenv("MODEL", "fake")
    monkeypatch.setenv("VOICE_ENABLED", "true")
    monkeypatch.chdir(tmp_path)
    session_id = "voice-tts-known"
    created = client.post("/api/chat", json={"session_id": session_id, "message": "첫 발화"})
    assert created.status_code == 200

    response = client.post(
        "/api/voice/synthesize", json={"session_id": session_id, "text": "응답 듣기"}
    )

    assert response.status_code == 401
    assert response.json()["error_code"] == "session_auth_required"


def test_synthesize_failure_preserves_existing_chat_response(monkeypatch, tmp_path, fake_providers):
    monkeypatch.setenv("MODEL", "fake")
    monkeypatch.setenv("VOICE_ENABLED", "true")
    monkeypatch.chdir(tmp_path)
    session_id = "voice-tts-failure"
    created = client.post("/api/chat", json={"session_id": session_id, "message": "첫 발화"})
    token = created.json()["session_token"]
    before_turns = chat._sessions[session_id].turns
    monkeypatch.setattr(
        voice_api, "synthesis_provider", FakeSynthesizer(error=VoiceProviderUnavailable())
    )

    response = client.post(
        "/api/voice/synthesize",
        json={"session_id": session_id, "session_token": token, "text": "응답 듣기"},
    )

    assert response.status_code == 503
    assert response.json()["error_code"] == "provider_unavailable"
    assert chat._sessions[session_id].turns == before_turns
    assert chat._sessions[session_id].history[-1]["role"] == "assistant"


def test_synthesize_returns_one_shot_audio_without_cache(monkeypatch, fake_providers):
    monkeypatch.setenv("VOICE_ENABLED", "true")

    response = client.post("/api/voice/synthesize", json={"text": "응답 듣기"})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"RIFFfake-wav"
