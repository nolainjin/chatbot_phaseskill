#!/usr/bin/env bash
# 로컬 통합 스모크: uvicorn 기동 -> 신규 세션 5회/시간 rate limit 경계 확인 ->
# 채팅 3턴 -> data/conversations JSON 저장 확인 -> load_to_sqlite.py 배치 실행 ->
# SQLite 행 수 확인. 하나라도 실패하면 비 0 종료코드.
#
# ponytail: 매 실행마다 임시 디렉토리를 cwd로 서버를 새로 띄운다. app/ratelimit.py,
# app/storage.py의 상태 파일 경로("data/ratelimit.json", "data/conversations")가
# env로 주입 가능하지 않고 상대경로로 고정돼 있어, 반복 실행 시 이전 실행의 rate
# limit 윈도우가 남아 있으면 "6번째 세션 = 429" 판정이 실행마다 달라진다. cwd를
# 매번 새 임시 디렉토리로 격리해 이 상태 오염을 우회한다(앱 코드 무수정 제약).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
PORT=8934
WORK_DIR="$(mktemp -d)"
SERVER_PID=""

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

cleanup() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

export MODEL=fake
export KNOWLEDGE_DIR="$REPO_ROOT/knowledge"

cd "$WORK_DIR"
"$PYTHON" -m uvicorn app.main:app --app-dir "$REPO_ROOT" \
  --host 127.0.0.1 --port "$PORT" --log-level warning &
SERVER_PID=$!

ready=0
for _ in $(seq 1 50); do
  if curl -s -o /dev/null "http://127.0.0.1:$PORT/"; then
    ready=1
    break
  fi
  sleep 0.2
done
[ "$ready" -eq 1 ] || fail "서버가 ${PORT}포트에서 기동하지 않음"

post_chat() {
  # $1=session_id $2=message -> stdout에 HTTP 상태코드
  curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$PORT/api/chat" \
    -H 'Content-Type: application/json' \
    -d "{\"session_id\": \"$1\", \"message\": \"$2\"}"
}

# --- 1) 신규 세션 5회/시간 rate limit 경계: 6번째 신규 세션은 429여야 한다 -------
for i in 1 2 3 4 5; do
  status=$(post_chat "smoke-session-$i" "안녕하세요")
  [ "$status" = "200" ] || fail "신규 세션 $i 기대 200, 실제 $status"
done
status=$(post_chat "smoke-session-6" "안녕하세요")
[ "$status" = "429" ] || fail "6번째 신규 세션 기대 429, 실제 $status"

# --- 2) 이미 등록된 세션(smoke-session-1)에 2턴 더 채팅 -> 총 3턴 -----------------
# (기존 세션의 후속 발화는 rate limit 윈도우를 소모하지 않는다 -- app/ratelimit.py)
status=$(post_chat "smoke-session-1" "두 번째 질문")
[ "$status" = "200" ] || fail "2번째 턴 기대 200, 실제 $status"
status=$(post_chat "smoke-session-1" "세 번째 질문")
[ "$status" = "200" ] || fail "3번째 턴 기대 200, 실제 $status"

# --- 3) data/conversations/오늘/*.json 존재 + 턴 수 확인 ------------------------
TODAY=$(date +%F)
CONV_FILE="$WORK_DIR/data/conversations/$TODAY/smoke-session-1.json"
[ -f "$CONV_FILE" ] || fail "대화 JSON 파일 없음: $CONV_FILE"
turn_count=$("$PYTHON" -c "import json; print(len(json.load(open('$CONV_FILE'))))")
[ "$turn_count" = "6" ] || fail "JSON 턴 수 기대 6(user/assistant x3), 실제 $turn_count"

# --- 4) load_to_sqlite.py 일배치 실행 -------------------------------------------
"$PYTHON" "$REPO_ROOT/scripts/load_to_sqlite.py" --date "$TODAY"

# --- 5) SQLite 조회로 행 수 확인 -------------------------------------------------
DB_FILE="$WORK_DIR/data/chatlog.db"
[ -f "$DB_FILE" ] || fail "SQLite DB 파일 없음: $DB_FILE"
row_count=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM turns WHERE session_id = 'smoke-session-1';")
[ "$row_count" = "6" ] || fail "SQLite 행 수 기대 6, 실제 $row_count"

echo "OK: 로컬 통합 스모크 전 구간 통과"
