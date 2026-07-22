from __future__ import annotations

import importlib
import os
import signal
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_ENV_KEYS = (
    "VOICE_ENABLED",
    "VOICE_NETWORK_DENY",
    "HF_HUB_OFFLINE",
    "TRANSFORMERS_OFFLINE",
    "VOICE_PROVIDER_PYTHON",
    "VOICE_SIDECAR_SCRIPT",
    "VOICE_STT_PROVIDER",
    "VOICE_TTS_VOICE",
    "VOICE_TEMP_ROOT",
    "VOICE_MODEL_PATH",
    "VOICE_WHISPER_CPP_MODEL",
    "VOICE_WHISPER_CPP_BIN",
    "VOICE_FFMPEG_BIN",
    "VOICE_PROVIDER_TEST_MODE",
)


class ServerFailure(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def isolate_launcher_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in LAUNCHER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _launcher() -> ModuleType:
    return importlib.import_module("scripts.run_local_voice")


def test_import_is_side_effect_free() -> None:
    # Given: a fresh interpreter with only the repository on PYTHONPATH.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    probe = (
        "import sys; import scripts.run_local_voice; "
        "names=('app.voice_provider','app.voice_api','voice_runtime.sidecar',"
        "'voice_runtime.adapters','app.main','uvicorn'); "
        "print(','.join(name for name in names if name in sys.modules))"
    )

    # When: the launcher module is imported without executing its entry point.
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )

    # Then: no application, provider, sidecar, or server module was imported.
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_launcher_removes_inherited_provider_test_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _launcher()
    monkeypatch.setenv("VOICE_PROVIDER_TEST_MODE", "1")

    module._apply_environment_defaults()

    assert "VOICE_PROVIDER_TEST_MODE" not in os.environ


@pytest.mark.skipif(not hasattr(signal, "SIGTERM"), reason="SIGTERM is unavailable")
def test_sigterm_is_classified_instead_of_killing_cleanup_path() -> None:
    # Given: uvicorn re-raises SIGTERM after its graceful shutdown phase.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    probe = (
        "import os, signal; import scripts.run_local_voice as launcher; "
        "launcher._apply_environment_defaults = lambda: None; "
        "launcher._run_server = lambda _host, _port: os.kill(os.getpid(), signal.SIGTERM); "
        "print(launcher.main([]), flush=True)"
    )

    # When: the launcher receives the termination signal in a child process.
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )

    # Then: main regains control so provider cleanup can finish and classifies 143.
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "143"


def test_non_loopback_host_is_rejected_before_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    launcher = _launcher()
    runtime_calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        launcher,
        "_run_server",
        lambda host, port: runtime_calls.append((host, port)),
    )

    # Given: a public bind address.
    # When: CLI parsing runs.
    with pytest.raises(SystemExit) as raised:
        launcher.main(["--host", "0.0.0.0", "--port", "8767"])

    # Then: argparse returns its classified usage code before runtime imports/builds.
    assert raised.value.code == 2
    assert runtime_calls == []


@pytest.mark.parametrize(
    ("missing", "component"),
    [
        ("python", "provider_python"),
        ("sidecar", "sidecar_script"),
        ("model", "model_cache"),
    ],
)
def test_preflight_classifies_missing_local_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    missing: str,
    component: str,
) -> None:
    launcher = _launcher()
    provider_python = tmp_path / "voice-python"
    sidecar_script = tmp_path / "voice-sidecar.py"
    model_path = tmp_path / "qwen-snapshot"
    if missing != "python":
        provider_python.write_text("#!/bin/sh\n", encoding="utf-8")
        provider_python.chmod(0o700)
    if missing != "sidecar":
        sidecar_script.write_text("# local sidecar\n", encoding="utf-8")
    if missing != "model":
        model_path.mkdir()
    monkeypatch.setenv("VOICE_PROVIDER_PYTHON", str(provider_python))
    monkeypatch.setenv("VOICE_SIDECAR_SCRIPT", str(sidecar_script))
    monkeypatch.setenv("VOICE_STT_PROVIDER", "qwen3-asr-0.6b-8bit")
    if missing == "model":
        monkeypatch.delenv("VOICE_MODEL_PATH", raising=False)
    else:
        monkeypatch.setenv("VOICE_MODEL_PATH", str(model_path))

    # Given: exactly one required local runtime component is absent.
    # When: preflight runs without importing the provider.
    with pytest.raises(launcher.LauncherPreflightError) as raised:
        launcher._preflight_local_runtime()

    # Then: the missing component is classified for a stable nonzero exit.
    assert raised.value.component == component


def test_provider_is_built_installed_closed_and_restored_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    launcher = _launcher()
    from app import voice_api, voice_provider
    from app.main import app
    from app.voice_contracts import (
        UnavailableSynthesisProvider,
        UnavailableTranscriptionProvider,
    )

    class FakeProvider:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    provider = FakeProvider()
    transcription_sentinel = UnavailableTranscriptionProvider()
    synthesis_sentinel = UnavailableSynthesisProvider()
    monkeypatch.setattr(voice_api, "transcription_provider", transcription_sentinel)
    monkeypatch.setattr(voice_api, "synthesis_provider", synthesis_sentinel)
    monkeypatch.setattr(launcher, "_preflight_local_runtime", lambda: None)
    monkeypatch.setattr(launcher, "_probe_local_provider", lambda _provider: None)
    monkeypatch.chdir(tmp_path)
    build_calls: list[None] = []

    def build_provider() -> FakeProvider:
        build_calls.append(None)
        return provider

    observed: list[tuple[bool, bool, str, int, Path]] = []

    def run_uvicorn(app_object, *, host: str, port: int) -> None:
        observed.append(
            (
                app_object is app,
                voice_api.transcription_provider is voice_api.synthesis_provider is provider,
                host,
                port,
                Path.cwd(),
            )
        )

    monkeypatch.setattr(voice_provider, "build_local_voice_provider", build_provider)
    monkeypatch.setattr("uvicorn.run", run_uvicorn)

    # Given: unavailable sentinels and a fake local provider.
    # When: the server exits normally.
    result = launcher.main([])

    # Then: one provider served both APIs, closed once, and exact sentinels returned.
    assert result == 0
    assert build_calls == [None]
    assert observed == [(True, True, "127.0.0.1", 8767, REPO_ROOT)]
    assert provider.close_calls == 1
    assert voice_api.transcription_provider is transcription_sentinel
    assert voice_api.synthesis_provider is synthesis_sentinel


@pytest.mark.parametrize(
    ("failure", "exit_code"),
    [(ServerFailure(), 1), (KeyboardInterrupt(), 130)],
)
def test_exception_closes_provider_restores_sentinels_and_returns_classified_code(
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
    exit_code: int,
) -> None:
    launcher = _launcher()
    from app import voice_api, voice_provider
    from app.voice_contracts import (
        UnavailableSynthesisProvider,
        UnavailableTranscriptionProvider,
    )

    class FakeProvider:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    provider = FakeProvider()
    transcription_sentinel = UnavailableTranscriptionProvider()
    synthesis_sentinel = UnavailableSynthesisProvider()
    monkeypatch.setattr(voice_api, "transcription_provider", transcription_sentinel)
    monkeypatch.setattr(voice_api, "synthesis_provider", synthesis_sentinel)
    monkeypatch.setattr(launcher, "_preflight_local_runtime", lambda: None)
    monkeypatch.setattr(launcher, "_probe_local_provider", lambda _provider: None)
    monkeypatch.setattr(voice_provider, "build_local_voice_provider", lambda: provider)

    def fail_uvicorn(*_args, **_kwargs) -> None:
        raise failure

    monkeypatch.setattr("uvicorn.run", fail_uvicorn)

    # Given: uvicorn raises after provider installation.
    # When: the launcher handles the top-level runtime failure.
    result = launcher.main([])

    # Then: cleanup still runs and the CLI reports a classified runtime failure.
    assert result == exit_code
    assert provider.close_calls == 1
    assert voice_api.transcription_provider is transcription_sentinel
    assert voice_api.synthesis_provider is synthesis_sentinel


def test_readiness_probe_exercises_both_directions_and_classifies_failure() -> None:
    launcher = _launcher()

    class RecordingProvider:
        def __init__(self, *, fail_synthesis: bool = False) -> None:
            self.calls: list[str] = []
            self.fail_synthesis = fail_synthesis

        def transcribe(self, path: Path, content_type: str) -> object:
            assert path == launcher.VOICE_PROBE_AUDIO
            assert content_type == "audio/wav"
            self.calls.append("transcribe")
            return object()

        def synthesize(self, text: str) -> object:
            assert text == "음성 기능 준비 확인"
            self.calls.append("synthesize")
            if self.fail_synthesis:
                raise OSError("tts unavailable")
            return object()

    healthy = RecordingProvider()
    launcher._probe_local_provider(healthy)
    assert healthy.calls == ["transcribe", "synthesize"]

    failing = RecordingProvider(fail_synthesis=True)
    with pytest.raises(launcher.LauncherPreflightError) as raised:
        launcher._probe_local_provider(failing)
    assert failing.calls == ["transcribe", "synthesize"]
    assert raised.value.component == "provider_readiness"


def test_readiness_probe_failure_closes_provider_before_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launcher = _launcher()
    from app import voice_provider

    class FakeProvider:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    provider = FakeProvider()
    failure = launcher.LauncherPreflightError(
        component="provider_readiness",
        location=launcher.VOICE_PROBE_AUDIO,
    )
    uvicorn_calls: list[None] = []

    monkeypatch.setattr(launcher, "_preflight_local_runtime", lambda: None)
    monkeypatch.setattr(
        launcher,
        "_probe_local_provider",
        lambda _provider: (_ for _ in ()).throw(failure),
    )
    monkeypatch.setattr(voice_provider, "build_local_voice_provider", lambda: provider)
    monkeypatch.setattr("uvicorn.run", lambda *_args, **_kwargs: uvicorn_calls.append(None))

    assert launcher.main([]) == 3
    assert provider.close_calls == 1
    assert uvicorn_calls == []


def test_profile_environment_is_forwarded_without_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launcher = _launcher()
    from app import voice_provider

    class FakeProvider:
        def close(self) -> None:
            return

    expected = {
        "VOICE_PROVIDER_PYTHON": "/custom/voice-python",
        "VOICE_SIDECAR_SCRIPT": "/custom/voice-sidecar.py",
        "VOICE_STT_PROVIDER": "whisper.cpp",
        "VOICE_WHISPER_CPP_MODEL": "/custom/model.ggml",
        "VOICE_TTS_VOICE": "Kyoko",
        "VOICE_TEMP_ROOT": "/custom/voice-temp",
    }
    for key, value in expected.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(launcher, "_preflight_local_runtime", lambda: None)
    monkeypatch.setattr(launcher, "_probe_local_provider", lambda _provider: None)
    forwarded: list[dict[str, str]] = []

    def build_provider() -> FakeProvider:
        forwarded.append({key: os.environ[key] for key in expected})
        forwarded[-1]["VOICE_ENABLED"] = os.environ["VOICE_ENABLED"]
        forwarded[-1]["VOICE_NETWORK_DENY"] = os.environ["VOICE_NETWORK_DENY"]
        return FakeProvider()

    monkeypatch.setattr(voice_provider, "build_local_voice_provider", build_provider)
    monkeypatch.setattr("uvicorn.run", lambda *_args, **_kwargs: None)

    # Given: an explicitly selected local profile.
    # When: the launcher builds the provider.
    result = launcher.main([])

    # Then: profile values are unchanged and local-only voice is enabled in-process.
    assert result == 0
    assert forwarded == [{**expected, "VOICE_ENABLED": "true", "VOICE_NETWORK_DENY": "1"}]


def test_preflight_failure_returns_three_before_runtime_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launcher = _launcher()
    failure = launcher.LauncherPreflightError(
        component="provider_python",
        location=Path("/missing/provider-python"),
    )
    monkeypatch.setattr(
        launcher,
        "_preflight_local_runtime",
        lambda: (_ for _ in ()).throw(failure),
    )

    # Given: local runtime preflight cannot find its configured Python.
    # When: the launcher starts.
    result = launcher.main([])

    # Then: it returns the stable preflight exit code without starting uvicorn.
    assert result == 3
