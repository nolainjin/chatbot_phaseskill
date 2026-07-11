"""JSON 저장 → SQLite 적재 → 조회 왕복 + 멱등성 테스트."""

import json
import sqlite3
from datetime import date

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
        "SELECT role, text FROM turns WHERE session_id = ? ORDER BY seq",
        ("session-b",),
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
        "SELECT COUNT(*) FROM turns WHERE session_id = ?", ("session-c",)
    ).fetchone()[0]
    conn.close()
    assert total == 1


def test_load_to_sqlite_missing_day_returns_zero(tmp_path):
    loaded = load_to_sqlite.load_day(
        date(2000, 1, 1),
        conversations_dir=tmp_path / "conversations",
        db_path=tmp_path / "chatlog.db",
    )
    assert loaded == 0
