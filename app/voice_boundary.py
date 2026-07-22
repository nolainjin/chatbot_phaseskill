from __future__ import annotations

import subprocess
import wave
from dataclasses import dataclass
from io import BytesIO
from ipaddress import ip_address
from typing import Final, assert_never

from starlette.datastructures import FormData, UploadFile

from app.voice_contracts import (
    MAX_AUDIO_BYTES,
    MAX_AUDIO_DURATION_MS,
    AudioDecodeError,
    decode_wav_duration_ms,
)

BROWSER_AUDIO_MEDIA_TYPES: Final = frozenset(
    {"audio/mp4", "audio/webm", "audio/x-m4a", "video/mp4", "video/webm"}
)
FFMPEG_TIMEOUT_SECONDS: Final = 20.0
MAX_MULTIPART_OVERHEAD_BYTES: Final = 64 * 1024
NORMALIZED_CHANNELS: Final = 1
NORMALIZED_SAMPLE_RATE: Final = 16_000
PCM_SAMPLE_WIDTH: Final = 2


@dataclass(frozen=True, slots=True)
class PreparedTranscriptionAudio:
    content: bytes
    content_type: str | None
    duration_ms: int


def is_loopback_client(host: str | None) -> bool:
    if host == "testclient":
        return True
    if host is None:
        return False
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def declared_body_too_large(content_length: str | None) -> bool:
    if content_length is None:
        return False
    try:
        return int(content_length, 10) > (
            MAX_AUDIO_BYTES + MAX_MULTIPART_OVERHEAD_BYTES
        )
    except ValueError:
        return False


def parsed_multipart_payload_too_large(form: FormData) -> bool:
    total_size = 0
    for _, value in form.multi_items():
        match value:
            case str():
                part_size = len(value.encode("utf-8"))
            case UploadFile(size=None):
                return True
            case UploadFile(size=int() as size):
                part_size = size
            case unreachable:
                assert_never(unreachable)
        total_size += part_size
        if total_size > MAX_AUDIO_BYTES + MAX_MULTIPART_OVERHEAD_BYTES:
            return True
    return False


def prepare_transcription_audio(
    audio: bytes,
    content_type: str | None,
    ffmpeg_bin: str,
) -> PreparedTranscriptionAudio:
    try:
        duration_ms = decode_wav_duration_ms(audio)
    except AudioDecodeError:
        media_type = (content_type or "").partition(";")[0].strip().lower()
        if media_type not in BROWSER_AUDIO_MEDIA_TYPES:
            raise
    else:
        return PreparedTranscriptionAudio(audio, content_type, duration_ms)

    try:
        completed = subprocess.run(
            [
                ffmpeg_bin,
                "-nostdin",
                "-v",
                "error",
                "-i",
                "pipe:0",
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                str(NORMALIZED_CHANNELS),
                "-ar",
                str(NORMALIZED_SAMPLE_RATE),
                "-c:a",
                "pcm_s16le",
                "-t",
                str((MAX_AUDIO_DURATION_MS + 1000) / 1000),
                "-f",
                "s16le",
                "pipe:1",
            ],
            input=audio,
            check=True,
            capture_output=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except (
        FileNotFoundError,
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise AudioDecodeError from exc
    if not completed.stdout or len(completed.stdout) % PCM_SAMPLE_WIDTH:
        raise AudioDecodeError

    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(NORMALIZED_CHANNELS)
        wav.setsampwidth(PCM_SAMPLE_WIDTH)
        wav.setframerate(NORMALIZED_SAMPLE_RATE)
        wav.writeframes(completed.stdout)
    normalized = buffer.getvalue()
    return PreparedTranscriptionAudio(
        normalized,
        "audio/wav",
        decode_wav_duration_ms(normalized),
    )
