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
                               "request_results"}}
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


def consent_scope(request, payload, callback):
    """Lock link before consumption, then create consent+binding+projection atomically."""
    from app import chat
    token = request.cookies.get("maeum_link")
    sid = payload.get("session_id")
    idem = payload.get("idempotency_key")
    if not isinstance(idem, str) or not 16 <= len(idem) <= 128:
        raise HTTPException(400, "접수 요청 키가 필요합니다.")
    with cloud_store.transaction("link:" + digest(token or "")):
        link_id, org_id, management, consumed = link_for_token(token, lock=True, allow_consumed=True)
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
                if (key.startswith("center_request:") and isinstance(source, dict)
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
