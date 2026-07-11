"""전일자(또는 --date) JSON 대화 로그를 SQLite(data/chatlog.db)에 적재한다.

세션+턴순번(PK)로 UPSERT하므로 같은 날짜를 여러 번 돌려도 중복되지 않는다
(멱등). 표준 sqlite3 모듈만 쓴다 — 서버 DB는 두지 않는다.

크론 등록 예시 (실제 등록은 배포 phase에서):
    0 3 * * * cd /path/to/repo && .venv/bin/python scripts/load_to_sqlite.py
"""

import argparse
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DEFAULT_CONVERSATIONS_DIR = Path("data/conversations")
DEFAULT_DB_PATH = Path("data/chatlog.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    session_id TEXT PRIMARY KEY,
    date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);
"""


def load_day(
    day: date,
    conversations_dir: Path = DEFAULT_CONVERSATIONS_DIR,
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    """day 디렉토리의 세션 JSON을 전부 SQLite에 UPSERT한다. 적재한 턴 수를 반환한다."""
    day_dir = Path(conversations_dir) / day.isoformat()
    if not day_dir.is_dir():
        return 0

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_SCHEMA)
        loaded = 0
        for json_file in sorted(day_dir.glob("*.json")):
            session_id = json_file.stem
            turns = json.loads(json_file.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO conversations (session_id, date) VALUES (?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET date=excluded.date",
                (session_id, day.isoformat()),
            )
            for turn in turns:
                conn.execute(
                    "INSERT INTO turns (session_id, seq, role, text) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(session_id, seq) DO UPDATE SET "
                    "role=excluded.role, text=excluded.text",
                    (session_id, turn["seq"], turn["role"], turn["text"]),
                )
                loaded += 1
        conn.commit()
        return loaded
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="적재할 날짜 YYYY-MM-DD (기본값: 어제)")
    args = parser.parse_args(argv)

    target_day = date.fromisoformat(args.date) if args.date else date.today() - timedelta(days=1)
    loaded = load_day(target_day)
    print(f"{target_day.isoformat()}: {loaded}턴 적재")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
