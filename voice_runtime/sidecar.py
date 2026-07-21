from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Self

from app.voice_contracts import (
    VoiceLocalOnlyViolation,
    VoiceProviderTimeout,
    VoiceProviderUnavailable,
)

SIDECAR_HOST: Final = "127.0.0.1"
SIDECAR_STARTUP_TIMEOUT_SECONDS: Final = 20.0
STT_TIMEOUT_SECONDS: Final = 45.0
TTS_TIMEOUT_SECONDS: Final = 30.0
RESTART_ATTEMPTS: Final = 1
REQUEST_ERRORS: Final = (ConnectionError, OSError, TimeoutError, urllib.error.URLError, http.client.HTTPException)


@dataclass(frozen=True, slots=True)
class SidecarConfig:
    python_executable: Path = field(default_factory=lambda: Path(sys.executable))
    sidecar_script: Path = field(default_factory=lambda: Path(__file__).resolve().parents[1] / "scripts" / "voice_sidecar.py")
    host: str = SIDECAR_HOST
    port: int = 0
    startup_timeout_seconds: float = SIDECAR_STARTUP_TIMEOUT_SECONDS
    stt_timeout_seconds: float = STT_TIMEOUT_SECONDS
    tts_timeout_seconds: float = TTS_TIMEOUT_SECONDS
    restart_attempts: int = RESTART_ATTEMPTS
    auto_start: bool = True
    extra_env: dict[str, str] | None = None
    temp_root: Path | None = None

    def __post_init__(self) -> None:
        if self.host != SIDECAR_HOST:
            raise ValueError("voice sidecar must bind to 127.0.0.1")
        if not 0 <= self.port <= 65_535:
            raise ValueError("invalid sidecar port")
        if self.restart_attempts < 0:
            raise ValueError("restart attempts cannot be negative")


class SidecarManager:
    def __init__(self, config: SidecarConfig) -> None:
        self.config = config
        self._process: subprocess.Popen[bytes] | None = None
        self._port = config.port

    @property
    def process(self) -> subprocess.Popen[bytes]:
        if self._process is None:
            raise VoiceProviderUnavailable
        return self._process

    @property
    def port(self) -> int:
        return self._port

    def _reserve_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((SIDECAR_HOST, 0))
            return int(sock.getsockname()[1])

    def _environment(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.config.extra_env is not None:
            env.update(self.config.extra_env)
        if env.get("VOICE_NETWORK_DENY") == "1":
            env["HF_HUB_OFFLINE"] = "1"
            env["TRANSFORMERS_OFFLINE"] = "1"
        return env

    def _health(self, timeout: float) -> bool:
        try:
            with urllib.request.urlopen(f"http://{SIDECAR_HOST}:{self._port}/health", timeout=timeout) as response:
                return response.status == 200
        except (ConnectionError, OSError, TimeoutError, urllib.error.URLError, http.client.HTTPException):
            return False

    def start(self) -> None:
        if self._process is not None and self._process.poll() is None and self._health(0.2):
            return
        if not self.config.auto_start:
            raise VoiceProviderUnavailable
        self._port = self.config.port or self._reserve_port()
        try:
            self._process = subprocess.Popen(
                [str(self.config.python_executable), str(self.config.sidecar_script), "--host", SIDECAR_HOST, "--port", str(self._port)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self._environment(),
            )
        except (FileNotFoundError, OSError) as exc:
            self._process = None
            raise VoiceProviderUnavailable from exc
        deadline = time.monotonic() + self.config.startup_timeout_seconds
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                self.close()
                raise VoiceProviderUnavailable
            if self._health(min(0.2, max(deadline - time.monotonic(), 0.01))):
                return
            time.sleep(0.05)
        self.close()
        raise VoiceProviderUnavailable

    def _raise_http_error(self, error: urllib.error.HTTPError) -> None:
        try:
            body = error.read()
        except OSError:
            body = b""
        code = "provider_unavailable"
        try:
            parsed = json.loads(body.decode("utf-8"))
            if isinstance(parsed, dict) and isinstance(parsed.get("error_code"), str):
                code = parsed["error_code"]
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            pass
        match code:
            case "provider_timeout":
                raise VoiceProviderTimeout
            case "local_only_violation":
                raise VoiceLocalOnlyViolation
            case "provider_unavailable":
                raise VoiceProviderUnavailable
            case _:
                raise VoiceProviderUnavailable

    def _raw_request(self, endpoint: str, body: bytes | None, timeout: float) -> tuple[bytes, dict[str, str]]:
        request = urllib.request.Request(f"http://{SIDECAR_HOST}:{self._port}{endpoint}", data=body, method="POST")
        request.add_header("Content-Type", "application/octet-stream")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(), dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            self._raise_http_error(exc)
        except (TimeoutError, socket.timeout) as exc:
            raise VoiceProviderTimeout from exc
        except REQUEST_ERRORS as exc:
            raise VoiceProviderUnavailable from exc

    def _request(self, endpoint: str, body: bytes | None, timeout: float) -> tuple[bytes, dict[str, str]]:
        self.start()
        for attempt in range(self.config.restart_attempts + 1):
            try:
                return self._raw_request(endpoint, body, timeout)
            except VoiceProviderTimeout:
                if attempt >= self.config.restart_attempts:
                    raise
                self._restart()
            except VoiceProviderUnavailable as exc:
                if attempt >= self.config.restart_attempts:
                    raise
                self._restart()
                if self._process is None:
                    raise VoiceProviderUnavailable from exc
        raise VoiceProviderUnavailable

    def _restart(self) -> None:
        self.close()
        self.start()

    def transcribe(self, audio: bytes) -> bytes:
        return self._request("/transcribe", audio, self.config.stt_timeout_seconds)[0]

    def synthesize(self, text: str) -> tuple[bytes, dict[str, str]]:
        return self._request("/synthesize", text.encode("utf-8"), self.config.tts_timeout_seconds)

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2.0)

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
