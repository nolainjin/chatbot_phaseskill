from __future__ import annotations

import math
import wave
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO
from typing import Final, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_AUDIO_BYTES: Final = 10 * 1024 * 1024
MIN_AUDIO_DURATION_MS: Final = 800
MAX_AUDIO_DURATION_MS: Final = 60_000
MAX_TTS_CHARS: Final = 1200


class VoiceErrorCode(StrEnum):
    VOICE_DISABLED = "voice_disabled"
    INVALID_REQUEST = "invalid_request"
    INVALID_AUDIO = "invalid_audio"
    AUDIO_TOO_LARGE = "audio_too_large"
    AUDIO_TOO_SHORT = "audio_too_short"
    AUDIO_TOO_LONG = "audio_too_long"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_TIMEOUT = "provider_timeout"
    LOCAL_ONLY_VIOLATION = "local_only_violation"
    SESSION_AUTH_REQUIRED = "session_auth_required"
    INVALID_TEXT = "invalid_text"


class VoiceProviderError(RuntimeError):
    error_code = VoiceErrorCode.PROVIDER_UNAVAILABLE


class VoiceProviderUnavailable(VoiceProviderError):
    pass


class VoiceProviderTimeout(VoiceProviderError):
    error_code = VoiceErrorCode.PROVIDER_TIMEOUT


class VoiceLocalOnlyViolation(VoiceProviderError):
    error_code = VoiceErrorCode.LOCAL_ONLY_VIOLATION


class AudioDecodeError(ValueError):
    pass


class VoiceErrorResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    error_code: VoiceErrorCode
    detail: str


class TranscriptionProviderOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1, max_length=2000)
    language: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=128)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("provider transcript is blank")
        return value


class TranscriptionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1, max_length=2000)
    language: str = Field(min_length=1, max_length=32)
    duration_ms: int = Field(ge=MIN_AUDIO_DURATION_MS, le=MAX_AUDIO_DURATION_MS)
    model: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=128)
    latency_ms: int = Field(ge=0)


class SynthesizeRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    session_id: str | None = None
    session_token: str | None = None


@dataclass(frozen=True, slots=True)
class SynthesizedAudio:
    content: bytes
    media_type: str
    duration_ms: int
    sample_rate: int
    channels: int


class TranscriptionProvider(Protocol):
    def transcribe(self, audio: bytes, content_type: str | None) -> TranscriptionProviderOutput: ...


class SynthesisProvider(Protocol):
    def predict_duration_ms(self, text: str) -> int: ...

    def synthesize(self, text: str) -> SynthesizedAudio: ...


class UnavailableTranscriptionProvider:
    def transcribe(self, audio: bytes, content_type: str | None) -> TranscriptionProviderOutput:
        raise VoiceProviderUnavailable


class UnavailableSynthesisProvider:
    def predict_duration_ms(self, text: str) -> int:
        return math.ceil(len(text) * 1000 / 20)

    def synthesize(self, text: str) -> SynthesizedAudio:
        raise VoiceProviderUnavailable


def decode_wav_duration_ms(audio: bytes) -> int:
    if not audio:
        raise AudioDecodeError
    try:
        with wave.open(BytesIO(audio)) as wav:
            frame_count = wav.getnframes()
            frame_rate = wav.getframerate()
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
    except (EOFError, wave.Error) as exc:
        raise AudioDecodeError from exc
    if frame_count <= 0 or frame_rate <= 0 or channels <= 0 or sample_width <= 0:
        raise AudioDecodeError
    return math.ceil(frame_count * 1000 / frame_rate)


def validate_synthesized_audio(audio: SynthesizedAudio) -> bool:
    return bool(
        audio.content
        and audio.media_type == "audio/wav"
        and 0 < audio.duration_ms <= MAX_AUDIO_DURATION_MS
        and audio.sample_rate > 0
        and audio.channels > 0
    )
