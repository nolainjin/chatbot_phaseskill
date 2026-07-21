from __future__ import annotations

import io
import math
import subprocess
import tempfile
import wave
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from voice_runtime.errors import RuntimeAudioError

MAX_AUDIO_DURATION_MS: Final = 60_000
MIN_AUDIO_DURATION_MS: Final = 800

NORMALIZED_SAMPLE_RATE: Final = 16_000
NORMALIZED_CHANNELS: Final = 1
PCM_SAMPLE_WIDTH: Final = 2
FFMPEG_TIMEOUT_SECONDS: Final = 20.0


@dataclass(frozen=True, slots=True)
class WavInfo:
    duration_ms: int
    sample_rate: int
    channels: int
    sample_width: int
    frames: int


@dataclass(frozen=True, slots=True)
class RuntimeSynthesizedAudio:
    content: bytes
    media_type: str
    duration_ms: int
    sample_rate: int
    channels: int


def _parse_wav(source: io.BytesIO | Path) -> tuple[WavInfo, bytes]:
    try:
        if isinstance(source, Path):
            with source.open("rb") as handle, wave.open(handle, "rb") as wav:
                frames = wav.getnframes()
                sample_rate = wav.getframerate()
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                compression = wav.getcomptype()
                payload = wav.readframes(frames)
        else:
            with wave.open(source, "rb") as wav:
                frames = wav.getnframes()
                sample_rate = wav.getframerate()
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                compression = wav.getcomptype()
                payload = wav.readframes(frames)
    except (EOFError, OSError, wave.Error) as exc:
        raise RuntimeAudioError("audio is not a readable WAV") from exc
    if (
        frames <= 0
        or sample_rate <= 0
        or channels <= 0
        or sample_width <= 0
        or compression != "NONE"
        or len(payload) != frames * channels * sample_width
    ):
        raise RuntimeAudioError("audio has invalid decoded frames")
    return WavInfo(math.ceil(frames * 1000 / sample_rate), sample_rate, channels, sample_width, frames), payload


def _ensure_duration(info: WavInfo) -> None:
    if info.duration_ms < MIN_AUDIO_DURATION_MS:
        raise RuntimeAudioError("audio is shorter than the minimum duration")
    if info.duration_ms > MAX_AUDIO_DURATION_MS:
        raise RuntimeAudioError("audio exceeds the maximum duration")


def _ensure_not_silent(info: WavInfo, payload: bytes) -> None:
    if info.sample_width != PCM_SAMPLE_WIDTH or info.channels != NORMALIZED_CHANNELS:
        return
    if not any(abs(int.from_bytes(payload[index : index + 2], "little", signed=True)) > 8 for index in range(0, len(payload), 2)):
        raise RuntimeAudioError("audio is silent")


def _validate_normalized(path: Path) -> WavInfo:
    info, payload = _parse_wav(path)
    if info.sample_rate != NORMALIZED_SAMPLE_RATE or info.channels != NORMALIZED_CHANNELS or info.sample_width != PCM_SAMPLE_WIDTH:
        raise RuntimeAudioError("audio was not normalized to 16 kHz mono PCM")
    _ensure_duration(info)
    _ensure_not_silent(info, payload)
    return info


@contextmanager
def normalize_audio(path_or_bytes: str | Path | bytes, *, ffmpeg_bin: str = "ffmpeg", temp_root: Path | None = None) -> Iterator[Path]:
    root = Path(temp_root) if temp_root is not None else None
    if root is not None:
        root.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="voice-stt-", dir=str(root) if root is not None else None) as directory:
            work = Path(directory)
            source = work / "input.audio"
            normalized = work / "normalized.wav"
            if isinstance(path_or_bytes, bytes):
                source.write_bytes(path_or_bytes)
            else:
                source.write_bytes(Path(path_or_bytes).read_bytes())
            try:
                subprocess.run(
                    [ffmpeg_bin, "-nostdin", "-v", "error", "-i", str(source), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-y", str(normalized)],
                    check=True,
                    capture_output=True,
                    timeout=FFMPEG_TIMEOUT_SECONDS,
                )
            except (FileNotFoundError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                raise RuntimeAudioError("ffmpeg could not decode audio") from exc
            _validate_normalized(normalized)
            yield normalized
    except (RuntimeAudioError, OSError) as exc:
        if isinstance(exc, RuntimeAudioError):
            raise
        raise RuntimeAudioError("audio source could not be read") from exc


def validate_wav_bytes(content: bytes) -> RuntimeSynthesizedAudio:
    info, _ = _parse_wav(io.BytesIO(content))
    if info.sample_width not in {2, 3, 4} or info.channels not in {1, 2}:
        raise RuntimeAudioError("provider returned unsupported PCM")
    if info.duration_ms <= 0 or info.duration_ms > MAX_AUDIO_DURATION_MS:
        raise RuntimeAudioError("provider returned audio outside duration limits")
    return RuntimeSynthesizedAudio(
        content=content,
        media_type="audio/wav",
        duration_ms=info.duration_ms,
        sample_rate=info.sample_rate,
        channels=info.channels,
    )
