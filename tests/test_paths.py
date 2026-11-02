"""Durable records follow late DATA_DIR changes and preserve explicit overrides."""

import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import access_log, consent, paths, ratelimit, retention, review, stats, storage
from scripts import load_to_sqlite, purge_expired


def test_autouse_data_dir_is_private_to_each_test(tmp_path):
    assert paths.data_dir() == tmp_path / "data"
    assert not paths.data_dir().exists()


@pytest.mark.parametrize("configured", [None, "custom-data", "absolute"])
def test_all_default_paths_preserve_names_and_read_environment(tmp_path, monkeypatch, configured):
    monkeypatch.chdir(tmp_path)
    if configured is None:
        monkeypatch.delenv("DATA_DIR")
        root = Path("data")
    else:
        root = tmp_path / configured if configured == "absolute" else Path(configured)
        monkeypatch.setenv("DATA_DIR", str(root))
    expected = {
        paths.conversations_dir: "conversations",
        paths.db_path: "chatlog.db",
        paths.ratelimit_path: "ratelimit.json",
        paths.records_lock_path: ".records.lock",
        paths.delete_codes_path: "delete_codes.jsonl",
        paths.tombstones_path: "tombstones.jsonl",
        paths.access_log_path: "access_log.jsonl",
        paths.reviews_path: "reviews.jsonl",
    }
    assert paths.data_dir() == root
    for resolver, filename in expected.items():
        assert resolver() == root / filename
    assert not root.exists()  # Resolving paths never creates files.
    storage.append_turn("default-path", "user", "synthetic")
    assert (root / "conversations" / date.today().isoformat() / "default-path.json").is_file()


def test_existing_objects_and_imported_functions_follow_data_dir_switches(tmp_path, monkeypatch):
    # Imported functions and an already constructed limiter must not freeze paths.
    append_turn, load_day = storage.append_turn, load_to_sqlite.load_day
    read_stats, read_detail = stats.read_stats, stats.read_session_detail
    limiter = ratelimit.RateLimiter()
    roots = [tmp_path / "first", tmp_path / "second"]
    code = None
    for index, root in enumerate(roots):
        monkeypatch.setenv("DATA_DIR", str(root))
        sid = f"late-{index}"
        assert not storage.conversation_exists(sid)
        if code is not None:
            assert consent.session_for_delete_code(code) is None
            assert review.read_reviews() == []
            assert not retention.session_retired(SimpleNamespace(session_id="retired", created_at="2000"))
        append_turn(sid, "user", "synthetic")
        storage.update_metadata(sid, {"synthetic": True})
        assert storage.conversation_exists(sid)
        assert load_day(date.today()) == 1
        assert read_stats()["totals"]["conversations"] == 1
        assert read_detail(date.today().isoformat(), sid)["session_id"] == sid
        code = consent.issue_delete_code(sid)
        assert consent.session_for_delete_code(code) == sid
        limiter.check("synthetic-ip", sid, daily_cap=1)
        review.record_review(sid, review.ACTIONS[0], "synthetic-token")
        access_log.record_access("raw_view", "synthetic-token", "synthetic-ip", session_id=sid)
        retention.tombstone("retired", "test")
        assert retention.session_retired(SimpleNamespace(session_id="retired", created_at="2000"))
        assert review.latest_actions()[access_log.hash_value(sid)] == review.ACTIONS[0]
        assert {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} == {
            f"conversations/{date.today().isoformat()}/{sid}.json", "chatlog.db",
            "delete_codes.jsonl", "ratelimit.json", "reviews.jsonl", "access_log.jsonl",
            "tombstones.jsonl", ".records.lock",
        }
    assert json.loads((roots[0] / "ratelimit.json").read_text())["daily"]["count"] == 1
    assert storage.conversation_exists("late-0") is False
    retention.delete_session("late-1", "test")
    assert not storage.conversation_exists("late-1")
    assert consent.session_for_delete_code(code) is None
    assert review.read_reviews() == []
    assert stats.read_stats()["totals"]["conversations"] == 0
    assert (roots[0] / "conversations" / date.today().isoformat() / "late-0.json").exists()


def test_explicit_paths_override_data_dir_after_environment_changes(tmp_path, monkeypatch):
    root = tmp_path / "explicit"
    conversations = root / "transcripts"
    database = root / "custom.db"
    limiter = ratelimit.RateLimiter(path=str(root / "custom-rate.json"))
    code = None
    for index in range(2):
        monkeypatch.setenv("DATA_DIR", str(tmp_path / f"unused-{index}"))
        sid = f"explicit-{index}"
        storage.append_turn(sid, "user", "synthetic", base_dir=conversations)
        code = consent.issue_delete_code(sid, base_dir=conversations)
        assert consent.session_for_delete_code(code, base_dir=conversations) == sid
        review.record_review(sid, review.ACTIONS[0], "synthetic", base_dir=conversations)
        access_log.record_access("raw_view", "synthetic", "synthetic", session_id=sid, base_dir=conversations)
        limiter.check("synthetic", sid)
        assert load_to_sqlite.load_day(date.today(), conversations_dir=conversations, db_path=database) == index + 1
        assert storage.conversation_exists(sid, base_dir=conversations)
        assert not paths.data_dir().exists()
        assert stats.read_stats(db_path=database)["totals"]["conversations"] == index + 1
        assert stats.read_session_detail(date.today().isoformat(), sid, db_path=database)["session_id"] == sid
        # Stats still reads reviews in DATA_DIR, under its existing record lock.
        assert list(paths.data_dir().iterdir()) == [paths.records_lock_path()]
    assert json.loads((root / "custom-rate.json").read_text())["daily"]["count"] == 2
    assert len(review.read_reviews(base_dir=conversations)) == 2
    retention.delete_session("explicit-1", "test", base_dir=conversations, db_path=database)
    assert consent.session_for_delete_code(code, base_dir=conversations) is None
    assert stats.read_stats(db_path=database)["totals"]["conversations"] == 1
    assert paths.tombstones_path(conversations).is_file()
    assert list(paths.data_dir().iterdir()) == [paths.records_lock_path()]


def test_import_and_purge_cli_use_current_data_dir(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MODEL", "fake")
    monkeypatch.setenv("KNOWLEDGE_DIR", str(Path(__file__).resolve().parents[1] / "knowledge-maeum"))
    today = date.today()
    day = today - timedelta(days=366)
    records = []
    for name in ("preserved", "purged"):
        root = tmp_path / name
        monkeypatch.setenv("DATA_DIR", str(root))
        path = paths.conversations_dir() / day.isoformat() / f"{name}.json"
        storage._write_private_json(path, {"turns": [{"seq": 0, "role": "user", "text": "synthetic"}]})
        assert load_to_sqlite.main(["--date", day.isoformat()]) == 0
        records.append(path)
    assert purge_expired.main(["--today", today.isoformat()]) == 0
    assert records[0].exists()
    assert not records[1].exists()
    assert stats.read_stats()["totals"]["conversations"] == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["sessions"] == 1


def test_consent_metadata_uses_current_data_dir(monkeypatch, tmp_path):
    session = SimpleNamespace(session_id="consent-path", participant_id="p_test", created_at="2000",
                              consent_pack=str(tmp_path), consented_at=None, consent_version=None)
    privacy = SimpleNamespace(consent_version="synthetic")
    consent.record_consent(session, privacy)
    first = paths.conversations_dir() / date.today().isoformat() / "consent-path.json"
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "other"))
    consent.persist_consent(session)
    second = paths.conversations_dir() / date.today().isoformat() / "consent-path.json"
    assert first != second
    assert json.loads(first.read_text()) == json.loads(second.read_text())
