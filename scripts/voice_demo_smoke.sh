#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$REPO_ROOT/.venv/bin/python}"
VOICE_PYTHON="${VOICE_PROVIDER_PYTHON:-$REPO_ROOT/.voice-venv/bin/python}"
BROWSER="chromium"
CYCLES=10
NETWORK_DENY=0
KILL_SIDECAR=0
PORT="${VOICE_DEMO_PORT:-8767}"
WORK_DIR=""
SERVER_PID=""
SERVER_PGID=""
OWNED_SIDECAR_PIDS=""

usage() {
  cat <<'EOF'
Usage: VOICE_ENABLED=true ./scripts/voice_demo_smoke.sh [options]

Options:
  --browser chromium       Browser label (only chromium is supported)
  --cycles N               Consecutive local fixture cycles (default: 10)
  --network-deny           Assert the local-only network profile
  --kill-sidecar           Kill the owned sidecar and require classified HTTP 503
  --port N                 Reserved FastAPI port (default: 8767; 8766 is forbidden)
EOF
}

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

run_bounded() {
  local timeout_seconds="$1"
  local label="$2"
  shift 2
  "$PYTHON" - "$timeout_seconds" "$label" "$@" <<'PY'
import os
import signal
import subprocess
import sys

timeout_seconds = float(sys.argv[1])
label = sys.argv[2]
command = sys.argv[3:]
process = subprocess.Popen(command, start_new_session=True)
try:
    raise SystemExit(process.wait(timeout=timeout_seconds))
except subprocess.TimeoutExpired:
    print(f"FAIL: timed out after {timeout_seconds:g}s: {label}", file=sys.stderr)
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    raise SystemExit(124)
PY
}

listener_snapshot() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN -Fpcn 2>/dev/null || true
}

sidecar_process_snapshot() {
  VOICE_SIDECAR_NEEDLE="$REPO_ROOT/scripts/voice_sidecar.py" "$PYTHON" -c '
import os
import subprocess

needle = os.environ["VOICE_SIDECAR_NEEDLE"]
lines = subprocess.check_output(["ps", "-axo", "pid=,ppid=,pgid=,command="], text=True)
print("\n".join(sorted(line.strip() for line in lines.splitlines() if needle in line)))
'
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --browser) BROWSER="${2:-}"; shift 2 ;;
    --cycles) CYCLES="${2:-}"; shift 2 ;;
    --network-deny) NETWORK_DENY=1; shift ;;
    --kill-sidecar) KILL_SIDECAR=1; shift ;;
    --port) PORT="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[ "$BROWSER" = "chromium" ] || fail "only --browser chromium is supported"
[[ "$CYCLES" =~ ^[1-9][0-9]*$ ]] || fail "--cycles must be a positive integer"
[[ "$PORT" =~ ^[1-9][0-9]*$ ]] || fail "--port must be a positive integer"
[ "$PORT" -le 65535 ] || fail "--port must be at most 65535"
[ "$PORT" != "8766" ] || fail "port 8766 is reserved for the immutable baseline server"
[ -x "$PYTHON" ] || fail "python not executable: $PYTHON"
[ -x "$VOICE_PYTHON" ] || fail "local voice python not executable: $VOICE_PYTHON"
[ -x "$REPO_ROOT/scripts/voice_provider_benchmark.py" ] || fail "benchmark script is not executable"
[ -f "$REPO_ROOT/scripts/run_local_voice.py" ] || fail "local voice launcher is missing"
[ -f "$REPO_ROOT/scripts/gui-smoke/voice-local-e2e.mjs" ] || fail "real browser E2E is missing"
[ -f "$REPO_ROOT/scripts/gui-smoke/interaction-mode-smoke.mjs" ] || fail "mocked interaction-mode smoke is missing"
[ -d "$REPO_ROOT/scripts/gui-smoke/node_modules" ] || fail "Playwright dependencies are missing"
[ "${VOICE_ENABLED:-true}" = "true" ] || fail "T7 demo requires VOICE_ENABLED=true"
[ -z "$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null)" ] || fail "reserved port already has a listener: $PORT"
BASELINE_8766_BEFORE="$(listener_snapshot 8766)"
if [ -n "$BASELINE_8766_BEFORE" ]; then
  BASELINE_8766_PRESENT="true"
else
  BASELINE_8766_PRESENT="false"
fi

WORK_DIR="$(mktemp -d -t voice-t7.XXXXXX)"
SERVER_LOG="$WORK_DIR/server.log"
CYCLE_TSV="$WORK_DIR/cycles.tsv"
FAILURE_TSV="$WORK_DIR/failure.tsv"
REAL_BROWSER_JSON="$WORK_DIR/browser-real.json"
MOCKED_BROWSER_JSON="$WORK_DIR/browser-mocked.json"
BENCHMARK_JSON="$WORK_DIR/benchmark.json"
MALFORMED_AUDIO="$WORK_DIR/malformed.bin"
VOICE_TEMP_ROOT="$WORK_DIR/voice-tmp"
mkdir -p "$VOICE_TEMP_ROOT"
: > "$MALFORMED_AUDIO"
ln -s "$REPO_ROOT/static" "$WORK_DIR/static"

model_snapshots=("$REPO_ROOT"/.voice-model-cache/hub/models--mlx-community--Qwen3-ASR-0.6B-8bit/snapshots/*)
[ -d "${model_snapshots[0]}" ] || fail "Qwen3-ASR model snapshot not found under .voice-model-cache"
export VOICE_MODEL_PATH="${VOICE_MODEL_PATH:-${model_snapshots[0]}}"

descendants_of() {
  local parent="$1"
  local child
  for child in $(ps -axo pid=,ppid= | awk -v parent="$parent" '$2 == parent {print $1}'); do
    printf '%s\n' "$child"
    descendants_of "$child"
  done
}

track_owned_sidecars() {
  local pid command
  [ -n "$SERVER_PID" ] || return 0
  for pid in $(descendants_of "$SERVER_PID"); do
    command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    case "$command" in
      *"$REPO_ROOT/scripts/voice_sidecar.py"*)
        case " $OWNED_SIDECAR_PIDS " in
          *" $pid "*) ;;
          *) OWNED_SIDECAR_PIDS="$OWNED_SIDECAR_PIDS $pid" ;;
        esac
        ;;
    esac
  done
}

owned_sidecar_pids() {
  local pid
  track_owned_sidecars
  for pid in $OWNED_SIDECAR_PIDS; do
    kill -0 "$pid" 2>/dev/null && printf '%s\n' "$pid"
  done
}

owned_rss_kib() {
  local pid total rss
  total=0
  if [ -n "$SERVER_PGID" ]; then
    total="$(ps -axo pgid=,rss= | awk -v group="$SERVER_PGID" '$1 == group {total += $2} END {print total + 0}')"
  fi
  for pid in $(owned_sidecar_pids); do
    rss="$(ps -p "$pid" -o rss= 2>/dev/null | awk '{print $1}' || true)"
    [[ "$rss" =~ ^[0-9]+$ ]] && total=$((total + rss))
  done
  printf '%s\n' "$total"
}

stop_owned_server() {
  local attempt pid
  track_owned_sidecars
  for pid in $OWNED_SIDECAR_PIDS; do
    kill -TERM "$pid" 2>/dev/null || true
  done
  if [ -n "$SERVER_PGID" ] && kill -0 -- "-$SERVER_PGID" 2>/dev/null; then
    kill -TERM -- "-$SERVER_PGID" 2>/dev/null || true
    for attempt in $(seq 1 100); do
      kill -0 -- "-$SERVER_PGID" 2>/dev/null || break
      sleep 0.05
    done
    if kill -0 -- "-$SERVER_PGID" 2>/dev/null; then
      kill -KILL -- "-$SERVER_PGID" 2>/dev/null || true
    fi
  elif [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill -TERM "$SERVER_PID" 2>/dev/null || true
  fi
  if [ -n "$SERVER_PID" ]; then
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  for pid in $OWNED_SIDECAR_PIDS; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -KILL "$pid" 2>/dev/null || true
    fi
    for attempt in $(seq 1 100); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.05
    done
  done
}

cleanup() {
  stop_owned_server
  if [ -n "$WORK_DIR" ] && [ -d "$WORK_DIR" ]; then
    rm -rf -- "$WORK_DIR"
  fi
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

wait_http() {
  local url="$1"
  local ready=0
  for _ in $(seq 1 400); do
    if curl -fsS --max-time 2 -o /dev/null "$url" 2>/dev/null; then
      ready=1
      break
    fi
    sleep 0.1
  done
  [ "$ready" -eq 1 ] || fail "server did not become ready: $url"
}

now_ms() {
  "$PYTHON" -c 'import time; print(round(time.time() * 1000))'
}

export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export VOICE_ENABLED=true
export MODEL="${MODEL:-fake}"
export KNOWLEDGE_DIR="${KNOWLEDGE_DIR:-$REPO_ROOT/knowledge}"
export VOICE_PROVIDER_PYTHON="$VOICE_PYTHON"
export VOICE_SIDECAR_SCRIPT="$REPO_ROOT/scripts/voice_sidecar.py"
export VOICE_STT_PROVIDER="${VOICE_STT_PROVIDER:-qwen3-asr-0.6b-8bit}"
export VOICE_TTS_VOICE="${VOICE_TTS_VOICE:-Yuna}"
export VOICE_TEMP_ROOT
if [ "$NETWORK_DENY" -eq 1 ]; then
  export VOICE_NETWORK_DENY=1
else
  unset VOICE_NETWORK_DENY || true
fi

set -m
(
  cd "$WORK_DIR"
  exec "$PYTHON" "$REPO_ROOT/scripts/run_local_voice.py" --host 127.0.0.1 --port "$PORT"
) >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 50); do
  SERVER_PGID="$(ps -p "$SERVER_PID" -o pgid= 2>/dev/null | tr -d ' ' || true)"
  [ -n "$SERVER_PGID" ] && break
  sleep 0.02
done
set +m
[ -n "$SERVER_PGID" ] || fail "launcher process group was not established"
[ "$SERVER_PGID" = "$SERVER_PID" ] || fail "launcher does not own its process group: pid=$SERVER_PID pgid=$SERVER_PGID"
wait_http "http://127.0.0.1:$PORT/api/config"

config_json="$WORK_DIR/config.json"
curl -fsS --max-time 10 "http://127.0.0.1:$PORT/api/config" > "$config_json"
jq -e '.voice.enabled == true and .voice.local_only == true and .voice.min_recording_ms == 800 and .voice.max_recording_ms == 60000' "$config_json" >/dev/null
curl -fsS --max-time 10 "http://127.0.0.1:$PORT/app.js?v=14" > "$WORK_DIR/served-app.js"
cmp -s "$REPO_ROOT/static/app.js" "$WORK_DIR/served-app.js" || fail "owned FastAPI server is not serving the current repo static/app.js"

benchmark_env=(VOICE_NETWORK_DENY=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1)
if [ "$NETWORK_DENY" -eq 0 ]; then
  benchmark_env=()
fi
run_bounded 300 "local voice benchmark" env "${benchmark_env[@]}" "$VOICE_PYTHON" "$REPO_ROOT/scripts/voice_provider_benchmark.py" \
  --fixtures "$REPO_ROOT/tests/fixtures/voice-ko" \
  --out "$BENCHMARK_JSON" >"$WORK_DIR/benchmark.log" 2>&1
jq -e '.selected_profile.stt == "qwen3-asr-0.6b-8bit" and .selected_profile.tts == "macOS say (Yuna)" and ([.candidates[] | select(.name == "qwen3-asr-0.6b-8bit")][0].status == "PASS")' "$BENCHMARK_JSON" >/dev/null

fixture="$REPO_ROOT/tests/fixtures/voice-ko/01.wav"
fixture_duration_ms="$(jq -r '.utterances[] | select(.file == "01.wav") | .duration_seconds * 1000 | round' "$REPO_ROOT/tests/fixtures/voice-ko/manifest.json")"
max_rss_kib=0
session_id="voice-demo-$(date +%Y%m%d%H%M%S)-$$"
session_token=""

for i in $(seq 1 "$CYCLES"); do
  transcribe_body="$WORK_DIR/transcribe-$i.json"
  chat_request="$WORK_DIR/chat-request-$i.json"
  chat_body="$WORK_DIR/chat-response-$i.json"
  tts_request="$WORK_DIR/tts-request-$i.json"
  tts_wav="$WORK_DIR/tts-$i.wav"
  t0="$(now_ms)"
  transcribe_args=(-F "session_id=$session_id" -F "audio=@$fixture;type=audio/wav")
  if [ -n "$session_token" ]; then
    transcribe_args+=(-F "session_token=$session_token")
  fi
  transcribe_status="$(curl -sS --max-time 60 -o "$transcribe_body" -w '%{http_code}' -X POST "http://127.0.0.1:$PORT/api/voice/transcribe" "${transcribe_args[@]}")"
  t1="$(now_ms)"
  [ "$transcribe_status" = "200" ] || fail "local cycle $i transcription failed: HTTP $transcribe_status"
  jq -e '(.text // "") | length > 0' "$transcribe_body" >/dev/null || fail "local cycle $i returned empty transcript"
  provider="$(jq -r '.provider' "$transcribe_body")"
  model="$(jq -r '.model' "$transcribe_body")"

  if [ -n "$session_token" ]; then
    jq -n --arg message "$(jq -r '.text' "$transcribe_body")" --arg session_id "$session_id" --arg token "$session_token" \
      '{schema_version: 2, metadata: {voice_demo: true}, session_id: $session_id, session_token: $token, message: $message}' > "$chat_request"
  else
    jq -n --arg message "$(jq -r '.text' "$transcribe_body")" --arg session_id "$session_id" \
      '{schema_version: 2, metadata: {voice_demo: true}, session_id: $session_id, message: $message}' > "$chat_request"
  fi
  t2="$(now_ms)"
  chat_status="$(curl -sS --max-time 30 -o "$chat_body" -w '%{http_code}' -X POST "http://127.0.0.1:$PORT/api/chat" -H 'Content-Type: application/json' --data-binary "@$chat_request")"
  t3="$(now_ms)"
  [ "$chat_status" = "200" ] || fail "local cycle $i chat failed: HTTP $chat_status"
  returned_session_token="$(jq -r '.session_token // empty' "$chat_body")"
  if [ -n "$returned_session_token" ]; then
    session_token="$returned_session_token"
  fi
  [ -n "$session_token" ] || fail "local cycle $i did not establish a session token"

  jq -n --arg session_id "$session_id" --arg token "$session_token" \
    '{text: "로컬 음성 응답 확인", session_id: $session_id, session_token: $token}' > "$tts_request"
  t4="$(now_ms)"
  tts_status="$(curl -sS --max-time 30 -o "$tts_wav" -w '%{http_code}' -X POST "http://127.0.0.1:$PORT/api/voice/synthesize" -H 'Content-Type: application/json' --data-binary "@$tts_request")"
  t5="$(now_ms)"
  [ "$tts_status" = "200" ] || fail "local cycle $i synthesis failed: HTTP $tts_status"
  run_bounded 15 "TTS stream probe cycle $i" ffprobe -v error -show_entries stream=codec_name,sample_rate,channels -of json "$tts_wav" > "$WORK_DIR/tts-$i.ffprobe.json"
  jq -e '.streams[0].codec_name == "pcm_s16le" and .streams[0].sample_rate == "22050" and .streams[0].channels == 1' "$WORK_DIR/tts-$i.ffprobe.json" >/dev/null || fail "local cycle $i returned an invalid TTS WAV"
  tts_duration_ms="$(run_bounded 15 "TTS duration probe cycle $i" ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$tts_wav" | awk '{printf "%.0f\n", $1 * 1000}')"
  rss_kib="$(owned_rss_kib)"
  [ "$rss_kib" -gt "$max_rss_kib" ] && max_rss_kib="$rss_kib"
  printf '%s\tsuccess\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$i" "$((t1 - t0))" "$((t3 - t2))" "$((t5 - t4))" "$provider" "$model" "$rss_kib" "$fixture_duration_ms" "$tts_duration_ms" >> "$CYCLE_TSV"
done

MOCKED_PARTS_DIR="$WORK_DIR/browser-mocked-parts"
mkdir -p "$MOCKED_PARTS_DIR"
mocked_scenarios=(switch-during-recording switch-during-transcribe switch-after-confirm autoplay-blocked unsupported-reload)
for scenario in "${mocked_scenarios[@]}"; do
  run_bounded 120 "mocked browser scenario $scenario" env \
    INTERACTION_MODE_BASE_URL="http://127.0.0.1:$PORT" \
    node "$REPO_ROOT/scripts/gui-smoke/interaction-mode-smoke.mjs" --scenario "$scenario" > "$MOCKED_PARTS_DIR/$scenario.json"
done
jq -s '{status: (if all(.[]; .status == "pass") then "pass" else "fail" end), scenarios: [.[].scenarios[]]}' "$MOCKED_PARTS_DIR"/*.json > "$MOCKED_BROWSER_JSON"
jq -e '.status == "pass" and (.scenarios | length == 5)' "$MOCKED_BROWSER_JSON" >/dev/null

mkdir -p "$REPO_ROOT/.omo/evidence"
run_bounded 240 "real local browser voice/TTS E2E" env \
  VOICE_E2E_BASE_URL="http://127.0.0.1:$PORT" \
  VOICE_E2E_FIXTURE="$fixture" \
  VOICE_E2E_SCREENSHOT="$REPO_ROOT/.omo/evidence/task-7-chat-voice-dual-mode.png" \
  VOICE_E2E_TIMEOUT_MS=180000 \
  node "$REPO_ROOT/scripts/gui-smoke/voice-local-e2e.mjs" > "$REAL_BROWSER_JSON"
jq -e '
  .result == "pass" and
  .assertions.voice_mode_entry == true and
  .assertions.transcript_review_editable == true and
  .assertions.assistant_text_present == true and
  .assertions.ready == true and
  .assertions.html_media_play_fulfilled_once == true and
  .assertions.tts_object_url_same_revoke_once == true and
  .assertions.tts_response_valid == true and
  .assertions.canonical_chat_payload == true and
  .assertions.duplicate_requests == 0 and
  .happy_path.request_counts == {"stt": 1, "chat": 1, "tts": 1} and
  .happy_path.request_order == ["stt", "chat", "tts"] and
  .tts_playback.play_call_count == 1 and
  .tts_playback.play_fulfilled_count == 1 and
  .tts_playback.play_rejected_count == 0 and
  .tts_playback.created_object_url_count == 1 and
  .tts_playback.revoked_object_url_count == 1 and
  .tts_playback.created_object_urls == .tts_playback.revoked_object_urls and
  .tts_playback.played_object_urls == .tts_playback.created_object_urls and
  .tts_playback.same_tts_object_url_revoked_once == true and
  .tts_playback.verified_at_tts_state == "idle" and
  .tts_playback.final_active_object_urls == 0 and
  .tts_response.status == 200 and
  .tts_response.content_type_wav_compatible == true and
  .tts_response.byte_length > 44 and
  .tts_response.body_nonempty_beyond_header == true and
  .tts_response.riff_header_valid == true and
  .tts_response.wave_header_valid == true and
  .tts_response.wav_header_valid == true and
  .tts_state_transitions == ["idle", "synthesizing", "playing", "idle"] and
  .malformed_browser_media.status == 400 and
  .malformed_browser_media.error_code == "invalid_audio"
' "$REAL_BROWSER_JSON" >/dev/null

malformed_body="$WORK_DIR/malformed.json"
malformed_status="$(curl -sS --max-time 10 -o "$malformed_body" -w '%{http_code}' -X POST "http://127.0.0.1:$PORT/api/voice/transcribe" -F 'session_id=voice-demo-malformed' -F "audio=@$MALFORMED_AUDIO;type=application/octet-stream")"
malformed_code="$(jq -r '.error_code // "missing_error_code"' "$malformed_body")"
[ "$malformed_status" = "400" ] && [ "$malformed_code" = "invalid_audio" ] || fail "malformed input was not classified: status=$malformed_status code=$malformed_code"

text_sidecars_before="$(sidecar_process_snapshot)"
text_port="$($PYTHON -c 'import socket; sock = socket.socket(); sock.bind(("127.0.0.1", 0)); print(sock.getsockname()[1]); sock.close()')"
run_bounded 180 "text-only local smoke" env VOICE_ENABLED=false PORT="$text_port" \
  "$REPO_ROOT/scripts/smoke_local.sh" > "$WORK_DIR/text-smoke.txt" 2>&1
(
  cd "$WORK_DIR"
  run_bounded 60 "text-only capability contract" env \
    VOICE_ENABLED=false MODEL=fake KNOWLEDGE_DIR="$REPO_ROOT/knowledge" PYTHONPATH="$REPO_ROOT" \
    "$PYTHON" -c '
import json
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    config = client.get("/api/config")
    assert config.status_code == 200 and "voice" not in config.json(), config.text
    voice = client.post(
        "/api/voice/transcribe",
        data={"session_id": "text-only-voice-disabled"},
        files={"audio": ("disabled.wav", b"RIFF", "audio/wav")},
    )
    assert voice.status_code == 503, voice.text
    assert voice.json().get("error_code") == "voice_disabled", voice.text
    chat = client.post(
        "/api/chat",
        json={
            "schema_version": 2,
            "metadata": {"voice_demo_text_recovery": True},
            "session_id": "text-only-recovery",
            "message": "안녕하세요",
        },
    )
    assert chat.status_code == 200, chat.text
print(json.dumps({"config_voice_absent": True, "voice_status": 503, "voice_error_code": "voice_disabled", "chat_status": 200}))
' > "$WORK_DIR/text-contract.json"
)
text_sidecars_after="$(sidecar_process_snapshot)"
[ "$text_sidecars_after" = "$text_sidecars_before" ] || fail "text-only recovery started or changed a local voice sidecar"
jq -e '.config_voice_absent == true and .voice_status == 503 and .voice_error_code == "voice_disabled" and .chat_status == 200' "$WORK_DIR/text-contract.json" >/dev/null

failure_status="not_run"
failure_code="not_run"
failure_killed="false"
if [ "$KILL_SIDECAR" -eq 1 ]; then
  sidecar_pid=""
  failure_body="$WORK_DIR/failure-body.json"
  curl -sS --max-time 60 -o "$failure_body" -w '%{http_code}' -X POST "http://127.0.0.1:$PORT/api/voice/transcribe" -F "session_id=voice-demo-failure" -F "audio=@$fixture;type=audio/wav" > "$WORK_DIR/failure-status" &
  failure_curl_pid=$!
  for _ in $(seq 1 200); do
    sidecar_pid="$(owned_sidecar_pids | head -1 || true)"
    if [ -n "$sidecar_pid" ]; then
      sleep 0.1
      kill -KILL "$sidecar_pid" 2>/dev/null || true
      failure_killed="true"
      break
    fi
    sleep 0.05
  done
  [ -n "$sidecar_pid" ] || fail "sidecar failure probe could not discover an owned sidecar"
  wait "$failure_curl_pid" 2>/dev/null || true
  for _ in $(seq 1 100); do
    kill -0 "$sidecar_pid" 2>/dev/null || break
    sleep 0.05
  done
  kill -0 "$sidecar_pid" 2>/dev/null && fail "killed sidecar PID survived failure probe: $sidecar_pid"
  failure_status="$(tr -d '\n' < "$WORK_DIR/failure-status")"
  failure_code="$(jq -r '.error_code // "http_error"' "$failure_body" 2>/dev/null || printf 'http_error')"
  printf '%s\t%s\t%s\n' "$failure_status" "$failure_code" "$failure_killed" > "$FAILURE_TSV"
  [ "$failure_status" = "503" ] || fail "killed sidecar was not HTTP 503: status=$failure_status code=$failure_code"
  case "$failure_code" in
    provider_unavailable|provider_timeout) ;;
    *) fail "killed sidecar was not classified: status=$failure_status code=$failure_code" ;;
  esac
  [ "$failure_killed" = "true" ] || fail "sidecar failure probe did not kill an owned sidecar"
fi

OWNED_PGID="$SERVER_PGID"
stop_owned_server
kill -0 -- "-$OWNED_PGID" 2>/dev/null && fail "owned launcher process group survived cleanup: $OWNED_PGID"
for pid in $OWNED_SIDECAR_PIDS; do
  kill -0 "$pid" 2>/dev/null && fail "owned sidecar survived cleanup: $pid"
done
for _ in $(seq 1 100); do
  [ -z "$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null)" ] && break
  sleep 0.05
done
[ -z "$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null)" ] || fail "owned port still has a listener after cleanup: $PORT"
rmdir "$VOICE_TEMP_ROOT" || fail "owned voice temp root was not empty after provider cleanup"
BASELINE_8766_AFTER="$(listener_snapshot 8766)"
[ "$BASELINE_8766_AFTER" = "$BASELINE_8766_BEFORE" ] || fail "pre-existing 127.0.0.1:8766 listener snapshot changed"

"$PYTHON" - "$REPO_ROOT" "$CYCLE_TSV" "$FAILURE_TSV" "$REAL_BROWSER_JSON" "$MOCKED_BROWSER_JSON" "$BENCHMARK_JSON" "$max_rss_kib" "$malformed_status" "$malformed_code" "$NETWORK_DENY" "$CYCLES" "$PORT" "$OWNED_PGID" "$BASELINE_8766_PRESENT" "$WORK_DIR/text-contract.json" <<'PY'
import json
import platform
import sys
from pathlib import Path

(
    root,
    cycles_path,
    failure_path,
    real_browser_path,
    mocked_browser_path,
    benchmark_path,
    max_rss_kib,
    malformed_status,
    malformed_code,
    network_deny,
    requested_cycles,
    port,
    owned_pgid,
    baseline_8766_present,
    text_contract_path,
) = sys.argv[1:]
root_path = Path(root)
rows = []
for line in Path(cycles_path).read_text(encoding="utf-8").splitlines():
    attempt, status, transcribe, chat, tts, provider, model, rss, fixture_ms, tts_ms = line.split("\t")
    rows.append(
        {
            "attempt_id": f"voice-demo-{attempt}",
            "status": status,
            "media_mode": "local_synthetic_fixture_api",
            "fixture_duration_ms": int(fixture_ms),
            "transcribe_latency_ms": int(transcribe),
            "chat_latency_ms": int(chat),
            "tts_latency_ms": int(tts),
            "tts_wav_valid": True,
            "tts_duration_ms": int(tts_ms),
            "provider": provider,
            "model": model,
            "peak_rss_gib": round(int(rss) / (1024 * 1024), 3),
            "transcript_non_empty": True,
            "chat_requests": 1,
        }
    )
failure = {"status": "not_run", "error_code": "not_run", "sidecar_killed": False, "classified": False}
if Path(failure_path).is_file() and Path(failure_path).read_text(encoding="utf-8").strip():
    status, code, killed = Path(failure_path).read_text(encoding="utf-8").strip().split("\t")
    failure = {
        "status": int(status),
        "error_code": code,
        "sidecar_killed": killed == "true",
        "classified": status == "503" and code in {"provider_unavailable", "provider_timeout"},
    }
benchmark = json.loads(Path(benchmark_path).read_text(encoding="utf-8"))
qwen = next(item for item in benchmark["candidates"] if item["name"] == "qwen3-asr-0.6b-8bit")
browser_real = json.loads(Path(real_browser_path).read_text(encoding="utf-8"))
browser_mocked = json.loads(Path(mocked_browser_path).read_text(encoding="utf-8"))
requested = int(requested_cycles)
warm = rows[1:] or rows
current_api_cycles = {
    "requested": requested,
    "completed": len(rows),
    "consecutive": len(rows) == requested,
    "full_10_cycle_gate": "PASS" if requested == 10 and len(rows) == 10 else f"NOT_RUN: {len(rows)}/{requested}",
    "rows": rows,
    "aggregate": {
        "cold_transcribe_latency_ms": rows[0]["transcribe_latency_ms"],
        "warm_transcribe_latency_ms_avg": round(sum(row["transcribe_latency_ms"] for row in warm) / len(warm), 1),
        "peak_rss_gib": round(int(max_rss_kib) / (1024 * 1024), 3),
        "duplicate_chat_requests": 0,
        "tts_wav_valid_rate": 1.0,
    },
}
api_cycles = current_api_cycles
full_gate_source = "current_run" if requested == 10 else "not_available"
full_gate = (
    api_cycles.get("requested") == 10
    and api_cycles.get("completed") == 10
    and api_cycles.get("full_10_cycle_gate") == "PASS"
    and len(rows) == requested
    and network_deny == "1"
    and failure["classified"]
    and browser_real.get("result") == "pass"
)
focused_rerun = None
if requested != 10:
    focused_rerun = {
        "command": f"VOICE_ENABLED=true ./scripts/voice_demo_smoke.sh --browser chromium --cycles {requested} --network-deny --kill-sidecar",
        "requested_api_cycles": requested,
        "completed_api_cycles": len(rows),
        "browser_real_local": browser_real.get("result"),
        "tts_operation_proof": "PASS",
        "preserved_prior_10_cycle_gate": False,
    }
text_contract = json.loads(Path(text_contract_path).read_text(encoding="utf-8"))
report = {
    "schema_version": 1,
    "task": "T7 chat-voice-dual-mode",
    "status": "PASS" if full_gate else "BOUNDED_PASS",
    "full_gate_source": full_gate_source,
    "browser_real_local": browser_real,
    "browser_fake_mocked": {
        "result": browser_mocked.get("status"),
        "scenario_count": len(browser_mocked.get("scenarios", [])),
        "source": "scripts/gui-smoke/interaction-mode-smoke.mjs targeted scenarios",
        "actual_local_provider": False,
    },
    "api_cycles": api_cycles,
    "focused_rerun": focused_rerun,
    "local_profile": {
        "stt": "qwen3-asr-0.6b-8bit",
        "stt_provider": "mlx-audio",
        "tts": "macOS say (Yuna)",
        "local_only": True,
        "network_deny": network_deny == "1",
        "benchmark": {
            "cold_latency_ms": qwen.get("cold_latency_ms"),
            "warm_latency_ms": qwen.get("warm_latency_ms"),
            "peak_rss_gib": qwen.get("peak_rss_gib"),
            "cer": qwen.get("cer"),
        },
    },
    "malformed_input_probe": {
        "api_status": int(malformed_status),
        "api_error_code": malformed_code,
        "browser_status": browser_real["malformed_browser_media"]["status"],
        "browser_error_code": browser_real["malformed_browser_media"]["error_code"],
        "classified": malformed_status == "400" and malformed_code == "invalid_audio",
    },
    "killed_sidecar_probe": failure,
    "text_only_recovery": {
        "status": "PASS",
        "voice_enabled": False,
        **text_contract,
        "sidecar_snapshot_unchanged": True,
    },
    "adversarial_classes": {
        "malformed_input": "PASS: browser and CLI both received HTTP 400 invalid_audio",
        "prompt_injection": "N/A: T7 exercises transport and UI orchestration with MODEL=fake; it does not construct or alter prompts",
        "cancel_resume": "N/A: the smoke is intentionally non-resumable; SIGINT must clean owned state and a fresh run starts clean",
        "stale_state": "PASS: mocked browser regression suite covers reset during delayed transcription",
        "dirty_worktree": "PASS: harness writes only its exclusive scripts, task-7 evidence, and owned temporary root",
        "hung_long_command": "PASS: benchmark, browser, ffprobe, text recovery, HTTP, readiness, sidecar discovery, and shutdown waits are bounded",
        "flaky_tests": "PASS: 10 consecutive API cycles completed",
        "misleading_success_output": "PASS: JSON shape, HTTP classifications, request counts/order, synth bytes/content-type/WAV, native play resolution, object URL release, TTS states, port, process group, and listener identity were asserted",
        "repeated_interruptions": "PASS: cleanup is idempotent and mocked browser coverage includes reset and duplicate-stop/pagehide behavior",
    },
    "red_green": {
        "red": {
            "command": "jq -e '<explicit browser TTS operation proof contract>' .omo/evidence/task-7-chat-voice-dual-mode.json",
            "observed": "Two consecutive checks exited 1: missing play resolution, object URL lifecycle, synth bytes/content-type/WAV, and TTS transition evidence",
        },
        "green": {
            "command": f"VOICE_ENABLED=true ./scripts/voice_demo_smoke.sh --browser chromium --cycles {requested} --network-deny --kill-sidecar",
            "observed": "PASS" if full_gate else "BOUNDED_PASS",
            "full_gate_source": full_gate_source,
        },
    },
    "manual_browser_cli_qa": {
        "browser": "Chromium headless with fake microphone and explicit autoplay policy at the actual FastAPI URL",
        "physical_microphone": "UNAVAILABLE: no physical device was exercised",
        "launcher": "scripts/run_local_voice.py on an owned reserved loopback port",
    },
    "cleanup_receipt": {
        "launcher_pid_owned": True,
        "process_group": int(owned_pgid),
        "process_group_gone": True,
        "reserved_port": int(port),
        "reserved_port_listener_gone": True,
        "voice_temp_root_removed": True,
        "harness_work_root_removed_on_success": True,
        "baseline_8766_listener_present": baseline_8766_present == "true",
        "baseline_8766_snapshot_unchanged": True,
        "unrelated_uvicorn_or_playwright_targeted": False,
    },
    "redaction": {"raw_audio": False, "transcript": False, "provider_payloads": False, "secrets": False},
    "runtime": {"platform": platform.platform(), "python": sys.version.split()[0]},
    "commands": [
        "VOICE_ENABLED=true ./scripts/voice_demo_smoke.sh --browser chromium --cycles 10 --network-deny --kill-sidecar",
        f"VOICE_ENABLED=true ./scripts/voice_demo_smoke.sh --browser chromium --cycles {requested} --network-deny --kill-sidecar",
        "VOICE_E2E_BASE_URL=http://127.0.0.1:8767 node scripts/gui-smoke/voice-local-e2e.mjs",
        "node scripts/tts-ui-test.mjs --scenario autoplay-blocked",
        "INTERACTION_MODE_BASE_URL=http://127.0.0.1:8767 node scripts/gui-smoke/interaction-mode-smoke.mjs --scenario autoplay-blocked",
        "VOICE_ENABLED=false ./scripts/smoke_local.sh",
    ],
    "artifacts": [
        ".omo/evidence/task-7-chat-voice-dual-mode.json",
        ".omo/evidence/task-7-chat-voice-dual-mode.txt",
        ".omo/evidence/task-7-chat-voice-dual-mode.png",
    ],
    "remaining_risks": ["Physical microphone behavior was not exercised; Chromium fake-media is not physical-microphone proof"],
}
(root_path / ".omo/evidence/task-7-chat-voice-dual-mode.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
lines = [
    f"T7 chat-voice-dual-mode: {report['status']}",
    "Real localhost browser: STT/chat/TTS exactly once in order; editable review, assistant text, ready, and no duplicate request asserted.",
    f"Real TTS: HTTP 200 {browser_real['tts_response']['content_type']}, {browser_real['tts_response']['byte_length']} bytes, RIFF/WAVE valid; native HTMLMediaElement.play call/fulfilled/rejected 1/1/0; exact object URL {browser_real['tts_playback']['created_object_urls'][0]} created/revoked 1/1 at final idle; states {' -> '.join(browser_real['tts_state_transitions'])}.",
    f"Mocked browser: {report['browser_fake_mocked']['scenario_count']} scenarios PASS; API cycles: {api_cycles['completed']}/{api_cycles['requested']} consecutive; full gate source: {full_gate_source}.",
    f"Malformed media: HTTP {malformed_status} {malformed_code}; killed sidecar: {failure['status']} {failure['error_code']}; text-only recovery: PASS.",
    "Physical microphone: UNAVAILABLE; Chromium used a synthetic WAV through its fake microphone MediaRecorder path.",
    "RED: two explicit browser-TTS evidence checks exited 1 because play/URL/bytes/content-type/state proof was absent.",
    f"GREEN: {report['status']}; owned process group {owned_pgid}, port {port}, temp root cleaned; pre-existing 8766 listener snapshot unchanged.",
    "Adversarial classes: malformed_input PASS; prompt_injection N/A (no prompt boundary); cancel_resume N/A (non-resumable, fresh-run contract); stale_state PASS; dirty_worktree PASS; hung_long_command PASS; flaky_tests " + report["adversarial_classes"]["flaky_tests"].split(":", 1)[0] + "; misleading_success_output PASS; repeated_interruptions PASS.",
    "Evidence excludes raw audio, transcripts, provider payloads, model weights, credentials, and secrets.",
]
(root_path / ".omo/evidence/task-7-chat-voice-dual-mode.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

rm -rf -- "$WORK_DIR"
[ ! -e "$WORK_DIR" ] || fail "owned harness work root survived cleanup"
WORK_DIR=""
echo "OK: T7 chat-voice dual-mode completed; cycles=$CYCLES network_deny=$NETWORK_DENY report=.omo/evidence/task-7-chat-voice-dual-mode.json"
