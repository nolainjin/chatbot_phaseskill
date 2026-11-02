"""Local record deletion and deterministic, session-wide retention enforcement."""

import hashlib
import json
import sqlite3
from contextlib import nullcontext
from datetime import date, datetime, timezone
from pathlib import Path

from app import consent, paths, review, storage
from app.config import Settings

SUMMARY_ROLES = ("intake_summary", "intake_snapshot")


def _db_path(db_path=None):
    if db_path is None:
        return paths.db_path()
    return Path(db_path)


def _connect(db_path):
    if not db_path.exists():
        return None
    from scripts.load_to_sqlite import _ensure_schema
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA secure_delete=ON")
    _ensure_schema(conn)
    return conn


def _remove_sql(conn, session_id, raw_only=False):
    if conn is None:
        return 0
    if raw_only:
        count = conn.execute("DELETE FROM turns WHERE session_id=? AND role NOT IN (?, ?)", (session_id, *SUMMARY_ROLES)).rowcount
    else:
        participants = conn.execute("SELECT DISTINCT participant_id FROM conversations WHERE session_id=?", (session_id,)).fetchall()
        count = conn.execute("DELETE FROM turns WHERE session_id=?", (session_id,)).rowcount
        conn.execute("DELETE FROM conversations WHERE session_id=?", (session_id,))
        conn.executemany("DELETE FROM participants WHERE participant_id=? AND participant_id NOT IN (SELECT participant_id FROM conversations)", participants)
    conn.commit()
    return count


def tombstone(session_id, via, base_dir=None):
    path = paths.tombstones_path(base_dir)
    entry = {"session_hash": hashlib.sha256(session_id.encode("utf-8")).hexdigest(),
             "deleted_at": datetime.now(timezone.utc).isoformat(), "via": via}
    previous = path.read_text(encoding="utf-8") if path.exists() else ""
    storage._write_private_text(path, previous + json.dumps(entry) + "\n")


def session_retired(session):
    """Invalidate live state if another local process purged/deleted its records."""
    path = paths.tombstones_path()
    if not path.exists():
        return False
    digest = hashlib.sha256(session.session_id.encode("utf-8")).hexdigest()
    return any(r["session_hash"] == digest and r["deleted_at"] >= session.created_at
               for r in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line))


def delete_session(session_id, via, base_dir=None, db_path=None):
    if not isinstance(session_id, str) or not storage.valid_session_id(session_id):
        raise ValueError("Invalid session id")
    root = paths.conversations_dir(base_dir)
    with storage.data_lock(root):
        review.remove_reviews(session_id, root)
        files = list(root.glob(f"*/{session_id}.json"))
        conn = _connect(_db_path(db_path))
        try:
            turns = _remove_sql(conn, session_id)
        finally:
            if conn is not None:
                conn.close()
        for path in files:
            path.unlink()
        consent.remove_delete_code(session_id, root)
        from app import chat
        chat._sessions.pop(session_id, None)
        tombstone(session_id, via, root)
    return {"sessions": 1, "files": len(files), "turns": turns}


def purge_expired(*, today=None, dry_run=False, base_dir=None, db_path=None, raw_days=None, summary_days=None):
    """Age starts at the earliest session day, never at a subsequent import/write."""
    settings = Settings.from_env()
    consent.load_privacy(settings.knowledge_dir, settings)
    raw_days = settings.retention_raw_days if raw_days is None else raw_days
    summary_days = settings.retention_summary_days if summary_days is None else summary_days
    if type(raw_days) is not int or type(summary_days) is not int or not 0 < raw_days <= summary_days:
        raise ValueError("Invalid retention periods")
    today = today or date.today()
    if isinstance(today, str):
        today = date.fromisoformat(today)
    root = paths.conversations_dir(base_dir)
    database = _db_path(db_path)
    with nullcontext() if dry_run else storage.data_lock(root):
        sessions = {}
        for path in sorted(root.glob("*/*.json")):
            if not storage.valid_session_id(path.stem):
                continue
            day = date.fromisoformat(path.parent.name)
            record = sessions.setdefault(path.stem, {"days": [], "files": [], "sql_turns": []})
            record["days"].append(day)
            payload = storage.normalize_conversation_payload(json.loads(path.read_text(encoding="utf-8")), path.stem)
            for key in ("created_at", "consented_at"):
                if isinstance(payload.get(key), str):
                    record["days"].append(datetime.fromisoformat(payload[key]).date())
            record["files"].append((path, payload))
        # Read-only mode also prevents SQLite journals/schema migrations in dry-run.
        conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) if database.exists() else None
        try:
            if conn is not None:
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type=?", ("table",))}
                if "conversations" in tables:
                    for sid, day in conn.execute("SELECT session_id, date FROM conversations"):
                        record = sessions.setdefault(sid, {"days": [], "files": [], "sql_turns": []})
                        record["days"].append(date.fromisoformat(day))
                if "turns" in tables:
                    for sid, role in conn.execute("SELECT session_id, role FROM turns"):
                        if sid in sessions:
                            sessions[sid]["sql_turns"].append(role)
        finally:
            if conn is not None:
                conn.close()
        targets = []
        for sid, record in sorted(sessions.items()):
            age = (today - min(record["days"])).days
            if age <= raw_days:
                continue
            full = age > summary_days
            json_turns = sum(sum(full or t.get("role") not in SUMMARY_ROLES for t in payload["turns"]) for _, payload in record["files"])
            sql_turns = sum(full or role not in SUMMARY_ROLES for role in record["sql_turns"])
            unmarked = any(not payload.get("raw_purged_at") for _, payload in record["files"])
            if not full and not (json_turns or sql_turns or unmarked):
                continue
            targets.append({"session_id": sid, "action": "summary" if full else "raw", "json_turns": json_turns, "sqlite_turns": sql_turns})
            if dry_run:
                continue
            if full:
                delete_session(sid, "retention_summary", root, database)
            else:
                conn = _connect(database)
                try:
                    _remove_sql(conn, sid, raw_only=True)
                finally:
                    if conn is not None:
                        conn.close()
                for path, payload in record["files"]:
                    payload["turns"] = [t for t in payload["turns"] if t.get("role") in SUMMARY_ROLES]
                    payload["raw_purged_at"] = today.isoformat()
                    storage._write_private_json(path, payload)
                from app import chat
                chat._sessions.pop(sid, None)
                tombstone(sid, "retention_raw", root)
        return {"dry_run": dry_run, "sessions": len(targets),
                "turns": sum(t["json_turns"] + t["sqlite_turns"] for t in targets), "targets": targets}
