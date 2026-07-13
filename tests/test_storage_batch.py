"""JSON 저장 → SQLite 적재 → 조회 왕복 + 멱등성 테스트."""

import json
import sqlite3
from datetime import date, timedelta

import pytest

from app import storage
from scripts import load_to_sqlite


def test_append_turn_rejects_path_traversal(tmp_path):
    conv_dir = tmp_path / "conversations"
    for bad in ("../evil", "a/b", "a\\b", "", "x" * 129):
        with pytest.raises(ValueError):
            storage.append_turn(bad, "user", "공격", base_dir=conv_dir)
    assert not (tmp_path / "evil.json").exists()


def test_append_turn_writes_json(tmp_path):
    conv_dir = tmp_path / "conversations"
    storage.append_turn("session-a", "user", "안녕하세요", base_dir=conv_dir)
    storage.append_turn("session-a", "assistant", "반갑습니다", base_dir=conv_dir)

    day_file = conv_dir / date.today().isoformat() / "session-a.json"
    turns = json.loads(day_file.read_text(encoding="utf-8"))
    assert turns == [
        {"seq": 0, "role": "user", "text": "안녕하세요"},
        {"seq": 1, "role": "assistant", "text": "반갑습니다"},
    ]


def test_load_to_sqlite_round_trip(tmp_path):
    conv_dir = tmp_path / "conversations"
    db_path = tmp_path / "chatlog.db"
    today = date.today()

    storage.append_turn("session-b", "user", "질문", base_dir=conv_dir)
    storage.append_turn("session-b", "assistant", "답변", base_dir=conv_dir)

    loaded = load_to_sqlite.load_day(today, conversations_dir=conv_dir, db_path=db_path)
    assert loaded == 2

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT role, text FROM turns WHERE date = ? AND session_id = ? ORDER BY seq",
        (today.isoformat(), "session-b"),
    ).fetchall()
    conn.close()
    assert rows == [("user", "질문"), ("assistant", "답변")]


def test_load_to_sqlite_is_idempotent(tmp_path):
    conv_dir = tmp_path / "conversations"
    db_path = tmp_path / "chatlog.db"
    today = date.today()

    storage.append_turn("session-c", "user", "중복 확인", base_dir=conv_dir)

    load_to_sqlite.load_day(today, conversations_dir=conv_dir, db_path=db_path)
    load_to_sqlite.load_day(today, conversations_dir=conv_dir, db_path=db_path)  # 재실행

    conn = sqlite3.connect(db_path)
    total = conn.execute(
        "SELECT COUNT(*) FROM turns WHERE date = ? AND session_id = ?",
        (today.isoformat(), "session-c"),
    ).fetchone()[0]
    conn.close()
    assert total == 1


def test_load_to_sqlite_keeps_same_session_id_on_different_dates(tmp_path):
    conv_dir = tmp_path / "conversations"
    db_path = tmp_path / "chatlog.db"
    first_day = date(2026, 7, 12)
    second_day = first_day + timedelta(days=1)

    for day, text in ((first_day, "첫날 질문"), (second_day, "다음날 질문")):
        day_dir = conv_dir / day.isoformat()
        day_dir.mkdir(parents=True)
        (day_dir / "same-session.json").write_text(
            json.dumps([{"seq": 0, "role": "user", "text": text}], ensure_ascii=False),
            encoding="utf-8",
        )

    assert load_to_sqlite.load_day(first_day, conversations_dir=conv_dir, db_path=db_path) == 1
    assert load_to_sqlite.load_day(second_day, conversations_dir=conv_dir, db_path=db_path) == 1

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT date, session_id, seq, text FROM turns ORDER BY date, seq"
    ).fetchall()
    conn.close()

    assert rows == [
        ("2026-07-12", "same-session", 0, "첫날 질문"),
        ("2026-07-13", "same-session", 0, "다음날 질문"),
    ]


def test_load_to_sqlite_migrates_legacy_session_id_primary_key(tmp_path):
    db_path = tmp_path / "chatlog.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE conversations (
            session_id TEXT PRIMARY KEY,
            date TEXT NOT NULL
        );
        CREATE TABLE turns (
            session_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            role TEXT NOT NULL,
            text TEXT NOT NULL,
            PRIMARY KEY (session_id, seq)
        );
        INSERT INTO conversations (session_id, date) VALUES ('legacy-session', '2026-07-11');
        INSERT INTO turns (session_id, seq, role, text)
        VALUES ('legacy-session', 0, 'user', '레거시 질문');
        """
    )
    conn.commit()
    conn.close()

    conv_dir = tmp_path / "conversations"
    day_dir = conv_dir / "2026-07-12"
    day_dir.mkdir(parents=True)
    (day_dir / "new-session.json").write_text(
        json.dumps([{"seq": 0, "role": "assistant", "text": "신규 답변"}], ensure_ascii=False),
        encoding="utf-8",
    )

    assert load_to_sqlite.load_day(date(2026, 7, 12), conversations_dir=conv_dir, db_path=db_path) == 1

    conn = sqlite3.connect(db_path)
    columns = [row[1] for row in conn.execute("PRAGMA table_info(turns)").fetchall()]
    rows = conn.execute(
        "SELECT date, session_id, seq, role, text FROM turns ORDER BY date, session_id"
    ).fetchall()
    conn.close()

    assert "date" in columns
    assert rows == [
        ("2026-07-11", "legacy-session", 0, "user", "레거시 질문"),
        ("2026-07-12", "new-session", 0, "assistant", "신규 답변"),
    ]


def test_load_to_sqlite_missing_day_returns_zero(tmp_path):
    loaded = load_to_sqlite.load_day(
        date(2000, 1, 1),
        conversations_dir=tmp_path / "conversations",
        db_path=tmp_path / "chatlog.db",
    )
    assert loaded == 0
