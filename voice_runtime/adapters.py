from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Protocol

from voice_runtime.audio import validate_wav_bytes
from voice_runtime.errors import RuntimeAudioError, RuntimeProviderTimeout, RuntimeProviderUnavailable


class SttBackend(Protocol):
    def transcribe(self, audio_path: Path) -> str: ...


class TtsBackend(Protocol):
    def synthesize(self, text: str) -> bytes: ...


class QwenAsrBackend:
    def __init__(self, model_path: Path | None) -> None:
        self.model_path = model_path
        self._model = None

    def transcribe(self, audio_path: Path) -> str:
        if self.model_path is None or not self.model_path.is_dir():
            raise RuntimeProviderUnavailable
        if self._model is None:
            try:
                from mlx_audio.stt import load

                self._model = load(str(self.model_path))
            except (ImportError, OSError, RuntimeError, ValueError) as exc:
                raise RuntimeProviderUnavailable from exc
        try:
            result = self._model.generate(str(audio_path), language="ko", max_tokens=256, temperature=0.0, verbose=False)
            text = str(result.text).strip()
        except (AttributeError, OSError, RuntimeError, ValueError) as exc:
            raise RuntimeProviderUnavailable from exc
        if not text:
            raise RuntimeProviderUnavailable
        return text


class WhisperCppBackend:
    def __init__(self, executable: str, model_path: Path | None) -> None:
        self.executable = executable
        self.model_path = model_path

    def transcribe(self, audio_path: Path) -> str:
        if self.model_path is None or not self.model_path.is_file():
            raise RuntimeProviderUnavailable
        executable = shutil.which(self.executable) or self.executable
        try:
            result = subprocess.run(
                [executable, "-m", str(self.model_path), "-f", str(audio_path), "-l", "ko", "-nt"],
                check=False,
                capture_output=True,
                text=True,
                timeout=45.0,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeProviderTimeout from exc
        except (FileNotFoundError, OSError) as exc:
            raise RuntimeProviderUnavailable from exc
        if result.returncode != 0:
            raise RuntimeProviderUnavailable
        text = result.stdout.strip()
        if not text:
            raise RuntimeProviderUnavailable
        return text


class MacSayBackend:
    def __init__(self, voice: str = "Yuna") -> None:
        self.voice = voice

    def synthesize(self, text: str) -> bytes:
        try:
            with tempfile.TemporaryDirectory(prefix="voice-tts-") as directory:
                aiff = Path(directory) / "speech.aiff"
                wav = Path(directory) / "speech.wav"
                subprocess.run(
                    ["/usr/bin/say", "-v", self.voice, "-o", str(aiff), text],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30.0,
                )
                subprocess.run(
                    ["ffmpeg", "-nostdin", "-v", "error", "-i", str(aiff), "-ac", "1", "-ar", "22050", "-c:a", "pcm_s16le", "-f", "wav", "-y", str(wav)],
                    check=True,
                    capture_output=True,
                    timeout=30.0,
                )
                content = wav.read_bytes()
        except subprocess.TimeoutExpired as exc:
            raise RuntimeProviderTimeout from exc
        except (FileNotFoundError, OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeProviderUnavailable from exc
        try:
            return validate_wav_bytes(content).content
        except RuntimeAudioError as exc:
            raise RuntimeProviderUnavailable from exc


def _model_path_from_env() -> Path | None:
    raw = os.getenv("VOICE_MODEL_PATH")
    if raw:
        return Path(raw)
    root = Path.cwd() / ".voice-model-cache" / "hub" / "models--mlx-community--Qwen3-ASR-0.6B-8bit" / "snapshots"
    snapshots = sorted(item for item in root.iterdir() if item.is_dir()) if root.is_dir() else []
    return snapshots[-1] if snapshots else None


def build_backends(stt_provider: str, *, model_path: Path | None = None) -> tuple[SttBackend, TtsBackend, str, str]:
    match stt_provider:
        case "qwen3-asr-0.6b-8bit":
            stt = QwenAsrBackend(model_path or _model_path_from_env())
            model = stt_provider
        case "whisper.cpp":
            raw_model = os.getenv("VOICE_WHISPER_CPP_MODEL")
            stt = WhisperCppBackend(os.getenv("VOICE_WHISPER_CPP_BIN", "whisper-cli"), Path(raw_model) if raw_model else None)
            model = "whisper.cpp"
        case _:
            raise RuntimeProviderUnavailable
    return stt, MacSayBackend(os.getenv("VOICE_TTS_VOICE", "Yuna")), model, "macos-say"


def fake_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes((1000).to_bytes(2, "little", signed=True) * 16_000)
    return buffer.getvalue()
