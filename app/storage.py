"""대화 턴을 날짜별 JSON 파일에 저장한다.

data/conversations/YYYY-MM-DD/{session_id}.json 에 세션의 턴을 통째로
읽고-append하고-다시 쓴다. 세션당 최대 20턴(사용자+봇 각 10턴)이라
파일 전체를 매번 재작성해도 충분히 가볍다 — append 전용 스트리밍 writer는
필요 없다. 표준 json 모듈만 쓴다.
"""

import json
import re
from datetime import date
from pathlib import Path

DEFAULT_CONVERSATIONS_DIR = Path("data/conversations")

# 공개 API가 주는 session_id가 파일명이 되므로 경로 구분자를 차단한다.
_SESSION_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,128}")


def append_turn(
    session_id: str,
    role: str,
    text: str,
    base_dir: str | Path = DEFAULT_CONVERSATIONS_DIR,
) -> None:
    """오늘 날짜 디렉토리의 세션 JSON에 (role, text) 턴을 추가한다."""
    if not _SESSION_ID_RE.fullmatch(session_id):
        raise ValueError(f"잘못된 session_id: {session_id!r}")
    day_dir = Path(base_dir) / date.today().isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{session_id}.json"

    turns = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    turns.append({"seq": len(turns), "role": role, "text": text})
    path.write_text(json.dumps(turns, ensure_ascii=False, indent=2), encoding="utf-8")
