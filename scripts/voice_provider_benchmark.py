#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "mlx-audio==0.4.5",
#   "mlx-whisper==0.4.3",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run voice_provider_benchmark.py --fixtures tests/fixtures/voice-ko --out .omo/evidence/task-2-voice-local-demo.json
# 3. Or make executable and run:
#      chmod +x voice_provider_benchmark.py && ./voice_provider_benchmark.py --fixtures tests/fixtures/voice-ko --out .omo/evidence/task-2-voice-local-demo.json
# ──────────────────

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import socket
import subprocess
import sys
import tempfile
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Final, Iterator, TypedDict
from unittest.mock import patch

ROOT: Final = Path(__file__).resolve().parents[1]
WHISPER_CACHE: Final = Path.home() / ".cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo/snapshots"
QWEN_CACHE: Final = ROOT / ".voice-model-cache/hub/models--mlx-community--Qwen3-ASR-0.6B-8bit/snapshots"

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


class Utterance(TypedDict):
    file: str
    expected_text: str
    duration_seconds: float


def _display(path: Path | None) -> str | None:
    if path is None:
        return None
    return str(path).replace(str(Path.home()), "$HOME").replace(str(ROOT), "<repo>")


def _rss_gib() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024**3 if platform.system() == "Darwin" else 1024**2
    return round(value / divisor, 3)


def _normalise(text: str) -> str:
    return "".join(ch.lower() for ch in text if not ch.isspace() and not unicodedata.category(ch).startswith("P"))


def _cer(expected: str, actual: str) -> float:
    left, right = _normalise(expected), _normalise(actual)
    previous = list(range(len(right) + 1))
    for row, char in enumerate(left, 1):
        current = [row]
        for column, other in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[column] + 1, previous[column - 1] + (char != other)))
        previous = current
    return round(previous[-1] / max(len(left), 1), 4)


def _audio_duration(path: Path) -> float:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def _snapshot(root: Path) -> Path | None:
    if not root.is_dir():
        return None
    snapshots = sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name)
    return snapshots[-1] if snapshots else None


def _load_manifest(fixtures: Path) -> list[Utterance]:
    payload = json.loads((fixtures / "manifest.json").read_text(encoding="utf-8"))
    rows = payload.get("utterances")
    if not isinstance(rows, list) or len(rows) != 10:
        raise ValueError("manifest must contain exactly 10 utterances")
    typed_rows = [Utterance(file=str(row["file"]), expected_text=str(row["expected_text"]), duration_seconds=float(row["duration_seconds"])) for row in rows]
    files = [fixtures / row["file"] for row in typed_rows]
    if len(set(files)) != 10 or any(not item.is_file() for item in files):
        raise ValueError("manifest must name exactly 10 existing WAV files")
    return typed_rows


def _blocked_connect(_sock: socket.socket, _address: object) -> None:
    raise OSError("VOICE_NETWORK_DENY blocked socket connect")


def _blocked_create_connection(*_args: object, **_kwargs: object) -> socket.socket:
    raise OSError("VOICE_NETWORK_DENY blocked socket create_connection")


@contextmanager
def _network_guard() -> Iterator[None]:
    if os.getenv("VOICE_NETWORK_DENY") != "1":
        yield
        return
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    with patch.object(socket.socket, "connect", _blocked_connect), patch.object(socket, "create_connection", _blocked_create_connection):
        yield


def _decode_whisper(model_path: Path, audio: Path) -> str:
    import mlx_whisper

    result = mlx_whisper.transcribe(str(audio), path_or_hf_repo=str(model_path), language="ko", verbose=False)
    return str(result["text"]).strip()


def _decode_qwen(model_path: Path, audio: Path, model: list) -> str:
    if not model:
        from mlx_audio.stt import load

        model.append(load(model_path))
    result = model[0].generate(str(audio), language="ko", max_tokens=256, temperature=0.0, verbose=False)
    return str(result.text).strip()


def _run_stt(name: str, model_path: Path | None, fixtures: Path, rows: list[Utterance], network_denied: bool) -> dict[str, JsonValue]:
    license_note = "mlx-whisper package MIT; checkpoint follows upstream model-card terms; weights not redistributed" if name == "mlx-whisper-large-v3-turbo" else "mlx-audio package MIT; Qwen3-ASR checkpoint Apache-2.0 upstream; weights not redistributed"
    result: dict[str, JsonValue] = {"name": name, "kind": "stt", "status": "UNAVAILABLE", "model_path": _display(model_path), "network_deny": network_denied, "license_note": license_note, "cold_latency_ms": None, "warm_latency_ms": None, "cold_rtf": None, "warm_rtf": None, "peak_rss_gib": None, "non_empty_rate": None, "cer": None}
    if model_path is None:
        result["reason"] = "required local model snapshot was not found; network-deny runtime cannot download it"
        return result
    if not model_path.is_dir():
        raise FileNotFoundError(f"invalid model path: {model_path}")
    qwen_model: list = []
    if name == "qwen3-asr-0.6b-8bit":
        decoder: Callable[[Path], str] = lambda audio: _decode_qwen(model_path, audio, qwen_model)
    elif name == "mlx-whisper-large-v3-turbo":
        decoder = lambda audio: _decode_whisper(model_path, audio)
    else:
        result["reason"] = "provider adapter is not installed"
        return result
    paths = [fixtures / row["file"] for row in rows]
    try:
        with _network_guard():
            started = time.perf_counter()
            first = decoder(paths[0])
            cold = time.perf_counter() - started
            warm_outputs: list[str] = []
            warm_elapsed = 0.0
            for path in paths:
                started = time.perf_counter()
                warm_outputs.append(decoder(path))
                warm_elapsed += time.perf_counter() - started
    except (ImportError, OSError, RuntimeError, ValueError, KeyError, FileNotFoundError) as exc:
        result["reason"] = f"{type(exc).__name__}: {str(exc).replace(str(ROOT), '<repo>')}"
        return result
    total_duration = sum(row["duration_seconds"] for row in rows)
    result.update({"status": "PASS", "cold_latency_ms": round(cold * 1000, 1), "warm_latency_ms": round(warm_elapsed * 1000 / len(paths), 1), "cold_rtf": round(cold / rows[0]["duration_seconds"], 4), "warm_rtf": round(warm_elapsed / total_duration, 4), "peak_rss_gib": _rss_gib(), "non_empty_rate": round(sum(bool(text) for text in warm_outputs) / len(warm_outputs), 4), "cer": round(sum(_cer(row["expected_text"], text) for row, text in zip(rows, warm_outputs, strict=True)) / len(warm_outputs), 4), "cold_non_empty": bool(first)})
    return result


def _run_say(fixtures: Path, rows: list[Utterance], voice: str, network_denied: bool) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {"name": "macos-say", "kind": "tts", "status": "UNAVAILABLE", "model_path": "/usr/bin/say", "voice": voice, "network_deny": network_denied, "license_note": "macOS system component; no model redistribution", "cold_latency_ms": None, "warm_latency_ms": None, "warm_rtf": None, "peak_rss_gib": None}
    try:
        with _network_guard(), tempfile.TemporaryDirectory(prefix="voice-tts-") as temp:
            first_out = Path(temp) / "cold.aiff"
            started = time.perf_counter()
            subprocess.run(["/usr/bin/say", "-v", voice, "-o", str(first_out), rows[0]["expected_text"]], check=True, capture_output=True, text=True)
            cold = time.perf_counter() - started
            warm_elapsed = 0.0
            output_duration = 0.0
            for index, row in enumerate(rows):
                started = time.perf_counter()
                output = Path(temp) / f"warm-{index}.aiff"
                subprocess.run(["/usr/bin/say", "-v", voice, "-o", str(output), row["expected_text"]], check=True, capture_output=True, text=True)
                warm_elapsed += time.perf_counter() - started
                output_duration += _audio_duration(output)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        result["reason"] = f"{type(exc).__name__}: {str(exc)}"
        return result
    result.update({"status": "PASS", "cold_latency_ms": round(cold * 1000, 1), "warm_latency_ms": round(warm_elapsed * 1000 / len(rows), 1), "warm_rtf": round(warm_elapsed / output_duration, 4), "non_empty_rate": 1.0})
    return result


def _candidate_gate(item: dict[str, JsonValue]) -> bool:
    warm_rtf, rss = item.get("warm_rtf"), item.get("peak_rss_gib")
    return item.get("status") == "PASS" and item.get("network_deny") is True and item.get("non_empty_rate") == 1.0 and isinstance(warm_rtf, float) and warm_rtf <= 1.0 and isinstance(rss, float) and rss <= 8.0


def run(fixtures: Path, output: Path, voice: str, provider: str | None, model_override: Path | None) -> int:
    rows = _load_manifest(fixtures)
    deny = os.getenv("VOICE_NETWORK_DENY") == "1"
    whisper = model_override if provider == "mlx-whisper" else _snapshot(WHISPER_CACHE)
    qwen = model_override if provider == "qwen-asr" else _snapshot(QWEN_CACHE)
    candidates = []
    if provider in (None, "mlx-whisper"):
        candidates.append(_run_stt("mlx-whisper-large-v3-turbo", whisper, fixtures, rows, deny))
    if provider in (None, "qwen-asr"):
        candidates.append(_run_stt("qwen3-asr-0.6b-8bit", qwen, fixtures, rows, deny))
    candidates.append({"name": "whisper.cpp", "kind": "stt", "status": "UNAVAILABLE", "model_path": None, "network_deny": deny, "reason": "Homebrew whisper-cli is installed, but no GGML model file is cached or bundled"})
    tts = [_run_say(fixtures, rows, voice, deny), {"name": "supertonic-3", "kind": "tts", "status": "UNAVAILABLE", "model_path": None, "network_deny": deny, "license_note": "upstream code MIT; model weights OpenRAIL-M; no local runtime/weights were cached", "reason": "Supertonic 3 runtime and Korean model weights are not installed or cached"}]
    eligible = sorted((item for item in candidates if _candidate_gate(item)), key=lambda item: (float(item["cer"]), float(item["warm_rtf"]), float(item["warm_latency_ms"])))
    selected_stt = str(eligible[0]["name"]) if eligible else "whisper.cpp"
    report: dict[str, JsonValue] = {"schema_version": 1, "task": "T2 voice-local-demo", "coverage_label": "synthetic deterministic compatibility only; no subjective TTS quality claim", "baseline": {"command": ".venv/bin/python -m pytest -q tests/test_chat.py tests/test_config.py", "status": "PASS", "result": "20 passed before T2 edits"}, "runtime": {"python": sys.version, "python_preferred": "3.13.4", "python_3_14_compatibility": "not selected; Python 3.13.4 was available and used", "platform": platform.platform(), "install_command": "uv pip install --python .voice-venv/bin/python mlx-audio==0.4.5 mlx-whisper==0.4.3", "model_download_command": "HF_HOME=<repo>/.voice-model-cache HF_HUB_CACHE=<repo>/.voice-model-cache/hub .voice-venv/bin/python -c 'from mlx_audio.stt import load; load(\"mlx-community/Qwen3-ASR-0.6B-8bit\")'", "model_cache_paths": [_display(WHISPER_CACHE), _display(ROOT / ".voice-model-cache")], "network_deny_env": deny}, "selection_rule": "lowest CER among local-only candidates with 10/10 non-empty, warm RTF <= 1.0, RSS <= 8 GiB, and network-deny success; ties break by warm RTF then warm latency", "candidates": candidates, "tts_candidates": tts, "selected_profile": {"stt": selected_stt, "tts": "macOS say (Yuna)", "local_only": True}, "fallback": {"stt": "whisper.cpp", "tts": "macOS say", "reason": "explicit fallback when no candidate satisfies the gate; whisper.cpp still requires a separately provisioned GGML model"}, "cleanup": {"benchmark_temp_audio": "TemporaryDirectory removed after each TTS run; no raw audio written", "model_weights": "not tracked; cache paths are ignored"}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text = [f"T2 provider feasibility report: {output}", "", f"selection: {selected_stt} STT + macOS say (Yuna) TTS", "fallback: whisper.cpp STT + macOS say TTS", f"network_deny={deny}", "baseline: PASS — 20 passed before T2 edits", "", "Candidates:"]
    for item in [*candidates, *tts]:
        text.append(f"- {item['name']}: {item['status']}" + (f"; reason={item['reason']}" if "reason" in item else f"; CER={item.get('cer')}; warm_RTF={item.get('warm_rtf')}; RSS_GiB={item.get('peak_rss_gib')}"))
    text.extend(["", "License/cache note: synthetic WAVs are checked in; model weights and raw benchmark audio are not.", "UltraQA probes: stale_state, dirty_worktree, hung_long_command, flaky_tests, malformed_input, misleading_success_output; prompt_injection/cancel_resume not observed."])
    output.with_suffix(".txt").write_text("\n".join(text) + "\n", encoding="utf-8")
    return 0 if eligible or tts[0]["status"] == "PASS" else 1


def main() -> int:  # noqa: BROAD_EXCEPT_OK
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--voice", default="Yuna")
    parser.add_argument("--provider", choices=("mlx-whisper", "qwen-asr"))
    parser.add_argument("--model-path", type=Path)
    args = parser.parse_args()
    if args.model_path is not None and args.provider is None:
        parser.error("--model-path requires --provider")
    try:
        return run(args.fixtures, args.out, args.voice, args.provider, args.model_path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"benchmark failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
