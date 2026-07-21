from __future__ import annotations

import io
import os
import subprocess
import sys
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.voice_contracts import AudioDecodeError, VoiceProviderTimeout, VoiceProviderUnavailable
from app.voice_provider import SidecarVoiceProvider
from voice_runtime.audio import validate_wav_bytes
from voice_runtime.audio import normalize_audio
from voice_runtime.sidecar import (
    SIDECAR_HOST,
    SIDECAR_STARTUP_TIMEOUT_SECONDS,
    STT_TIMEOUT_SECONDS,
    TTS_TIMEOUT_SECONDS,
    SidecarConfig,
    SidecarManager,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SIDECAR_SCRIPT = REPO_ROOT / "scripts/voice_sidecar.py"


def make_wav(duration_ms: int, *, silent: bool = False) -> bytes:
    frames = round(16_000 * duration_ms / 1000)
    sample = 0 if silent else 1000
    payload = (sample.to_bytes(2, "little", signed=True)) * frames
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(payload)
    return buffer.getvalue()


def make_manager(tmp_path: Path, *, stt_timeout: float = 2.0, tts_timeout: float = 2.0, **extra_env: str) -> SidecarManager:
    env = {
        "VOICE_PROVIDER_TEST_MODE": "1",
        "VOICE_NETWORK_DENY": "1",
        "VOICE_TEMP_ROOT": str(tmp_path / "voice-runtime"),
        **extra_env,
    }
    return SidecarManager(
        SidecarConfig(
            python_executable=Path(sys.executable),
            sidecar_script=SIDECAR_SCRIPT,
            startup_timeout_seconds=2.0,
            stt_timeout_seconds=stt_timeout,
            tts_timeout_seconds=tts_timeout,
            extra_env=env,
            temp_root=tmp_path / "voice-runtime",
        )
    )


def test_provider_defaults_are_loopback_and_bounded() -> None:
    assert SIDECAR_HOST == "127.0.0.1"
    assert SIDECAR_STARTUP_TIMEOUT_SECONDS == 20.0
    assert STT_TIMEOUT_SECONDS == 45.0
    assert TTS_TIMEOUT_SECONDS == 30.0
    with pytest.raises(ValueError):
        SidecarConfig(host="0.0.0.0")


def test_selected_provider_transcribes_offline_and_cleans_temp_files(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    provider = SidecarVoiceProvider(manager, temp_root=tmp_path / "voice-runtime")

    try:
        result = provider.transcribe(make_wav(1000), "audio/wav")
    finally:
        provider.close()

    assert result.text == "테스트 전사"
    assert result.provider == "fake-local-sidecar"
    assert not list((tmp_path / "voice-runtime").glob("voice-stt-*"))


@pytest.mark.parametrize(
    ("audio", "error"),
    [
        (b"not wav", AudioDecodeError),
        (make_wav(1000, silent=True), AudioDecodeError),
        (make_wav(799), AudioDecodeError),
        (make_wav(60_001), AudioDecodeError),
    ],
)
def test_provider_rejects_decoded_malformed_silent_and_out_of_range_audio(
    tmp_path: Path, audio: bytes, error: type[Exception]
) -> None:
    provider = SidecarVoiceProvider(make_manager(tmp_path), temp_root=tmp_path / "voice-runtime")
    try:
        with pytest.raises(error):
            provider.transcribe(audio, "audio/wav")
    finally:
        provider.close()
    assert not list((tmp_path / "voice-runtime").glob("voice-stt-*"))


def test_tts_is_one_shot_validated_pcm_wav(tmp_path: Path) -> None:
    provider = SidecarVoiceProvider(make_manager(tmp_path), temp_root=tmp_path / "voice-runtime")
    try:
        audio = provider.synthesize("안녕하세요")
    finally:
        provider.close()

    validated = validate_wav_bytes(audio.content)
    assert validated.media_type == "audio/wav"
    assert validated.sample_rate == 16_000
    assert validated.channels == 1
    assert not list((tmp_path / "voice-runtime").glob("voice-*"))


def test_provider_timeout_is_stable_and_restart_is_bounded(tmp_path: Path) -> None:
    provider = SidecarVoiceProvider(
        make_manager(tmp_path, stt_timeout=0.2, tts_timeout=0.2, VOICE_SIDECAR_TEST_BEHAVIOR="hang_stt"),
        temp_root=tmp_path / "voice-runtime",
    )
    try:
        with pytest.raises(VoiceProviderTimeout):
            provider.transcribe(make_wav(1000), "audio/wav")
    finally:
        provider.close()


def test_no_sidecar_operation_fails_closed_without_download_or_temp_leak(tmp_path: Path) -> None:
    config = SidecarConfig(
        python_executable=Path("/definitely/missing/python"),
        sidecar_script=SIDECAR_SCRIPT,
        auto_start=False,
        temp_root=tmp_path / "voice-runtime",
    )
    provider = SidecarVoiceProvider(SidecarManager(config), temp_root=config.temp_root)
    try:
        with pytest.raises(VoiceProviderUnavailable):
            provider.transcribe(make_wav(1000), "audio/wav")
    finally:
        provider.close()
    assert not list((tmp_path / "voice-runtime").glob("voice-*"))


def test_sidecar_shutdown_is_graceful(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    manager.start()
    process = manager.process
    manager.close()
    manager.close()
    assert process.poll() is not None


def test_killed_inflight_stt_fails_closed_without_replay_or_temp_leak(tmp_path: Path) -> None:
    marker = tmp_path / "first-stt-started"
    manager = make_manager(
        tmp_path,
        VOICE_SIDECAR_TEST_BEHAVIOR="block_first_stt",
        VOICE_SIDECAR_TEST_MARKER=str(marker),
    )
    provider = SidecarVoiceProvider(manager, temp_root=tmp_path / "voice-runtime")

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(provider.transcribe, make_wav(1000), "audio/wav")
            deadline = time.monotonic() + 2.0
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert marker.exists()
            manager.process.kill()

            with pytest.raises(VoiceProviderUnavailable):
                pending.result(timeout=3.0)

        result = provider.transcribe(make_wav(1000), "audio/wav")
    finally:
        provider.close()

    assert result.text == "테스트 전사"
    assert not list((tmp_path / "voice-runtime").iterdir())


def test_audio_temp_files_are_removed_when_cancelled(tmp_path: Path) -> None:
    with pytest.raises(KeyboardInterrupt):
        with normalize_audio(make_wav(1000), temp_root=tmp_path / "voice-runtime"):
            raise KeyboardInterrupt
    assert not list((tmp_path / "voice-runtime").glob("voice-stt-*"))


def test_disabled_app_does_not_import_or_start_provider(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["VOICE_ENABLED"] = "false"
    env["PYTHONPATH"] = str(REPO_ROOT)
    probe = subprocess.run(
        [sys.executable, "-c", "import sys; import app.main; print('app.voice_provider' in sys.modules)"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert probe.stdout.strip() == "False"
