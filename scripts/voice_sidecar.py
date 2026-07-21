#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run voice_sidecar.py --host 127.0.0.1 --port 8765
# 3. Or make executable and run:
#      chmod +x voice_sidecar.py && ./voice_sidecar.py
# ──────────────────

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import tempfile
import time
import wave
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import FrameType
from typing import Protocol
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from voice_runtime.adapters import SttBackend, TtsBackend, build_backends, fake_wav
from voice_runtime.errors import RuntimeAudioError as AudioDecodeError
from voice_runtime.errors import RuntimeLocalOnlyViolation as VoiceLocalOnlyViolation
from voice_runtime.errors import RuntimeProviderTimeout as VoiceProviderTimeout
from voice_runtime.errors import RuntimeProviderUnavailable as VoiceProviderUnavailable


class BackendBundle:
    def __init__(self, stt: SttBackend, tts: TtsBackend, stt_model: str, stt_provider: str, tts_provider: str) -> None:
        self.stt = stt
        self.tts = tts
        self.stt_model = stt_model
        self.stt_provider = stt_provider
        self.tts_provider = tts_provider


class FakeBackend:
    stt_model = "fake-test"
    stt_provider = "fake-local-sidecar"
    tts_provider = "fake-local-sidecar"

    def transcribe(self, _audio_path: Path) -> str:
        behavior = os.getenv("VOICE_SIDECAR_TEST_BEHAVIOR", "")
        if behavior == "hang_stt":
            time.sleep(5.0)
        if behavior == "fail_stt":
            raise VoiceProviderUnavailable
        return "테스트 전사"

    def synthesize(self, _text: str) -> bytes:
        if os.getenv("VOICE_SIDECAR_TEST_BEHAVIOR", "") == "fail_tts":
            raise VoiceProviderUnavailable
        return fake_wav()


def _handler(backend: BackendBundle | FakeBackend, temp_root: Path | None) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "voice-sidecar/1"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _send(self, status: int, content: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _json(self, status: int, payload: dict[str, str]) -> None:
            self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json")

        def do_GET(self) -> None:
            if self.path != "/health":
                self._json(HTTPStatus.NOT_FOUND, {"error_code": "provider_unavailable"})
                return
            model = backend.stt_model if isinstance(backend, BackendBundle) else backend.stt_model
            self._json(HTTPStatus.OK, {"status": "ok", "stt": model})

        def _read_body(self) -> bytes:
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise AudioDecodeError("invalid content length") from exc
            if length <= 0 or length > 10 * 1024 * 1024:
                raise AudioDecodeError("invalid request body")
            return self.rfile.read(length)

        def do_POST(self) -> None:
            try:
                if self.path == "/transcribe":
                    self._transcribe()
                    return
                if self.path == "/synthesize":
                    self._synthesize()
                    return
                self._json(HTTPStatus.NOT_FOUND, {"error_code": "provider_unavailable"})
            except AudioDecodeError:
                self._json(HTTPStatus.BAD_REQUEST, {"error_code": "invalid_audio"})
            except VoiceProviderTimeout:
                self._json(HTTPStatus.GATEWAY_TIMEOUT, {"error_code": "provider_timeout"})
            except VoiceLocalOnlyViolation:
                self._json(HTTPStatus.CONFLICT, {"error_code": "local_only_violation"})
            except VoiceProviderUnavailable:
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error_code": "provider_unavailable"})

        def _transcribe(self) -> None:
            body = self._read_body()
            directory = tempfile.TemporaryDirectory(prefix="voice-sidecar-", dir=str(temp_root) if temp_root else None)
            try:
                audio_path = Path(directory.name) / "normalized.wav"
                audio_path.write_bytes(body)
                if isinstance(backend, FakeBackend):
                    text = backend.transcribe(audio_path)
                    payload = {"text": text, "language": "ko", "model": backend.stt_model, "provider": backend.stt_provider}
                else:
                    text = backend.stt.transcribe(audio_path)
                    payload = {"text": text, "language": "ko", "model": backend.stt_model, "provider": backend.stt_provider}
                self._send(HTTPStatus.OK, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json")
            finally:
                directory.cleanup()

        def _synthesize(self) -> None:
            text = self._read_body().decode("utf-8")
            if not text.strip():
                self._json(HTTPStatus.BAD_REQUEST, {"error_code": "invalid_text"})
                return
            if isinstance(backend, FakeBackend):
                content = backend.synthesize(text)
            else:
                content = backend.tts.synthesize(text)
            self._send(HTTPStatus.OK, content, "audio/wav")

    return Handler


def _parse_args(argv: list[str]) -> tuple[str, int]:
    host = ""
    port = 0
    index = 0
    while index < len(argv):
        if argv[index] == "--host" and index + 1 < len(argv):
            host = argv[index + 1]
            index += 2
            continue
        if argv[index] == "--port" and index + 1 < len(argv):
            port = int(argv[index + 1])
            index += 2
            continue
        raise ValueError("unsupported sidecar argument")
    return host, port


def _network_guard() -> patch[None]:
    if os.getenv("VOICE_NETWORK_DENY") != "1":
        return patch.dict(os.environ, {})
    original_connect = socket.socket.connect

    def blocked_connect(sock: socket.socket, address: object) -> None:
        if isinstance(address, tuple) and address and address[0] not in {"127.0.0.1", "::1"}:
            raise OSError("VOICE_NETWORK_DENY blocked outbound connect")
        original_connect(sock, address)

    return patch.object(socket.socket, "connect", blocked_connect)


def main(argv: list[str] | None = None) -> int:
    try:
        host, port = _parse_args(sys.argv[1:] if argv is None else argv)
        if host != "127.0.0.1" or not 0 < port <= 65_535:
            return 2
        if os.getenv("VOICE_PROVIDER_TEST_MODE") == "1":
            backend: BackendBundle | FakeBackend = FakeBackend()
        else:
            stt_name = os.getenv("VOICE_STT_PROVIDER", "qwen3-asr-0.6b-8bit")
            stt, tts, stt_model, tts_provider = build_backends(stt_name)
            stt_provider = "mlx-audio" if stt_name == "qwen3-asr-0.6b-8bit" else "whisper.cpp"
            backend = BackendBundle(stt, tts, stt_model, stt_provider, tts_provider)
        temp_root = Path(os.getenv("VOICE_TEMP_ROOT", ".voice-tmp"))
        temp_root.mkdir(parents=True, exist_ok=True)
        server = ThreadingHTTPServer((host, port), _handler(backend, temp_root))
        server.daemon_threads = True
        def stop(_signal: int, _frame: FrameType | None) -> None:
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, stop)
        with _network_guard():
            server.serve_forever()
    except (OSError, ValueError, VoiceProviderUnavailable):
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        if "server" in locals():
            server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
