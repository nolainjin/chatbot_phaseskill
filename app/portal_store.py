"""Tenant data boundary; portal reads use a non-owner, NOBYPASSRLS connection."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlparse
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from fastapi import HTTPException

from app import cloud_store, portal_config, report_quality


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def retained_summary(value):
    """Strip raw quotations from both metadata and serialized summary turns."""
    if isinstance(value, dict):
        return {key: retained_summary(item) for key, item in value.items()
                if key not in {"center_requests", "sources", "quotes", "source_turns",
                               "slot_evidence", "slot_revisions", "source_text",
                               "request_results", "attention_notes"}}
    if isinstance(value, list):
        return [retained_summary(item) for item in value]
    return value


def projected_summary(value):
    """Build the active report projection without copying raw/cache fields."""
    if not isinstance(value, dict):
        return value
    projected = {key: item for key, item in value.items()
                 if key not in {"request_results", "source_text", "quotes"}}
    evidence = value.get("slot_evidence")
    if isinstance(evidence, dict):
        projected["slot_evidence"] = {
            key: {field: item[field] for field in (
                "status", "value", "source", "source_turn", "updated_at", "category", "label"
            ) if field in item}
            for key, item in evidence.items() if isinstance(item, dict)
        }
    revisions = value.get("slot_revisions")
    if isinstance(revisions, list):
        safe_revisions = []
        for item in revisions:
            if not isinstance(item, dict):
                continue
            safe = {field: item[field] for field in ("field", "source_turn") if field in item}
            source = item.get("source")
            if (isinstance(source, dict) and isinstance(source.get("day"), str)
                    and isinstance(source.get("seq"), int) and source.get("role") == "user"):
                safe["source"] = {"day": source["day"], "seq": source["seq"], "role": "user"}
            safe_revisions.append(safe)
        projected["slot_revisions"] = safe_revisions
    return projected


def require_local_url(url):
    parsed = urlparse(url)
    if (not portal_config.local_only() or parsed.hostname not in {"127.0.0.1", "localhost"}
            or not parsed.path.startswith("/maeum_test_")):
        raise RuntimeError("Local portal requires a loopback maeum_test_ database")


def require_database_url(url):
    if not portal_config.cloud():
        return require_local_url(url)
    portal_config.validate_cloud()
    parsed = urlparse(url)
    if (parsed.scheme not in {'postgres', 'postgresql'}
            or parsed.hostname != 'aws-0-ap-northeast-2.pooler.supabase.com'
            or not (parsed.username or '').endswith('.ojhuuipsyxewtiubujom')
            or parsed.path != '/postgres'):
        raise RuntimeError('Unexpected cloud database target')


def database_tls():
    if not portal_config.cloud():
        return {'sslmode': 'disable'}
    return {'sslmode': 'verify-full', 'sslrootcert': str(Path(__file__).resolve().parents[1] / 'deploy/supabase-ca.crt')}


@contextmanager
def connect(*, authentication=False):
    url = os.environ["PORTAL_AUTH_DATABASE_URL" if authentication else "PORTAL_DATABASE_URL"]
    require_database_url(url)
    with psycopg.connect(url, **database_tls(), prepare_threshold=None,
                         row_factory=dict_row, connect_timeout=5) as conn:
        # Do not silently use an owner/service connection for the portal.
        role = conn.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
        owner = conn.execute("SELECT pg_has_role(current_user,tableowner,'USAGE') AS owner FROM pg_tables WHERE schemaname='maeum' AND tablename='intakes'").fetchone()
        if role["rolsuper"] or role["rolbypassrls"] or owner["owner"]:
            raise RuntimeError("Portal database role must be a non-owner without BYPASSRLS")
        expected = 'maeum_auth' if authentication else 'maeum_portal'
        if conn.execute('SELECT current_user AS role').fetchone()['role'] != expected:
            raise RuntimeError('Unexpected portal database role')
        yield conn


def context(conn, user_id, org_id, permission, session_hash=""):
    conn.execute("SELECT set_config('maeum.user',%s,true),set_config('maeum.org',%s,true)",
                 (user_id, org_id))
    conn.execute("SELECT set_config('maeum.session',%s,true),set_config('maeum.idle_seconds',%s,true)",
                 (session_hash, str(portal_config.session_idle_seconds())))
    if not conn.execute("SELECT maeum.permitted(%s,%s) AS ok", (org_id, permission)).fetchone()["ok"]:
        raise HTTPException(403, "기관 권한이 없습니다.")


def audit(conn, org_id, user_id, action, target, outcome="allowed"):
    conn.execute("INSERT INTO maeum.audit_events(org_id,actor_id,action,target_hash,outcome) VALUES(%s,%s,%s,%s,%s)",
                 (org_id, user_id, action, digest(target), outcome))


def link_for_token(token, *, lock=False, allow_consumed=False):
    if not isinstance(token, str) or not 32 <= len(token) <= 128:
        raise HTTPException(410, "접수 링크를 사용할 수 없습니다.")
    with cloud_store.connection() as conn:
        row = conn.execute(
            "SELECT l.id,l.org_id,l.management_id,l.consumed_intake_id FROM maeum.intake_links l "
            "JOIN maeum.organizations o ON o.id=l.org_id WHERE l.token_hash=%s "
            "AND NOT l.revoked AND l.expires_at>%s AND o.active" + (" FOR UPDATE OF l" if lock else ""),
            (digest(token), time.time())).fetchone()
        if row is None or (row[3] and not allow_consumed):
            raise HTTPException(410, "접수 링크를 사용할 수 없습니다.")
        return row


# Shared review link: an administrator creates a link whose management id starts with OPEN-
# directly in the database. It is never consumed itself; every visit gets a fresh single-use
# TRY-<name>-<parent hash>-… link of the same organization, so many reviewers can use one URL.
# The parent hash keeps each shared link's children apart even when names overlap; staff cannot
# issue OPEN- or TRY- ids. To stop a shared link, revoke the parent; per-visit links it already
# handed out live at most REUSABLE_CHILD_SECONDS.
REUSABLE_PREFIX = "OPEN-"
RESERVED_PREFIXES = (REUSABLE_PREFIX, "TRY-")
REUSABLE_CHILD_LIMIT = 300
REUSABLE_CHILD_SECONDS = 24 * 3600


def reusable(management):
    return isinstance(management, str) and management.startswith(REUSABLE_PREFIX)


def _child_base(parent_id, management):
    return "TRY-" + management[len(REUSABLE_PREFIX):][:8] + "-" + digest(parent_id)[:8].upper()


def _children(parent_id, management):
    """SQL condition on alias l for one shared link's per-visit links, including those minted on
    2026-11-10 morning as TRY-<name>-<8 hex> before the parent hash was added (names are unique)."""
    legacy = "^TRY-" + management[len(REUSABLE_PREFIX):][:20] + "-[0-9A-F]{8}$"
    return "(l.management_id LIKE %s OR l.management_id ~ %s)", [_child_base(parent_id, management) + "-%", legacy]


def issue_reusable_child(parent_id, org_id, management, link_seconds):
    """Mint one single-use link under a shared review link and return its raw token."""
    base = _child_base(parent_id, management)
    token = secrets.token_urlsafe(32)
    with cloud_store.transaction("reusable-link:" + parent_id):
        with cloud_store.connection() as conn:
            parent = conn.execute("SELECT expires_at FROM maeum.intake_links WHERE id=%s AND org_id=%s "
                                  "AND NOT revoked AND expires_at>%s", (parent_id, org_id, time.time())).fetchone()
            condition, params = _children(parent_id, management)
            issued = conn.execute("SELECT count(*) FROM maeum.intake_links l WHERE l.org_id=%s AND " + condition,
                                  [org_id, *params]).fetchone()[0]
            if parent is None or issued >= REUSABLE_CHILD_LIMIT:
                raise HTTPException(410, "접수 링크를 사용할 수 없습니다.")
            conn.execute("INSERT INTO maeum.intake_links(id,org_id,token_hash,management_id,expires_at) VALUES(%s,%s,%s,%s,%s)",
                         (str(uuid4()), org_id, digest(token), base + "-" + secrets.token_hex(4).upper(),
                          min(parent[0], time.time() + min(link_seconds, REUSABLE_CHILD_SECONDS))))
    return token


def _shared_summary(summary, raw_expired):
    """Only what the shared view shows: slot values and states, attention notes, center requests."""
    if not isinstance(summary, dict):
        return {}
    if raw_expired:
        summary = retained_summary(summary)
    plain = lambda value: isinstance(value, str) or (isinstance(value, list) and all(isinstance(v, str) for v in value))
    slots = summary.get("slots") if isinstance(summary.get("slots"), dict) else {}
    evidence = summary.get("slot_evidence") if isinstance(summary.get("slot_evidence"), dict) else {}
    return {
        "slots": {key: value for key, value in slots.items() if plain(value)},
        "slot_evidence": {key: {field: item[field] for field in ("status", "value") if plain(item.get(field))}
                          for key, item in evidence.items() if isinstance(item, dict)},
        "attention_notes": [{"text": note["text"]} for note in summary.get("attention_notes") or []
                            if isinstance(note, dict) and isinstance(note.get("text"), str)],
        "center_requests": [{field: item[field] for field in ("label", "category", "text", "status") if isinstance(item.get(field), str)}
                            for item in summary.get("center_requests") or [] if isinstance(item, dict)],
    }


def shared_review_cases(org_id, parent_id, management, limit=30):
    """Newest cases opened through one shared review link: report summary and conversation turns.
    Anyone holding the shared link may read them (두찬 11/10); other cases of the org stay hidden."""
    condition, params = _children(parent_id, management)
    with cloud_store.connection() as conn:
        rows = conn.execute(
            "SELECT i.session_id,i.management_id,i.created_at,r.summary,r.status,r.raw_expired "
            "FROM maeum.intakes i JOIN maeum.intake_links l ON l.id=i.link_id AND l.org_id=i.org_id "
            "LEFT JOIN maeum.report_snapshots r ON r.intake_id=i.id AND r.org_id=i.org_id "
            "WHERE i.org_id=%s AND " + condition + " ORDER BY i.created_at DESC LIMIT %s",
            [org_id, *params, limit]).fetchall()
        documents = conn.execute(
            "SELECT payload->>'session_id',payload FROM maeum.records WHERE kind='conversation' "
            "AND payload->>'session_id' = ANY(%s) ORDER BY record_key", ([row[0] for row in rows],)).fetchall() if rows else []
    by_session = {}
    for session_id, document in documents:
        by_session.setdefault(session_id, []).append(document)
    cases = []
    for session_id, case_id, created_at, summary, status, raw_expired in rows:
        turns = []
        for document in [] if raw_expired else by_session.get(session_id, []):
            if document.get("raw_purged_at"):
                raw_expired, turns = True, []
                break
            turns += [{"role": turn["role"], "text": turn["text"]} for turn in document.get("turns") or []
                      if turn.get("role") in ("user", "assistant") and isinstance(turn.get("text"), str)]
        cases.append({"case": case_id, "created_at": created_at, "status": status or "draft",
                      "summary": _shared_summary(summary, raw_expired), "turns": turns})
    return cases


def consent_scope(request, payload, callback):
    """Lock link before consumption, then create consent+binding+projection atomically."""
    from app import chat
    # Each tab names the link it exchanged, so another tab's cookie cannot decide which link
    # (and organization) this consent consumes. Without it, the cookie is used as before.
    tab_link = payload.pop("link_token", None)
    token = tab_link if isinstance(tab_link, str) and tab_link else request.cookies.get("maeum_link")
    sid = payload.get("session_id")
    idem = payload.get("idempotency_key")
    if not isinstance(idem, str) or not 16 <= len(idem) <= 128:
        raise HTTPException(400, "접수 요청 키가 필요합니다.")
    with cloud_store.transaction("link:" + digest(token or "")):
        link_id, org_id, management, consumed = link_for_token(token, lock=True, allow_consumed=True)
        if reusable(management):
            # Only the per-visit TRY-… link is ever consumed; the shared link stays open for everyone.
            raise HTTPException(410, "접수 링크를 사용할 수 없습니다.")
        if payload.get("accepted") is False:
            return callback(request, payload)
        with cloud_store.session_scope(sid):
            with cloud_store.connection() as conn:
                if consumed:
                    row = conn.execute("SELECT id,session_id,idempotency_hash FROM maeum.intakes WHERE id=%s AND org_id=%s",
                                       (consumed, org_id)).fetchone()
                    if (row and row[1] == sid and row[2] == digest(idem)
                            and chat.owns_session(sid, payload.get("session_token"))):
                        return {"accepted": True, "intake_id": row[0], "resumed": True}
                    raise HTTPException(410, "접수 링크를 사용할 수 없습니다.")
                # No client-supplied org, participant or old v1 credentials control ownership.
                clean = {k: v for k, v in payload.items() if k not in {"management_id", "link_ticket", "org_id"}}
                result = callback(request, clean)
                # The chatbot names the receiving center when the client asks who sees the story.
                named = conn.execute("SELECT name FROM maeum.organizations WHERE id=%s", (org_id,)).fetchone()
                if named and sid in chat._sessions:
                    chat._sessions[sid].center_name = named[0]
                intake_id = str(uuid4())
                conn.execute("INSERT INTO maeum.intakes(id,org_id,link_id,session_id,management_id,consent_version,idempotency_hash) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                             (intake_id, org_id, link_id, sid, management, payload["consent_version"], digest(idem)))
                conn.execute("UPDATE maeum.intake_links SET consumed_intake_id=%s WHERE id=%s", (intake_id, link_id))
                result["intake_id"] = intake_id
                project(sid)
                return result


def project(session_id):
    """Called inside the existing engine transaction; no model calls on report reads."""
    if not portal_config.enabled():
        return
    with cloud_store.connection() as conn:
        binding = conn.execute("SELECT id,org_id FROM maeum.intakes WHERE session_id=%s", (session_id,)).fetchone()
        if not binding:
            return  # legacy/unassigned conversations never enter the portal
        rows = conn.execute("SELECT record_key,payload FROM maeum.records WHERE kind='conversation' AND payload->>'session_id'=%s ORDER BY record_key", (session_id,)).fetchall()
        summary = {}
        expired = False
        for _, payload in rows:
            if isinstance(payload.get("intake_snapshot"), dict):
                summary = payload["intake_snapshot"]
            expired = expired or bool(payload.get("raw_purged_at"))
        if expired:
            # Old projections may predate the current retention scrub.  Never
            # re-publish their raw provenance after the transcript boundary.
            summary = retained_summary(summary)
        revision = digest(json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str))
        sources = {}
        if not expired:
            for slot, value in summary.get("slots", {}).items():
                evidence = summary.get("slot_evidence", {}).get(slot, {})
                source = evidence.get("source") if isinstance(evidence, dict) else None
                if (isinstance(source, dict) and isinstance(source.get("day"), str)
                        and isinstance(source.get("seq"), int) and source.get("role") == "user"):
                    sources[slot] = [source]
                    continue
                if isinstance(value, str) and len(value.strip()) >= 4:
                    matches = [{"day": key.split("/")[0], "seq": t["seq"]}
                               for key, p in rows for t in p.get("turns", [])
                               if t.get("role") == "user" and value in t.get("text", "")]
                    if matches:
                        sources[slot] = matches
            for key, evidence in summary.get("slot_evidence", {}).items():
                source = evidence.get("source") if isinstance(evidence, dict) else None
                if (key.startswith(("center_request:", "attention:")) and isinstance(source, dict)
                        and isinstance(source.get("day"), str)
                        and isinstance(source.get("seq"), int) and source.get("role") == "user"):
                    sources[key] = [source]
        status = "complete" if summary.get("handoff", {}).get("sent") else "in_progress"
        # Report snapshots are retained projections, never a second raw store.
        # Provenance pointers are materialized separately in `sources` below.
        project_summary = projected_summary(summary)
        conn.execute("INSERT INTO maeum.report_snapshots(org_id,intake_id,version,source_revision,summary,status,raw_expired) VALUES(%s,%s,1,%s,%s,%s,%s) "
                     "ON CONFLICT(intake_id) DO UPDATE SET version=maeum.report_snapshots.version+1,source_revision=excluded.source_revision,summary=excluded.summary,status=excluded.status,raw_expired=excluded.raw_expired,updated_at=now() "
                     "WHERE maeum.report_snapshots.source_revision<>excluded.source_revision",
                     (binding[1], binding[0], revision, Jsonb(project_summary), status, expired))
        conn.execute("UPDATE maeum.report_snapshots SET sources=%s WHERE intake_id=%s", (Jsonb(sources), binding[0]))


def delete_binding(session_id):
    if portal_config.enabled():
        with cloud_store.connection() as conn:
            # Keep the spent link as revoked; never make it reusable after deletion.
            conn.execute("UPDATE maeum.intake_links SET revoked=true,consumed_intake_id=NULL WHERE consumed_intake_id IN (SELECT id FROM maeum.intakes WHERE session_id=%s)", (session_id,))
            conn.execute("DELETE FROM maeum.intakes WHERE session_id=%s", (session_id,))


def require_bound_session(session_id):
    if portal_config.enabled():
        with cloud_store.connection() as conn:
            row = conn.execute("SELECT 1 FROM maeum.intakes i JOIN maeum.organizations o ON o.id=i.org_id WHERE i.session_id=%s AND o.active", (session_id,)).fetchone()
            if not row:
                raise HTTPException(403, "유효한 기관 접수가 필요합니다.")


def detail(conn, org_id, intake_id):
    row = conn.execute("SELECT i.id,i.management_id,i.created_at,r.summary,r.version,r.source_revision,r.updated_at,r.status,r.raw_expired,r.sources "
                       "FROM maeum.intakes i JOIN maeum.report_snapshots r ON r.intake_id=i.id AND r.org_id=i.org_id "
                       "WHERE i.org_id=%s AND i.id=%s", (org_id, intake_id)).fetchone()
    if not row:
        raise HTTPException(404, "접수 기록을 찾을 수 없습니다.")
    if row.get("raw_expired") and isinstance(row.get("summary"), dict):
        # Read-time defense for legacy report_snapshots persisted before the
        # retention scrub was introduced. A later project() call repairs it.
        row["summary"] = retained_summary(row["summary"])
        row["sources"] = {}
    elif isinstance(row.get("summary"), dict):
        documents = None
        raw_boundary_hit = False
        permitted = conn.execute(
            "SELECT maeum.permitted(%s,%s) AS ok", (org_id, "raw:read")
        ).fetchone()
        if permitted and permitted.get("ok"):
            raw_rows = conn.execute(
                "SELECT maeum.read_transcript(%s) AS document", (intake_id,)
            ).fetchall()
            documents = [item["document"] for item in raw_rows]
            if any(isinstance(document, dict) and document.get("raw_purged_at")
                   for document in documents):
                row["summary"] = retained_summary(row["summary"])
                row["sources"] = {}
                row["raw_expired"] = True
                documents = None
                raw_boundary_hit = True
        if not raw_boundary_hit:
            projection = report_quality.project(row["summary"], row.get("sources") or {}, documents)
            row["summary"] = projection["summary"]
            row["sources"] = projection["sources"]
    row["reviews"] = conn.execute("SELECT actor_id,status,created_at FROM maeum.portal_reviews WHERE org_id=%s AND intake_id=%s ORDER BY created_at,id", (org_id, intake_id)).fetchall()
    return row
