"""Synthetic crisis confirmation, pending counts, note redaction and erasure."""

import json
import stat
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import paths as data_paths
from app import access_log, chat, consent, intake, main, retention, review, stats, storage
from scripts.load_to_sqlite import load_day

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "synthetic-stats-token-for-c4"
SESSION = "synthetic-crisis"
HEADERS = {"X-Stats-Token": TOKEN}


@pytest.fixture
def review_client(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MODEL", "fake")
    monkeypatch.setenv("PRIVATE_LOCAL_UI", "1")
    monkeypatch.setenv("KNOWLEDGE_DIR", str(ROOT / "knowledge-maeum"))
    monkeypatch.setenv("STATS_API_TOKEN", TOKEN)
    monkeypatch.setattr(main, "_stats_auth_failures", {})
    monkeypatch.setattr(main, "_deletion_auth_failures", {})
    monkeypatch.setattr(chat, "_sessions", {})
    _seed(SESSION, "위기")
    _seed("synthetic-emotional", "정서")
    with TestClient(main.app) as client:
        yield client


def _seed(session_id, track, *, day=None, red_flags=None):
    day = day or date.today()
    summary = {"track": track, "slots": {"track": track}, "red_flags": red_flags or [], "unfilled": {}}
    path = data_paths.conversations_dir() / day.isoformat() / (session_id + ".json")
    storage._write_private_json(path, {"participant_id": "p_" + session_id,
                                      "turns": [{"seq": 0, "role": "intake_summary", "text": json.dumps(summary)}]})
    load_day(day)
    return path


def _payload(**updates):
    return {"day": date.today().isoformat(), "session_id": SESSION, "action": "안내 전화함", **updates}


def _stats(client, **params):
    response = client.get("/api/stats", headers=HEADERS, params=params)
    assert response.status_code == 200
    return response.json()


def test_summary_requires_review_for_crisis_or_any_red_flag():
    schema = intake.load_schema(ROOT / "knowledge-maeum")
    assert intake.build_summary_json(schema, {"track": "위기"})["review_required"] is True
    assert intake.build_summary_json(schema, {"track": "정서"})["review_required"] is False
    from dataclasses import replace
    flagged_schema = replace(schema, slots=[replace(slot, red_flag=True) if slot.id == "chief_complaint" else slot for slot in schema.slots])
    assert intake.build_summary_json(flagged_schema, {"track": "정서", "chief_complaint": "합성 호소"})["review_required"] is True


def test_pending_then_confirmation_and_reconfirmation(review_client):
    before = _stats(review_client)
    assert before["review_pending"] == 1
    assert next(r for r in before["recent_sessions"] if r["session_id"] == SESSION)["review_status"] == "대기"
    assert next(r for r in before["recent_sessions"] if r["track"] == "정서")["review_required"] is False
    assert all("review_required" in r and "review_status" in r for r in before["individual_flags"])
    assert review_client.post("/api/review", json=_payload(), headers=HEADERS).status_code == 200
    after = _stats(review_client)
    assert after["review_pending"] == 0
    assert next(r for r in after["recent_sessions"] if r["session_id"] == SESSION)["review_status"] == "안내 전화함"
    assert review_client.post("/api/review", json=_payload(action="연락 불가"), headers=HEADERS).status_code == 200
    records = review.read_reviews()
    assert len(records) == 2
    assert review.latest_actions()[access_log.hash_value(SESSION)] == "연락 불가"
    assert next(r for r in _stats(review_client)["individual_flags"] if r["session_id"] == SESSION)["review_status"] == "연락 불가"
    path = data_paths.reviews_path()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert SESSION not in path.read_text() and TOKEN not in path.read_text()
    assert set(records[0]) == {"session_hash", "action", "at", "actor"}
    audit = [json.loads(line) for line in data_paths.access_log_path().read_text().splitlines()]
    assert len([row for row in audit if row["kind"] == "review"]) == 2
    assert all(row["actor"] == access_log.actor_hash(TOKEN) for row in records + audit)


def test_review_requires_auth_and_honors_failure_lock(review_client):
    for _ in range(main.MAX_STATS_AUTH_FAILURES):
        assert review_client.post("/api/review", json=_payload()).status_code == 401
    assert review_client.post("/api/review", json=_payload(), headers=HEADERS).status_code == 429
    assert not data_paths.reviews_path().exists()
    assert not data_paths.access_log_path().exists()


@pytest.mark.parametrize("updates", [{"action": "임의 결과"}, {"action": ["안내 전화함"]}, {"note": "가" * 201},
                                      {"note": None}, {"day": "2026-02-30"}, {"day": 123}, {"session_id": "../invalid"}])
def test_invalid_input_is_400_without_writes(review_client, updates):
    assert review_client.post("/api/review", json=_payload(**updates), headers=HEADERS).status_code == 400
    assert not data_paths.reviews_path().exists()
    assert not data_paths.access_log_path().exists()


@pytest.mark.parametrize("action", review.ACTIONS)
def test_all_actions_and_note_redaction(review_client, action):
    note = "합성 번호 010-0000-0000, synthetic@example.invalid"
    assert review_client.post("/api/review", json=_payload(action=action, note=note), headers=HEADERS).status_code == 200
    assert review.read_reviews()[0]["note"] == storage.redact_pii(note)
    assert "010-0000-0000" not in data_paths.reviews_path().read_text()
    assert _stats(review_client)["review_pending"] == 0


def test_review_cookie_auth(review_client, monkeypatch):
    monkeypatch.setattr(main, "STATIC_DIR", str(ROOT / "static"))
    assert review_client.get("/stats.html").status_code == 200
    assert review_client.post("/api/review", json=_payload()).status_code == 200


def test_unknown_session_or_wrong_day_is_not_reviewed(review_client):
    for updates in ({"session_id": "missing"}, {"day": "2000-01-01"}):
        assert review_client.post("/api/review", json=_payload(**updates), headers=HEADERS).status_code == 404
    assert not data_paths.reviews_path().exists()
    assert not data_paths.access_log_path().exists()


@pytest.mark.parametrize("which", ["access", "review"])
def test_write_failure_does_not_acknowledge_confirmation(review_client, monkeypatch, which):
    def fail(*_args, **_kwargs):
        raise OSError("synthetic disk failure")

    if which == "access":
        monkeypatch.setattr(access_log, "record_access", fail)
    else:
        monkeypatch.setattr(review, "record_review", fail)
    assert review_client.post("/api/review", json=_payload(), headers=HEADERS).status_code == 503
    assert not data_paths.reviews_path().exists()
    assert stats.read_stats()["review_pending"] == 1


@pytest.mark.parametrize("via", ["delete_code", "session_token"])
def test_self_deletion_removes_only_its_reviews_and_keeps_access_log(review_client, via):
    for action in review.ACTIONS[:2]:
        assert review_client.post("/api/review", json=_payload(action=action), headers=HEADERS).status_code == 200
    review.record_review("synthetic-emotional", "해당 없음", TOKEN)
    audit_before = data_paths.access_log_path().read_bytes()
    if via == "delete_code":
        payload = {"delete_code": consent.issue_delete_code(SESSION)}
    else:
        session = chat._get_session(SESSION)
        payload = {"session_id": SESSION, "session_token": session.session_token}
    assert review_client.post("/api/session/delete", json=payload).status_code == 200
    assert all(r["session_hash"] != access_log.hash_value(SESSION) for r in review.read_reviews())
    assert len(review.read_reviews()) == 1
    assert data_paths.access_log_path().read_bytes() == audit_before
    assert review_client.post("/api/review", json=_payload(), headers=HEADERS).status_code == 404


@pytest.mark.parametrize("age", [91, 366])
def test_retention_keeps_review_until_session_is_fully_erased(review_client, age):
    sid = "synthetic-expired"
    _seed(sid, "위기", day=date.today() - timedelta(days=age))
    review.record_review(sid, "기관 연결함", TOKEN)
    access_log.record_access("review", TOKEN, "synthetic-peer", session_id=sid)
    audit_before = data_paths.access_log_path().read_bytes()
    review_before = data_paths.reviews_path().read_bytes()
    retention.purge_expired(today=date.today(), dry_run=True)
    assert data_paths.reviews_path().read_bytes() == review_before
    retention.purge_expired(today=date.today())
    assert bool(review.read_reviews()) == (age == 91)
    assert data_paths.access_log_path().read_bytes() == audit_before


def test_red_flags_and_multiple_days_count_unique_pending_sessions(review_client):
    _seed("synthetic-flagged", "정서", red_flags=["synthetic-flag"])
    _seed(SESSION, "위기", day=date.today() - timedelta(days=1))
    result = _stats(review_client)
    assert result["review_pending"] == 2
    assert _stats(review_client, session_prefix="synthetic-flagged")["review_pending"] == 1


def test_latest_summary_and_old_pending_case_remain_visible(review_client):
    # A later crisis summary must not be overwritten by an earlier emotional one.
    storage.append_turn("synthetic-emotional", "intake_summary", json.dumps({"track": "위기", "red_flags": []}), participant_id="p_synthetic-emotional")
    _seed("synthetic-old-pending", "위기", day=date.today() - timedelta(days=2))
    for number in range(205):
        _seed("synthetic-normal-" + str(number).zfill(3), "정서")
    result = _stats(review_client)
    assert result["review_pending"] == 3
    assert any(r["session_id"] == "synthetic-old-pending" for r in result["recent_sessions"])
    assert next(r for r in result["recent_sessions"] if r["session_id"] == "synthetic-emotional")["review_required"] is True


def test_public_review_remains_dark_even_with_token(review_client, monkeypatch):
    monkeypatch.setenv("PUBLIC_CHAT_UI", "1")
    response = review_client.post("http://public.example/api/review", json=_payload(), headers=HEADERS)
    assert response.status_code == 404
    assert not data_paths.reviews_path().exists()


def test_empty_database_has_zero_pending(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert stats.read_stats()["review_pending"] == 0
