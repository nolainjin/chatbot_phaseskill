import io
import math
import struct
import subprocess
import sys
import wave
from pathlib import Path

import pytest
import sniffio
from fastapi.testclient import TestClient

from app import chat, ratelimit, voice_api
import app.main as main
from app.main import app
from app.voice_contracts import (
    MAX_AUDIO_BYTES,
    SynthesizedAudio,
    TranscriptionProviderOutput,
    VoiceLocalOnlyViolation,
    VoiceProviderTimeout,
    VoiceProviderUnavailable,
    decode_wav_duration_ms,
)
from app.voice_provider import SidecarVoiceProvider
from voice_runtime.sidecar import SidecarConfig, SidecarManager


client = TestClient(app, raise_server_exceptions=False)
MULTIPART_OVERHEAD_BYTES = 64 * 1024


def make_wav(duration_ms: int, sample_rate: int = 16_000) -> bytes:
    frames = round(sample_rate * duration_ms / 1000)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\0\0" * frames)
    return buffer.getvalue()


def make_non_silent_wav(duration_ms: int, sample_rate: int = 16_000) -> bytes:
    frames = round(sample_rate * duration_ms / 1000)
    samples = b"".join(
        struct.pack("<h", round(8_000 * math.sin(2 * math.pi * 440 * index / sample_rate)))
        for index in range(frames)
    )
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(samples)
    return buffer.getvalue()


def transcode_browser_audio(wav: bytes, media_type: str) -> bytes:
    output_args = {
        "audio/webm": ["-c:a", "libopus", "-f", "webm"],
        "audio/mp4": [
            "-c:a",
            "aac",
            "-movflags",
            "frag_keyframe+empty_moov",
            "-f",
            "mp4",
        ],
    }[media_type]
    completed = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "wav",
            "-i",
            "pipe:0",
            "-vn",
            *output_args,
            "pipe:1",
        ],
        input=wav,
        check=True,
        capture_output=True,
    )
    return completed.stdout


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
        self.received_audio: bytes | None = None
        self.received_content_type: str | None = None
        self.ran_in_async_context: bool | None = None

    def transcribe(self, audio: bytes, content_type: str | None) -> TranscriptionProviderOutput:
        self.received_audio = audio
        self.received_content_type = content_type
        try:
            sniffio.current_async_library()
        except sniffio.AsyncLibraryNotFoundError:
            self.ran_in_async_context = False
        else:
            self.ran_in_async_context = True
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


def post_transcribe(
    session_id: str,
    audio: bytes,
    token: str | None = None,
    *,
    media_type: str = "audio/wav",
    test_client: TestClient = client,
):
    data = {"session_id": session_id}
    if token is not None:
        data["session_token"] = token
    return test_client.post(
        "/api/voice/transcribe",
        data=data,
        files={"audio": ("sample.audio", audio, media_type)},
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
    "request_kwargs",
    [
        {"data": {}, "files": {"audio": ("sample.wav", make_wav(1000), "audio/wav")}},
        {"data": {"session_id": "voice-missing-audio"}, "files": {}},
    ],
)
def test_transcribe_requires_multipart_session_and_audio(monkeypatch, fake_providers, request_kwargs):
    monkeypatch.setenv("VOICE_ENABLED", "true")

    response = client.post("/api/voice/transcribe", **request_kwargs)

    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_request"


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


def test_known_session_transcribe_rejects_wrong_token(monkeypatch, tmp_path, fake_providers):
    monkeypatch.setenv("MODEL", "fake")
    monkeypatch.setenv("VOICE_ENABLED", "true")
    monkeypatch.chdir(tmp_path)
    session_id = "voice-known-wrong-token"
    created = client.post("/api/chat", json={"session_id": session_id, "message": "첫 발화"})
    assert created.status_code == 200

    response = post_transcribe(session_id, make_wav(1000), token="not-the-session-token")

    assert response.status_code == 401
    assert response.json()["error_code"] == "session_auth_required"


def test_voice_regression_does_not_weaken_chat_rate_limit_contract(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL", "fake")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        main,
        "_rate_limiter",
        ratelimit.RateLimiter(path=str(tmp_path / "rate-limit.json"), max_per_window=0),
    )

    response = client.post(
        "/api/chat", json={"session_id": "voice-rate-limited", "message": "첫 발화"}
    )

    assert response.status_code == 429
    assert not chat.has_session("voice-rate-limited")


def test_transcribe_rejects_empty_audio(monkeypatch, fake_providers):
    monkeypatch.setenv("VOICE_ENABLED", "true")

    response = post_transcribe("voice-empty", b"")

    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_audio"


@pytest.mark.parametrize("media_type", ["audio/webm", "audio/mp4"])
def test_transcribe_accepts_real_browser_mediarecorder_containers(
    monkeypatch, media_type
):
    monkeypatch.setenv("VOICE_ENABLED", "true")
    fake = FakeTranscriber()
    monkeypatch.setattr(voice_api, "transcription_provider", fake)
    browser_audio = transcode_browser_audio(make_non_silent_wav(1000), media_type)

    response = post_transcribe(
        f"voice-browser-{media_type.removeprefix('audio/')}",
        browser_audio,
        media_type=media_type,
    )

    assert response.status_code == 200
    assert fake.received_audio is not None
    assert fake.received_audio.startswith(b"RIFF")
    assert fake.received_content_type == "audio/wav"
    assert response.json()["duration_ms"] == decode_wav_duration_ms(fake.received_audio)


def test_transcribe_runs_blocking_provider_outside_async_context(monkeypatch):
    monkeypatch.setenv("VOICE_ENABLED", "true")
    fake = FakeTranscriber()
    monkeypatch.setattr(voice_api, "transcription_provider", fake)

    response = post_transcribe("voice-worker-thread", make_wav(1000))

    assert response.status_code == 200
    assert fake.ran_in_async_context is False


@pytest.mark.parametrize("path", ["/api/voice/transcribe", "/api/voice/synthesize"])
def test_voice_endpoints_reject_non_loopback_peer_even_with_forwarded_loopback(
    monkeypatch, fake_providers, path
):
    monkeypatch.setenv("VOICE_ENABLED", "true")
    remote_client = TestClient(
        app,
        raise_server_exceptions=False,
        client=("203.0.113.10", 50000),
    )
    headers = {"X-Forwarded-For": "127.0.0.1"}

    if path.endswith("transcribe"):
        response = remote_client.post(
            path,
            data={"session_id": "voice-remote"},
            files={"audio": ("sample.wav", make_wav(1000), "audio/wav")},
            headers=headers,
        )
    else:
        response = remote_client.post(path, json={"text": "원격 요청"}, headers=headers)

    assert response.status_code == 403
    assert response.json()["error_code"] == "local_only_violation"


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "testclient"])
def test_synthesize_permits_ipv4_ipv6_and_testclient_loopback(
    monkeypatch, fake_providers, host
):
    monkeypatch.setenv("VOICE_ENABLED", "true")
    local_client = TestClient(
        app,
        raise_server_exceptions=False,
        client=(host, 50000),
    )

    response = local_client.post(
        "/api/voice/synthesize",
        json={"text": "로컬 요청"},
        headers={"X-Forwarded-For": "203.0.113.10"},
    )

    assert response.status_code == 200


def test_transcribe_allows_exact_file_limit_with_multipart_overhead(monkeypatch):
    # Given an invalid audio file whose payload is exactly the per-file limit
    monkeypatch.setenv("VOICE_ENABLED", "true")

    # When the client wraps it in a multipart request body
    response = post_transcribe("voice-exact-file-limit", b"x" * MAX_AUDIO_BYTES)

    # Then multipart framing alone does not trigger the file-size error
    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_audio"


def test_transcribe_rejects_streamed_total_payload_over_multipart_limit(
    monkeypatch,
):
    # Given an exact-limit audio file plus enough text payload to exceed the total cap
    monkeypatch.setenv("VOICE_ENABLED", "true")
    boundary = b"voice-total-size-boundary"
    prefix = (
        b"--"
        + boundary
        + b'\r\nContent-Disposition: form-data; name="session_id"\r\n\r\n'
        + b"voice-streamed-total\r\n--"
        + boundary
        + b'\r\nContent-Disposition: form-data; name="audio"; filename="sample.wav"\r\n'
        + b"Content-Type: audio/wav\r\n\r\n"
    )
    padding = (
        b"\r\n--"
        + boundary
        + b'\r\nContent-Disposition: form-data; name="padding"\r\n\r\n'
        + b"p" * (70 * 1024)
        + b"\r\n--"
        + boundary
        + b"--\r\n"
    )

    # When the multipart body is streamed without a Content-Length header
    response = client.post(
        "/api/voice/transcribe",
        content=iter([prefix, b"x" * MAX_AUDIO_BYTES, padding]),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
    )

    # Then the parsed total-size fallback classifies the request as too large
    assert "content-length" not in response.request.headers
    assert response.status_code == 413
    assert response.json()["error_code"] == "audio_too_large"


def test_transcribe_rejects_declared_body_over_multipart_limit_before_parse(
    monkeypatch,
):
    # Given a malformed multipart body declared above the file-plus-overhead cap
    monkeypatch.setenv("VOICE_ENABLED", "true")

    # When the endpoint receives the request
    response = client.post(
        "/api/voice/transcribe",
        content=b"this is intentionally not a parsed multipart body",
        headers={
            "Content-Type": "multipart/form-data; boundary=voice-boundary",
            "Content-Length": str(
                MAX_AUDIO_BYTES + MULTIPART_OVERHEAD_BYTES + 1
            ),
        },
    )

    # Then it rejects from Content-Length without invoking multipart parsing
    assert response.status_code == 413
    assert response.json()["error_code"] == "audio_too_large"


def test_transcribe_keeps_post_read_cap_without_content_length(monkeypatch):
    monkeypatch.setenv("VOICE_ENABLED", "true")
    boundary = b"voice-chunked-boundary"
    prefix = (
        b"--"
        + boundary
        + b'\r\nContent-Disposition: form-data; name="session_id"\r\n\r\n'
        + b"voice-chunked\r\n--"
        + boundary
        + b'\r\nContent-Disposition: form-data; name="audio"; filename="sample.wav"\r\n'
        + b"Content-Type: audio/wav\r\n\r\n"
    )
    suffix = b"\r\n--" + boundary + b"--\r\n"

    response = client.post(
        "/api/voice/transcribe",
        content=iter([prefix, b"x" * (MAX_AUDIO_BYTES + 1), suffix]),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
    )

    assert response.status_code == 413
    assert response.json()["error_code"] == "audio_too_large"


def test_real_sidecar_transcribe_maps_silent_audio_to_invalid_audio_and_cleans_temp(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("VOICE_ENABLED", "true")
    temp_root = tmp_path / "voice-runtime"
    provider = SidecarVoiceProvider(
        SidecarManager(
            SidecarConfig(
                python_executable=Path(sys.executable),
                sidecar_script=Path(__file__).resolve().parents[1] / "scripts/voice_sidecar.py",
                extra_env={
                    "VOICE_NETWORK_DENY": "1",
                    "VOICE_PROVIDER_TEST_MODE": "1",
                    "VOICE_TEMP_ROOT": str(temp_root),
                },
                startup_timeout_seconds=2.0,
                stt_timeout_seconds=2.0,
                tts_timeout_seconds=2.0,
                temp_root=temp_root,
            )
        ),
        temp_root=temp_root,
    )
    monkeypatch.setattr(voice_api, "transcription_provider", provider)

    try:
        response = post_transcribe("voice-silent-sidecar", make_wav(1000))
    finally:
        provider.close()

    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_audio"
    assert not list(temp_root.iterdir())


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


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (VoiceProviderUnavailable(), "provider_unavailable"),
        (VoiceProviderTimeout(), "provider_timeout"),
        (VoiceLocalOnlyViolation(), "local_only_violation"),
    ],
)
def test_synthesize_maps_prediction_provider_failures(monkeypatch, error, code):
    monkeypatch.setenv("VOICE_ENABLED", "true")

    class BadPredict:
        def predict_duration_ms(self, text: str) -> int:
            raise error

        def synthesize(self, text: str) -> SynthesizedAudio:
            raise AssertionError("synthesis must not run after prediction failure")

    monkeypatch.setattr(voice_api, "synthesis_provider", BadPredict())

    response = client.post("/api/voice/synthesize", json={"text": "예측 실패"})

    assert response.status_code == 503
    assert response.json()["error_code"] == code


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
    assert response.headers["x-voice-duration-ms"] == "1000"
    assert "set-cookie" not in response.headers
    assert response.content == b"RIFFfake-wav"
