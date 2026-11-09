"""Optional Postgres persistence for the public, API-only cloud deployment.

Each request restores one session under a database advisory transaction lock,
runs the existing conversation engine, and commits state and transcript together.
The process dictionary is only a temporary working copy in this mode. Rate and
authentication limits use separate short transactions, shared by every worker.
No schema changes or local-data imports happen during application startup.
"""

from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading

_local = threading.local()


def enabled():
    return bool(os.environ.get("MAEUM_DATABASE_URL"))


def _connect():
    import psycopg

    tls = {'sslmode': 'require'}
    if os.getenv("PORTAL_ENABLED") == "1":
        from app.portal_store import require_database_url, database_tls
        from app.portal_config import cloud
        require_database_url(os.environ["MAEUM_DATABASE_URL"])
        tls = database_tls()

    conn = psycopg.connect(
        os.environ["MAEUM_DATABASE_URL"],
        connect_timeout=10,
        **tls,
        prepare_threshold=None,  # Supavisor transaction pooling has no prepared statements.
    )
    try:
        from app.portal_config import cloud
        if cloud():
            require_engine_role(conn)
        return conn
    except Exception:
        conn.close()
        raise


def require_engine_role(conn):
    role = conn.execute("SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
    owner = conn.execute("SELECT pg_has_role(current_user,tableowner,'USAGE') FROM pg_tables WHERE schemaname='maeum' AND tablename='records'").fetchone()
    if not role or role[0] != 'maeum_engine' or role[1] or role[2] or not owner or owner[0]:
        raise RuntimeError('Cloud engine requires its restricted non-owner database role')


def _lock(conn, name):
    key = int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "big", signed=True)
    conn.execute("SET LOCAL lock_timeout = '10s'")
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (key,))


@contextmanager
def connection():
    current = getattr(_local, "connection", None)
    if current is not None:
        yield current
    else:
        with _connect() as conn:
            yield conn


@contextmanager
def transaction(name):
    if getattr(_local, "connection", None) is not None:
        yield
        return
    with _connect() as conn:
        _lock(conn, name)
        _local.connection = conn
        try:
            yield
        finally:
            _local.connection = None


def get(kind, key, default=None):
    with connection() as conn:
        row = conn.execute(
            "SELECT payload FROM maeum.records WHERE kind=%s AND record_key=%s",
            (kind, key),
        ).fetchone()
    return row[0] if row else default


def put(kind, key, value):
    from psycopg.types.json import Jsonb

    with connection() as conn:
        conn.execute(
            "INSERT INTO maeum.records (kind, record_key, payload) VALUES (%s,%s,%s) "
            "ON CONFLICT (kind,record_key) DO UPDATE SET payload=excluded.payload, updated_at=now()",
            (kind, key, Jsonb(value)),
        )


def remove(kind, key):
    with connection() as conn:
        conn.execute("DELETE FROM maeum.records WHERE kind=%s AND record_key=%s", (kind, key))


def records(kind):
    with connection() as conn:
        return conn.execute(
            "SELECT record_key,payload FROM maeum.records WHERE kind=%s ORDER BY record_key",
            (kind,),
        ).fetchall()


@contextmanager
def session_scope(session_id):
    """Never overwrite a concurrently changed session: lock before reading it."""
    from app import chat, storage

    if not enabled() or not isinstance(session_id, str) or not storage.valid_session_id(session_id):
        yield
        return
    with transaction("session:" + session_id):
        if os.getenv("PORTAL_ENABLED") == "1":
            with connection() as conn:
                conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (session_id,))
        state = get("session", session_id)
        chat._sessions.pop(session_id, None)
        if state is not None:
            chat._sessions[session_id] = chat.ChatSession(**state)
        try:
            yield
            session = chat._sessions.get(session_id)
            if session is not None:
                # Redact user/model content, not random IDs, tokens or timestamps:
                # an opaque ID can accidentally contain phone-like digit runs.
                state = asdict(session)
                for field in ('history', 'slots', 'handoff', 'center_requests', 'closing_draft',
                              'slot_evidence', 'pending_slot_items', 'attention_notes'):
                    state[field] = storage._redact_obj(state[field])
                pending = state.get('closing_analysis_pending')
                if isinstance(pending, dict):
                    opaque_request_id = pending.get('request_id')
                    state['closing_analysis_pending'] = storage._redact_obj(pending)
                    state['closing_analysis_pending']['request_id'] = opaque_request_id
                revisions = []
                for revision in state.get('slot_revisions', []):
                    if not isinstance(revision, dict):
                        continue
                    opaque_request_id = revision.get('source_request_id')
                    cleaned = storage._redact_obj(revision)
                    cleaned['source_request_id'] = opaque_request_id
                    revisions.append(cleaned)
                state['slot_revisions'] = revisions
                # Idempotency keys and digests are opaque protocol material;
                # generic PII regexes must not rewrite them. Only redact the
                # user/model-bearing fields nested inside each result.
                for request in state.get('request_results', {}).values():
                    if isinstance(request, dict):
                        if 'message_preview' in request:
                            request['message_preview'] = storage._redact_obj(request['message_preview'])
                        if 'result' in request:
                            opaque_request_id = request['result'].get('request_id') if isinstance(request['result'], dict) else None
                            request['result'] = storage._redact_obj(request['result'])
                            if opaque_request_id is not None:
                                request['result']['request_id'] = opaque_request_id
                put("session", session_id, state)
                if os.getenv("PORTAL_ENABLED") == "1":
                    from app.portal_store import project
                    project(session_id)
            else:
                remove("session", session_id)
        finally:
            chat._sessions.pop(session_id, None)


def conversation_exists(session_id):
    with connection() as conn:
        return conn.execute(
            "SELECT 1 FROM maeum.records WHERE kind='conversation' "
            "AND payload->>'session_id'=%s LIMIT 1", (session_id,),
        ).fetchone() is not None


def update_conversation(session_id, participant_id, *, turn=None, turns=None, metadata=None):
    from app import storage

    key = date.today().isoformat() + "/" + session_id
    raw = get("conversation", key, {})
    payload = storage.normalize_conversation_payload(raw, session_id, participant_id)
    incoming = list(turns or ([] if turn is None else [turn]))
    refs = []
    next_seq = max((t["seq"] for t in payload["turns"]), default=-1) + 1
    for role, text in incoming:
        saved_turn = {"seq": next_seq, "role": role, "text": storage.redact_pii(text)}
        payload["turns"].append(saved_turn)
        refs.append({"day": key.split("/", 1)[0], "seq": next_seq, "role": role})
        next_seq += 1
    updates = metadata(refs) if callable(metadata) else metadata
    if updates:
        payload.update(storage._redact_obj(updates))
    put("conversation", key, payload)
    if turns is not None:
        return refs
    if turn is not None:
        return refs[0]


def _retired(session_id, via):
    digest = hashlib.sha256(session_id.encode()).hexdigest()
    put("tombstone", digest, {"deleted_at": datetime.now(timezone.utc).isoformat(), "via": via})


def session_retired(session):
    digest = hashlib.sha256(session.session_id.encode()).hexdigest()
    marker = get("tombstone", digest)
    return bool(marker and marker["deleted_at"] >= session.created_at)


def delete_session(session_id, via):
    from app import chat

    if os.getenv("PORTAL_ENABLED") == "1":
        from app.portal_store import delete_binding
        delete_binding(session_id)

    with connection() as conn:
        deleted = conn.execute(
            "DELETE FROM maeum.records WHERE kind='conversation' "
            "AND payload->>'session_id'=%s RETURNING payload", (session_id,),
        ).fetchall()
        digest = hashlib.sha256(session_id.encode()).hexdigest()
        conn.execute("DELETE FROM maeum.records WHERE kind='reviews' AND payload->>'session_hash'=%s", (digest,))
    remove("delete_code", session_id)
    remove("session", session_id)
    chat._sessions.pop(session_id, None)
    _retired(session_id, via)
    return {"sessions": 1, "files": len(deleted), "turns": sum(len(r[0].get("turns", [])) for r in deleted)}


def purge_expired(*, today=None, dry_run=False, raw_days=90, summary_days=365):
    """Apply the local retention contract to cloud records and durable context."""
    from app import chat
    from app.retention import SUMMARY_ROLES

    today = date.fromisoformat(today) if isinstance(today, str) else today or date.today()
    groups = {}
    for key, payload in records("conversation"):
        groups.setdefault(payload["session_id"], []).append((key, payload))
    targets = []
    for session_id in groups:
        # Re-read after taking the same lock as chat/delete; no stale snapshot writes.
        with transaction("session:" + session_id):
            if os.getenv("PORTAL_ENABLED") == "1":
                with connection() as conn:
                    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (session_id,))
            with connection() as conn:
                rows = conn.execute(
                    "SELECT record_key,payload FROM maeum.records WHERE kind='conversation' "
                    "AND payload->>'session_id'=%s", (session_id,),
                ).fetchall()
            if not rows:
                continue
            days = [date.fromisoformat(key.split("/", 1)[0]) for key, _ in rows]
            for _, payload in rows:
                for field in ("created_at", "consented_at"):
                    if payload.get(field):
                        days.append(datetime.fromisoformat(payload[field]).date())
            age = (today - min(days)).days
            if age <= raw_days:
                continue
            full = age > summary_days
            count = sum(sum(full or t.get("role") not in SUMMARY_ROLES for t in p["turns"]) for _, p in rows)
            if not full and not count and all(p.get("raw_purged_at") for _, p in rows):
                continue
            targets.append({"session_id": session_id, "action": "summary" if full else "raw", "json_turns": count, "sqlite_turns": 0})
            if dry_run:
                continue
            if full:
                delete_session(session_id, "retention_summary")
            else:
                for key, payload in rows:
                    payload["turns"] = [t for t in payload["turns"] if t.get("role") in SUMMARY_ROLES]
                    payload["raw_purged_at"] = today.isoformat()
                    if os.getenv("PORTAL_ENABLED") == "1":
                        # Free-form requests and quotations have the raw retention lifetime.
                        from app.portal_store import retained_summary
                        payload["intake_snapshot"] = retained_summary(payload.get("intake_snapshot", {}))
                        cleaned_turns = []
                        for turn in payload["turns"]:
                            try:
                                value = json.loads(turn["text"])
                            except (ValueError, TypeError):
                                continue  # unstructured raw text is not a retained projection
                            if isinstance(value, dict):
                                cleaned_turns.append({**turn, "text": json.dumps(retained_summary(value), ensure_ascii=False)})
                        payload["turns"] = cleaned_turns
                    put("conversation", key, payload)
                remove("session", session_id)
                chat._sessions.pop(session_id, None)
                _retired(session_id, "retention_raw")
                if os.getenv("PORTAL_ENABLED") == "1":
                    from app.portal_store import project
                    project(session_id)
    return {"dry_run": dry_run, "sessions": len(targets),
            "turns": sum(t["json_turns"] for t in targets), "targets": targets}


def check_rate(ip, session_id, daily_cap, max_per_window):
    """Commit admission separately; an LLM failure still consumes its request budget."""
    from app import ratelimit
    from psycopg.types.json import Jsonb

    with _connect() as conn:
        _lock(conn, "rate-limit")
        row = conn.execute("SELECT payload FROM maeum.records WHERE kind='rate' AND record_key='global'").fetchone()
        state = row[0] if row else {"windows": {}, "known_sessions": {}, "daily": {"date": "", "count": 0}}
        now = datetime.now(timezone.utc)
        def recent(value, window):
            return now - datetime.fromisoformat(value) < window
        known = {sid: ts for sid, ts in state["known_sessions"].items() if recent(ts, ratelimit.KNOWN_SESSION_TTL)}
        windows = {key: [ts for ts in stamps if recent(ts, ratelimit.WINDOW)] for key, stamps in state["windows"].items()}
        windows = {key: stamps for key, stamps in windows.items() if stamps}
        ip_key = hashlib.sha256(ip.encode()).hexdigest()
        stamps = windows.setdefault(ip_key, [])
        daily = state["daily"] if state["daily"]["date"] == now.date().isoformat() else {"date": now.date().isoformat(), "count": 0}
        if daily["count"] >= daily_cap:
            raise ratelimit.RateLimitExceeded(ratelimit.DAILY_CAP_MESSAGE)
        if session_id not in known and len(stamps) >= max_per_window:
            raise ratelimit.RateLimitExceeded(ratelimit.RATE_LIMIT_MESSAGE)
        if session_id not in known:
            stamps.append(now.isoformat())
        known[session_id] = now.isoformat()
        daily["count"] += 1
        state = {"windows": windows, "known_sessions": known, "daily": daily}
        conn.execute(
            "INSERT INTO maeum.records VALUES ('rate','global',%s,now()) "
            "ON CONFLICT (kind,record_key) DO UPDATE SET payload=excluded.payload,updated_at=now()",
            (Jsonb(state),),
        )


def auth_failure(kind, ip, *, record=False, limit=30):
    from app import ratelimit
    from psycopg.types.json import Jsonb

    key = kind + ":" + hashlib.sha256(ip.encode()).hexdigest()
    with _connect() as conn:
        _lock(conn, "auth:" + key)
        row = conn.execute("SELECT payload FROM maeum.records WHERE kind='auth' AND record_key=%s", (key,)).fetchone()
        now = datetime.now(timezone.utc)
        stamps = [ts for ts in (row[0] if row else []) if now - datetime.fromisoformat(ts) < ratelimit.WINDOW]
        if record:
            stamps.append(now.isoformat())
        conn.execute(
            "INSERT INTO maeum.records VALUES ('auth',%s,%s,now()) "
            "ON CONFLICT (kind,record_key) DO UPDATE SET payload=excluded.payload,updated_at=now()",
            (key, Jsonb(stamps)),
        )
        return len(stamps) < limit


@contextmanager
def stats_snapshot():
    """Reuse the existing report queries over a disposable, private projection."""
    from scripts.load_to_sqlite import _ensure_schema

    with tempfile.TemporaryDirectory(prefix="maeum-stats-") as directory:
        path = Path(directory) / "report.db"
        with sqlite3.connect(path) as conn:
            _ensure_schema(conn)
            for key, payload in records("conversation"):
                day = key.split("/", 1)[0]
                sid, pid = payload["session_id"], payload["participant_id"]
                conn.execute("INSERT OR IGNORE INTO participants VALUES (?)", (pid,))
                conn.execute("INSERT INTO conversations VALUES (?,?,?)", (day, sid, pid))
                turns = list(payload["turns"])
                if isinstance(payload.get("intake_snapshot"), dict):
                    turns.append({"seq": max((t["seq"] for t in turns), default=-1) + 1,
                                  "role": "intake_snapshot", "text": json.dumps(payload["intake_snapshot"], ensure_ascii=False)})
                conn.executemany("INSERT INTO turns VALUES (?,?,?,?,?)",
                                 [(day, sid, t["seq"], t["role"], t["text"]) for t in turns])
        os.chmod(path, 0o600)
        yield path
