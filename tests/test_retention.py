"""Retention dates, SQL/JSON consistency, and a genuinely read-only CLI dry-run."""
import json
import os
import sqlite3
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest

from app import paths as data_paths
from app import chat, consent, retention, storage
from scripts.load_to_sqlite import load_day

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 2)


@pytest.fixture(autouse=True)
def isolated_records(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MODEL", "fake")
    monkeypatch.setenv("KNOWLEDGE_DIR", str(ROOT / "knowledge-maeum"))
    monkeypatch.setattr(chat, "_sessions", {})


def _seed(sid, age):
    day = TODAY - timedelta(days=age)
    path = data_paths.conversations_dir() / day.isoformat() / f"{sid}.json"
    turns = [{"seq": n, "role": role, "text": "합성 원문" if n < 3 else "합성 요약"}
             for n, role in enumerate(("user", "bot", "assistant", "intake_summary"))]
    storage._write_private_json(path, {"session_id": sid, "consent_version": "test", "consented_at": day.isoformat(),
                                       "intake_snapshot": {"track": "정서"}, "turns": turns})
    load_day(day)
    code = consent.issue_delete_code(sid)
    chat._get_session(sid)
    return path, day, code


def _snapshot():
    return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in data_paths.data_dir().rglob("*") if p.is_file()}


def test_91_days_removes_raw_but_keeps_summary_metadata_and_code():
    path, day, code = _seed("raw-expired", 91)
    result = retention.purge_expired(today=TODAY)
    assert result["sessions"] == 1
    assert result["turns"] == 6  # Three raw turns in each durable store.
    payload = json.loads(path.read_text())
    assert [t["role"] for t in payload["turns"]] == ["intake_summary"]
    assert payload["consent_version"] == "test"
    assert payload["intake_snapshot"] == {"track": "정서"}
    assert payload["raw_purged_at"] == TODAY.isoformat()
    assert "합성 원문" not in path.read_text()
    with sqlite3.connect(data_paths.db_path()) as conn:
        assert {r[0] for r in conn.execute("SELECT role FROM turns")} == {"intake_summary", "intake_snapshot"}
    assert consent.session_for_delete_code(code) == "raw-expired"
    assert "raw-expired" not in chat._sessions
    assert len(data_paths.tombstones_path().read_text().splitlines()) == 1
    load_day(day)
    assert retention.purge_expired(today=TODAY)["sessions"] == 0
    with sqlite3.connect(data_paths.db_path()) as conn:
        assert conn.execute("SELECT count(*) FROM turns WHERE role NOT IN (?,?)", retention.SUMMARY_ROLES).fetchone()[0] == 0


def test_366_days_deletes_everything_and_minimal_tombstone():
    path, _, code = _seed("summary-expired", 366)
    assert retention.purge_expired(today=TODAY)["sessions"] == 1
    assert not path.exists()
    assert not chat._sessions
    assert consent.session_for_delete_code(code) is None
    with sqlite3.connect(data_paths.db_path()) as conn:
        for table in ("turns", "conversations", "participants"):
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    tombstones = data_paths.tombstones_path().read_text().splitlines()
    assert len(tombstones) == 1
    assert json.loads(tombstones[0])["via"] == "retention_summary"
    assert all(s not in tombstones[0] for s in ("summary-expired", "합성", code))


@pytest.mark.parametrize("age,roles", [(90, ["user", "bot", "assistant", "intake_summary"]), (365, ["intake_summary"])])
def test_retention_boundary_keeps_unexpired_layer(age, roles):
    path, _, _ = _seed("boundary", age)
    retention.purge_expired(today=TODAY)
    assert [t["role"] for t in json.loads(path.read_text())["turns"]] == roles


def test_dry_run_is_read_only_for_both_layers_and_cli():
    _seed("raw", 91)
    _seed("summary", 366)
    before = _snapshot()
    result = retention.purge_expired(today=TODAY, dry_run=True)
    assert result["sessions"] == 2
    assert _snapshot() == before
    process = subprocess.run([str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/purge_expired.py"), "--dry-run", "--today", TODAY.isoformat()],
                             env=os.environ.copy(), capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)["sessions"] == 2
    assert _snapshot() == before


def test_empty_dry_run_creates_no_data_directory():
    assert retention.purge_expired(today=TODAY, dry_run=True)["sessions"] == 0
    assert not data_paths.data_dir().exists()


def test_sqlite_only_records_are_expired():
    path, _, _ = _seed("sql-only", 366)
    path.unlink()
    assert retention.purge_expired(today=TODAY)["sessions"] == 1
    with sqlite3.connect(data_paths.db_path()) as conn:
        assert conn.execute("SELECT count(*) FROM turns").fetchone()[0] == 0


def test_multiday_session_uses_earliest_day_and_prunes_every_file():
    older, _, _ = _seed("multiday", 91)
    newer = data_paths.conversations_dir() / TODAY.isoformat() / "multiday.json"
    storage._write_private_json(newer, {"turns": [{"seq": 0, "role": "user", "text": "新しい合成文"}]})
    load_day(TODAY)
    assert retention.purge_expired(today=TODAY)["sessions"] == 1
    assert json.loads(newer.read_text())["turns"] == []
    assert [t["role"] for t in json.loads(older.read_text())["turns"]] == ["intake_summary"]


def test_import_reconciles_removed_source_turns():
    path, day, _ = _seed("mirror", 0)
    payload = json.loads(path.read_text())
    payload["turns"] = [t for t in payload["turns"] if t["role"] == "intake_summary"]
    storage._write_private_json(path, payload)
    load_day(day)
    with sqlite3.connect(data_paths.db_path()) as conn:
        assert conn.execute("SELECT count(*) FROM turns WHERE role IN (?,?,?)", ("user", "bot", "assistant")).fetchone()[0] == 0


def test_consent_timestamp_prevents_new_folder_from_extending_retention():
    path, _, _ = _seed("dated-consent", 0)
    payload = json.loads(path.read_text())
    payload["consented_at"] = (TODAY - timedelta(days=366)).isoformat()
    storage._write_private_json(path, payload)
    assert retention.purge_expired(today=TODAY)["sessions"] == 1
    assert not path.exists()


def test_cli_purge_invalidates_live_state_in_another_process():
    from fastapi.testclient import TestClient
    from app.main import app

    path, _, _ = _seed("external-purge", 0)
    session = chat._sessions["external-purge"]
    process = subprocess.run([str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/purge_expired.py"), "--today", "2030-01-01"],
                             env=os.environ.copy(), capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    assert not path.exists()
    assert "external-purge" in chat._sessions  # Memory in the parent was not touched by the CLI.
    assert retention.session_retired(session)
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"session_id": session.session_id, "session_token": session.session_token, "message": "합성 입력"})
    assert response.status_code == 401
    assert "external-purge" not in chat._sessions
    assert not path.exists()
