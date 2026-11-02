"""Bearer deletion, private code persistence, all-day deletion and abuse limits."""
import json
import sqlite3
import stat
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import chat, consent, main, ratelimit, storage
from scripts.load_to_sqlite import load_day

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def deletion_client(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MODEL", "fake")
    monkeypatch.setenv("KNOWLEDGE_DIR", str(ROOT / "knowledge-maeum"))
    monkeypatch.setattr(chat, "_sessions", {})
    monkeypatch.setattr(main, "_deletion_auth_failures", {})
    monkeypatch.setattr(main, "_rate_limiter", ratelimit.RateLimiter())
    with TestClient(main.app) as client:
        yield client


def _seed(client):
    result = client.post("/api/consent", json={"session_id": "delete-me", "accepted": True, "consent_version": "maeum-2026-11-02"}).json()
    response = client.post("/api/chat", json={"session_id": "delete-me", "session_token": result["session_token"], "message": "합성 고민: 요즘 불안해서 잠을 못 자요"})
    assert response.status_code == 200
    storage.append_turn("keep-me", "user", "보존할 합성 기록", participant_id=result["participant_id"])
    today = date.today()
    yesterday = today - timedelta(days=1)
    earlier = Path("data/conversations") / yesterday.isoformat()
    earlier.mkdir()
    (earlier / "delete-me.json").write_text(json.dumps({"participant_id": result["participant_id"], "turns": [{"seq": 0, "role": "user", "text": "전날 합성 원문"}]}))
    load_day(today)
    load_day(yesterday)
    return result


@pytest.mark.parametrize("via", ["session_token", "delete_code"])
def test_delete_removes_all_days_sql_memory_and_hash_with_minimal_tombstone(deletion_client, via):
    result = _seed(deletion_client)
    if via == "delete_code":
        # Codes continue working after a process restart loses all session tokens.
        chat._sessions.clear()
        payload = {"delete_code": result["delete_code"].lower().replace("-", " ")}
    else:
        payload = {"session_id": "delete-me", "session_token": result["session_token"]}
    response = deletion_client.post("/api/session/delete", json=payload)
    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert not list(Path("data/conversations").glob("*/delete-me.json"))
    assert len(list(Path("data/conversations").glob("*/keep-me.json"))) == 1
    with sqlite3.connect("data/chatlog.db") as conn:
        for table in ("conversations", "turns"):
            assert conn.execute(f"SELECT count(*) FROM {table} WHERE session_id=?", ("delete-me",)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM turns WHERE session_id=?", ("keep-me",)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM participants").fetchone()[0] == 1
    assert "delete-me" not in chat._sessions
    assert consent.session_for_delete_code(result["delete_code"]) is None
    lines = Path("data/tombstones.jsonl").read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert set(record) == {"session_hash", "deleted_at", "via"}
    assert len(record["session_hash"]) == 64
    assert record["via"] == via
    for secret in ("delete-me", result["delete_code"], "불안", "전날 합성 원문"):
        assert secret not in lines[0]
    # Re-import cannot resurrect removed JSON or SQL turns.
    load_day(date.today())
    with sqlite3.connect("data/chatlog.db") as conn:
        assert conn.execute("SELECT count(*) FROM turns WHERE session_id=?", ("delete-me",)).fetchone()[0] == 0


def test_code_is_only_salted_hash_on_disk_and_private(deletion_client):
    result = _seed(deletion_client)
    path = Path("data/delete_codes.jsonl")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    record = json.loads(path.read_text().splitlines()[0])
    assert set(record) == {"session_id", "salt", "code_hash"}
    assert len(record["salt"]) == len(record["code_hash"]) == 64
    for path in Path("data").rglob("*"):
        if path.is_file():
            assert result["delete_code"].encode() not in path.read_bytes()
            assert result["delete_code"].replace("-", "").encode() not in path.read_bytes()


@pytest.mark.parametrize("payload", [
    {"delete_code": "AAAA-BBBB-CCCC"}, {"delete_code": None}, {"delete_code": ["not a code"]},
    {"session_id": "delete-me", "session_token": "wrong"},
    {"session_id": "delete-me", "session_token": "틀린 토큰"},
    {"session_id": "../bad", "session_token": "wrong"},
])
def test_wrong_credentials_are_401_without_deletion(deletion_client, payload):
    result = _seed(deletion_client)
    assert deletion_client.post("/api/session/delete", json=payload).status_code == 401
    assert list(Path("data/conversations").glob("*/delete-me.json"))
    assert consent.session_for_delete_code(result["delete_code"]) == "delete-me"
    assert not Path("data/tombstones.jsonl").exists()


def test_deletion_failure_limit_is_per_ip_and_windowed(deletion_client):
    for _ in range(main.MAX_STATS_AUTH_FAILURES):
        assert deletion_client.post("/api/session/delete", json={"delete_code": "wrong"}).status_code == 401
    assert deletion_client.post("/api/session/delete", json={"delete_code": "wrong"}).status_code == 429
    assert main._failure_allowed("another-ip", main._deletion_auth_failures)
    main._deletion_auth_failures["testclient"] = ["2000-01-01T00:00:00+00:00"]
    assert deletion_client.post("/api/session/delete", json={"delete_code": "wrong"}).status_code == 401


def test_deletion_preserves_unrelated_orphan_participants(deletion_client):
    result = _seed(deletion_client)
    with sqlite3.connect("data/chatlog.db") as conn:
        conn.execute("INSERT INTO participants VALUES (?)", ("unrelated-orphan",))
    assert deletion_client.post("/api/session/delete", json={"delete_code": result["delete_code"]}).status_code == 200
    with sqlite3.connect("data/chatlog.db") as conn:
        assert conn.execute("SELECT participant_id FROM participants WHERE participant_id=?", ("unrelated-orphan",)).fetchone() == ("unrelated-orphan",)
