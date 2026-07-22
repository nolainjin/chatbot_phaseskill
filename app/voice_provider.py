from __future__ import annotations

import json
import math
import os
import threading
from pathlib import Path

from app.voice_contracts import (
    AudioDecodeError,
    SynthesizedAudio,
    TranscriptionProviderOutput,
    VoiceProviderUnavailable,
)
from voice_runtime.audio import normalize_audio, validate_wav_bytes
from voice_runtime.errors import RuntimeAudioError
from voice_runtime.sidecar import SidecarConfig, SidecarManager


class SidecarVoiceProvider:
    def __init__(self, manager: SidecarManager, *, temp_root: Path | None = None) -> None:
        self.manager = manager
        self.temp_root = temp_root or manager.config.temp_root
        self._operation_lock = threading.RLock()

    def transcribe(self, path_or_bytes: str | Path | bytes, content_type: str | None = None) -> TranscriptionProviderOutput:
        del content_type
        with self._operation_lock:
            try:
                with normalize_audio(
                    path_or_bytes,
                    ffmpeg_bin=os.getenv("VOICE_FFMPEG_BIN", "ffmpeg"),
                    temp_root=self.temp_root,
                ) as normalized:
                    response = self.manager.transcribe(normalized.read_bytes())
            except RuntimeAudioError as exc:
                raise AudioDecodeError(str(exc)) from exc
            try:
                payload = json.loads(response.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError
                text = payload["text"]
                language = payload.get("language", "ko")
                model = payload["model"]
                provider = payload["provider"]
                if not all(
                    isinstance(value, str)
                    for value in (text, language, model, provider)
                ):
                    raise ValueError
                return TranscriptionProviderOutput(
                    text=text,
                    language=language,
                    model=model,
                    provider=provider,
                )
            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                raise VoiceProviderUnavailable from exc

    def predict_duration_ms(self, text: str) -> int:
        return math.ceil(len(text) * 1000 / 20)

    def synthesize(self, text: str) -> SynthesizedAudio:
        with self._operation_lock:
            response, _headers = self.manager.synthesize(text)
            try:
                audio = validate_wav_bytes(response)
            except RuntimeAudioError as exc:
                raise VoiceProviderUnavailable from exc
            return SynthesizedAudio(
                content=audio.content,
                media_type=audio.media_type,
                duration_ms=audio.duration_ms,
                sample_rate=audio.sample_rate,
                channels=audio.channels,
            )

    def close(self) -> None:
        with self._operation_lock:
            self.manager.close()

    def __enter__(self) -> SidecarVoiceProvider:
        with self._operation_lock:
            self.manager.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def build_local_voice_provider() -> SidecarVoiceProvider:
    config = SidecarConfig(
        python_executable=Path(os.getenv("VOICE_PROVIDER_PYTHON", ".voice-venv/bin/python")),
        sidecar_script=Path(os.getenv("VOICE_SIDECAR_SCRIPT", "scripts/voice_sidecar.py")),
        extra_env={key: value for key, value in os.environ.items() if key.startswith("VOICE_")},
        temp_root=Path(os.getenv("VOICE_TEMP_ROOT", ".voice-tmp")),
    )
    return SidecarVoiceProvider(SidecarManager(config), temp_root=config.temp_root)
