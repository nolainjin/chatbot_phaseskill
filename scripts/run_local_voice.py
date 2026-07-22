from __future__ import annotations

import argparse
import os
import signal
import shutil
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import FrameType
from typing import Final, Protocol, Sequence, assert_never


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
LOOPBACK_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 8767
QWEN_SNAPSHOTS: Final = (
    REPO_ROOT
    / ".voice-model-cache"
    / "hub"
    / "models--mlx-community--Qwen3-ASR-0.6B-8bit"
    / "snapshots"
)


class SttProfile(StrEnum):
    QWEN = "qwen3-asr-0.6b-8bit"
    WHISPER_CPP = "whisper.cpp"


class ClosableVoiceProvider(Protocol):
    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class LauncherPreflightError(RuntimeError):
    component: str
    location: Path

    def __str__(self) -> str:
        return f"missing local voice component: {self.component} ({self.location})"


@dataclass(frozen=True, slots=True)
class _LauncherTermination(BaseException):
    signum: int


def _loopback_host(value: str) -> str:
    if value != LOOPBACK_HOST:
        raise argparse.ArgumentTypeError("voice launcher only accepts 127.0.0.1")
    return value


def _port(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 0 < parsed <= 65_535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the local-only FastAPI app with the configured voice provider."
    )
    parser.add_argument("--host", type=_loopback_host, default=LOOPBACK_HOST)
    parser.add_argument("--port", type=_port, default=DEFAULT_PORT)
    return parser


def _latest_qwen_snapshot() -> Path | None:
    if not QWEN_SNAPSHOTS.is_dir():
        return None
    snapshots = sorted(path for path in QWEN_SNAPSHOTS.iterdir() if path.is_dir())
    return snapshots[-1] if snapshots else None


def _apply_environment_defaults() -> None:
    os.environ["VOICE_ENABLED"] = "true"
    os.environ["VOICE_NETWORK_DENY"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ.setdefault(
        "VOICE_PROVIDER_PYTHON", str(REPO_ROOT / ".voice-venv" / "bin" / "python")
    )
    os.environ.setdefault("VOICE_SIDECAR_SCRIPT", str(REPO_ROOT / "scripts" / "voice_sidecar.py"))
    os.environ.setdefault("VOICE_STT_PROVIDER", SttProfile.QWEN)
    os.environ.setdefault("VOICE_TTS_VOICE", "Yuna")
    os.environ.setdefault("VOICE_TEMP_ROOT", str(REPO_ROOT / ".voice-tmp"))
    if os.environ["VOICE_STT_PROVIDER"] == SttProfile.QWEN and "VOICE_MODEL_PATH" not in os.environ:
        snapshot = _latest_qwen_snapshot()
        if snapshot is not None:
            os.environ["VOICE_MODEL_PATH"] = str(snapshot)


def _preflight_local_runtime() -> None:
    provider_python = Path(os.environ.get("VOICE_PROVIDER_PYTHON", ""))
    if not provider_python.is_file() or not os.access(provider_python, os.X_OK):
        raise LauncherPreflightError("provider_python", provider_python)

    sidecar_script = Path(os.environ.get("VOICE_SIDECAR_SCRIPT", ""))
    if not sidecar_script.is_file():
        raise LauncherPreflightError("sidecar_script", sidecar_script)

    ffmpeg = os.environ.get("VOICE_FFMPEG_BIN", "ffmpeg")
    if shutil.which(ffmpeg) is None:
        raise LauncherPreflightError("ffmpeg", Path(ffmpeg))

    if os.environ.get("VOICE_PROVIDER_TEST_MODE") == "1":
        return

    raw_profile = os.environ.get("VOICE_STT_PROVIDER", SttProfile.QWEN)
    try:
        profile = SttProfile(raw_profile)
    except ValueError as exc:
        raise LauncherPreflightError("stt_profile", Path(raw_profile)) from exc
    match profile:
        case SttProfile.QWEN:
            raw_model_path = os.environ.get("VOICE_MODEL_PATH")
            model_path = Path(raw_model_path) if raw_model_path else QWEN_SNAPSHOTS
            if not raw_model_path or not model_path.is_dir():
                raise LauncherPreflightError("model_cache", model_path)
        case SttProfile.WHISPER_CPP:
            raw_model_path = os.environ.get("VOICE_WHISPER_CPP_MODEL")
            model_path = Path(raw_model_path) if raw_model_path else Path("VOICE_WHISPER_CPP_MODEL")
            if not raw_model_path or not model_path.is_file():
                raise LauncherPreflightError("model_cache", model_path)
            executable = os.environ.get("VOICE_WHISPER_CPP_BIN", "whisper-cli")
            if shutil.which(executable) is None:
                raise LauncherPreflightError("stt_executable", Path(executable))
        case unreachable:
            assert_never(unreachable)


def _run_server(host: str, port: int) -> None:
    _preflight_local_runtime()
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    os.chdir(REPO_ROOT)

    import uvicorn

    from app import voice_api
    from app.main import app
    from app.voice_provider import build_local_voice_provider

    unavailable_transcription = voice_api.transcription_provider
    unavailable_synthesis = voice_api.synthesis_provider
    provider: ClosableVoiceProvider = build_local_voice_provider()
    try:
        voice_api.transcription_provider = provider
        voice_api.synthesis_provider = provider
        uvicorn.run(app, host=host, port=port)
    finally:
        try:
            provider.close()
        finally:
            voice_api.transcription_provider = unavailable_transcription
            voice_api.synthesis_provider = unavailable_synthesis


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _apply_environment_defaults()
    original_handlers: dict[int, signal.Handlers] = {}

    def terminate(signum: int, _frame: FrameType | None) -> None:
        raise _LauncherTermination(signum)

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            original_handlers[signum] = signal.signal(signum, terminate)
        _run_server(args.host, args.port)
    except LauncherPreflightError as exc:
        print(f"voice launcher preflight failed: {exc}", file=sys.stderr)
        return 3
    except _LauncherTermination as exc:
        return 128 + exc.signum
    except KeyboardInterrupt:
        return 130
    except (ImportError, OSError, RuntimeError) as exc:
        print(f"voice launcher failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    finally:
        for signum, handler in original_handlers.items():
            signal.signal(signum, handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
