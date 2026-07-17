#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$REPO_ROOT/.venv/bin/python}"
PORT="${PORT:-8934}"
HOST="${HOST:-127.0.0.1}"
PACK="${PACK:-${KNOWLEDGE_DIR:-knowledge}}"
WORK_DIR="$(mktemp -d)"
SERVER_PID=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --pack)
      PACK="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --host)
      HOST="$2"
      shift 2
      ;;
    --python)
      PYTHON="$2"
      shift 2
      ;;
    *)
      echo "FAIL: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

cleanup() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

case "$PACK" in
  /*) PACK_DIR="$PACK" ;;
  *) PACK_DIR="$REPO_ROOT/$PACK" ;;
esac
[ -d "$PACK_DIR" ] || fail "knowledge pack directory not found: $PACK_DIR"
[ -x "$PYTHON" ] || fail "python not executable: $PYTHON"

export MODEL="${MODEL:-fake}"
export KNOWLEDGE_DIR="$PACK_DIR"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

if [ -f "$REPO_ROOT/scripts/validate_knowledge_pack.py" ] && [ -f "$PACK_DIR/_validation_scenario.json" ]; then
  "$PYTHON" "$REPO_ROOT/scripts/validate_knowledge_pack.py" "$PACK_DIR" >/dev/null
fi

cd "$WORK_DIR"
"$PYTHON" -m uvicorn app.main:app --app-dir "$REPO_ROOT" \
  --host "$HOST" --port "$PORT" --log-level warning &
SERVER_PID=$!

ready=0
for _ in $(seq 1 450); do
  if curl -s -o /dev/null "http://$HOST:$PORT/api/config"; then
    ready=1
    break
  fi
  sleep 0.2
done
[ "$ready" -eq 1 ] || fail "server did not start on $HOST:$PORT"

post_chat() {
  curl -s -o /dev/null -w '%{http_code}' -X POST "http://$HOST:$PORT/api/chat" \
    -H 'Content-Type: application/json' \
    -d "{\"schema_version\":2,\"metadata\":{\"smoke\":true},\"session_id\":\"$1\",\"message\":\"$2\"}"
}

post_chat_body() {
  curl -s -X POST "http://$HOST:$PORT/api/chat" \
    -H 'Content-Type: application/json' \
    -d "{\"schema_version\":2,\"metadata\":{\"smoke\":true},\"session_id\":\"$1\",\"message\":\"$2\"}"
}

post_chat_owned() {
  curl -s -o /dev/null -w '%{http_code}' -X POST "http://$HOST:$PORT/api/chat" \
    -H 'Content-Type: application/json' \
    -d "{\"schema_version\":2,\"metadata\":{\"smoke\":true},\"session_id\":\"$1\",\"session_token\":\"$3\",\"message\":\"$2\"}"
}

first_body=$(post_chat_body "smoke-session-1" "안녕하세요")
status=$(printf '%s' "$first_body" | "$PYTHON" -c 'import json, sys; print(json.load(sys.stdin).get("session_token", ""))')
[ -n "$status" ] || fail "first session did not return a session token"
session_token="$status"

for i in 2 3 4 5; do
  status=$(post_chat "smoke-session-$i" "안녕하세요")
  [ "$status" = "200" ] || fail "new session $i expected 200, got $status"
done
status=$(post_chat "smoke-session-6" "안녕하세요")
[ "$status" = "429" ] || fail "6th new session expected 429, got $status"

status=$(post_chat_owned "smoke-session-1" "두 번째 질문" "$session_token")
[ "$status" = "200" ] || fail "second turn expected 200, got $status"
status=$(post_chat_owned "smoke-session-1" "세 번째 질문" "$session_token")
[ "$status" = "200" ] || fail "third turn expected 200, got $status"

TODAY=$(date +%F)
CONV_FILE="$WORK_DIR/data/conversations/$TODAY/smoke-session-1.json"
[ -f "$CONV_FILE" ] || fail "conversation JSON missing: $CONV_FILE"
turn_count=$("$PYTHON" - "$CONV_FILE" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as f:
    payload = json.load(f)
turns = payload.get("turns", payload) if isinstance(payload, dict) else payload
print(len(turns))
PY
)
[ "$turn_count" = "6" ] || fail "JSON turns expected 6, got $turn_count"

"$PYTHON" "$REPO_ROOT/scripts/load_to_sqlite.py" --date "$TODAY"

DB_FILE="$WORK_DIR/data/chatlog.db"
[ -f "$DB_FILE" ] || fail "SQLite DB missing: $DB_FILE"
row_count=$("$PYTHON" - "$DB_FILE" <<'PY'
import sqlite3
import sys
conn = sqlite3.connect(sys.argv[1])
try:
    print(conn.execute("SELECT COUNT(*) FROM turns WHERE session_id = 'smoke-session-1'").fetchone()[0])
finally:
    conn.close()
PY
)
[ "$row_count" = "6" ] || fail "SQLite rows expected 6, got $row_count"

echo "OK: local smoke passed pack=$PACK_DIR port=$PORT"
