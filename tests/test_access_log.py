"""Access records are private and mandatory before releasing raw content."""

import hashlib
import json
import logging
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import paths as data_paths
from app import access_log, main, storage

TOKEN = "synthetic-stats-token-for-c3"
SESSION = "synthetic-c3-session"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def audit_client(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MODEL", "fake")
    monkeypatch.setenv("PRIVATE_LOCAL_UI", "1")
    monkeypatch.setenv("KNOWLEDGE_DIR", str(ROOT / "knowledge-maeum"))
    monkeypatch.setenv("STATS_API_TOKEN", TOKEN)
    monkeypatch.setattr(main, "_stats_auth_failures", {})
    storage.append_turn(SESSION, "user", "합성 접수 내용", participant_id="p_synthetic_c3")
    with TestClient(main.app) as client:
        yield client


def _lines():
    return [json.loads(line) for line in data_paths.access_log_path().read_text().splitlines()]


def test_stats_and_raw_view_log_once_without_plain_credentials(audit_client):
    headers = {"X-Stats-Token": TOKEN}
    assert audit_client.get("/api/stats", params={"session_prefix": "synthetic-c3"}, headers=headers).status_code == 200
    entries = _lines()
    assert len(entries) == 1
    assert entries[0]["kind"] == "stats"
    assert entries[0]["filters"] == {"participant_prefix": None, "session_prefix": "synthetic-c3"}
    response = audit_client.get("/api/stats/session", params={"day": date.today().isoformat(), "session_id": SESSION}, headers=headers)
    assert response.status_code == 200
    entries = _lines()
    assert [row["kind"] for row in entries] == ["stats", "raw_view"]
    assert entries[1]["session_hash"] == hashlib.sha256(SESSION.encode()).hexdigest()
    for entry in entries:
        assert entry["actor"] == hashlib.sha256(TOKEN.encode()).hexdigest()[:8]
        assert entry["ip_hash"] == hashlib.sha256(b"testclient").hexdigest()
        assert datetime.fromisoformat(entry["at"]).tzinfo is not None
    path = data_paths.access_log_path()
    if os.name != "nt":  # Windows 에는 POSIX 권한 비트가 없다
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert all(value not in path.read_text() for value in (TOKEN, SESSION, "testclient", "합성 접수 내용"))


@pytest.mark.parametrize("url,params", [("/api/stats", {}), ("/api/stats/session", {"day": "2026-11-02", "session_id": SESSION})])
def test_failed_auth_has_no_access_record(audit_client, url, params):
    for headers in ({}, {"X-Stats-Token": "incorrect"}):
        assert audit_client.get(url, params=params, headers=headers).status_code == 401
    assert not data_paths.access_log_path().exists()


def test_cookie_uses_same_hashed_actor(audit_client, monkeypatch):
    monkeypatch.setattr(main, "STATIC_DIR", str(ROOT / "static"))
    assert audit_client.get("/stats.html").status_code == 200
    assert audit_client.get("/api/stats").status_code == 200
    assert _lines()[0]["actor"] == access_log.actor_hash(TOKEN)


def test_audit_failure_blocks_raw_but_stats_logs_error(audit_client, monkeypatch, caplog):
    def fail(*_args, **_kwargs):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(access_log, "record_access", fail)
    headers = {"X-Stats-Token": TOKEN}
    with caplog.at_level(logging.ERROR, logger="app.main"):
        raw = audit_client.get("/api/stats/session", params={"day": date.today().isoformat(), "session_id": SESSION}, headers=headers)
        result = audit_client.get("/api/stats", headers=headers)
    assert raw.status_code == 503
    assert "합성 접수 내용" not in raw.text
    assert result.status_code == 200
    assert "Access record could not be written (stats)" in caplog.text


def test_missing_session_does_not_log_success(audit_client):
    response = audit_client.get("/api/stats/session", params={"day": date.today().isoformat(), "session_id": "missing"}, headers={"X-Stats-Token": TOKEN})
    assert response.status_code == 404
    assert not data_paths.access_log_path().exists()


def test_existing_access_file_permissions_are_tightened(audit_client):
    path = data_paths.access_log_path()
    path.touch(mode=0o644)
    path.chmod(0o644)
    assert audit_client.get("/api/stats", headers={"X-Stats-Token": TOKEN}).status_code == 200
    if os.name != "nt":  # Windows 에는 POSIX 권한 비트가 없다
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_concurrent_appends_are_complete_lines(tmp_path):
    root = tmp_path / "data/conversations"
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: access_log.record_access("raw_view", TOKEN, "synthetic-peer", session_id=SESSION, base_dir=root), range(30)))
    rows = [json.loads(line) for line in (root.parent / "access_log.jsonl").read_text().splitlines()]
    assert len(rows) == 30
    assert all(row["kind"] == "raw_view" for row in rows)
