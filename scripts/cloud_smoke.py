"""Synthetic integration checks against an explicitly selected cloud database.

Credentials are read from a private JSON file or the environment, never argv.
Worker requests and session tokens travel through subprocess pipes. The report
contains check names and counts only. No local conversations are imported.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def worker():
    from fastapi.testclient import TestClient
    from app import cloud_store
    from app.main import app

    request = json.load(sys.stdin)
    if "rate" in request:
        from app.ratelimit import RateLimitExceeded
        try:
            cloud_store.check_rate(request["rate"], request["sid"], request["cap"], 25)
            result = {"status": 200}
        except RateLimitExceeded:
            result = {"status": 429}
    else:
        with TestClient(app, base_url="https://cloud-smoke.invalid") as client:
            response = client.request(request["method"], request["path"], json=request.get("body"))
            result = {"status": response.status_code, "body": response.json()}
    print(json.dumps(result, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker:
        worker()
        return
    if args.config:
        config = json.loads(args.config.read_text())
        os.environ["MAEUM_DATABASE_URL"] = config["MAEUM_DATABASE_URL"]
    if not os.environ.get("MAEUM_DATABASE_URL"):
        parser.error("MAEUM_DATABASE_URL or --config is required")
    os.environ.update(PUBLIC_CHAT_UI="1", PRIVATE_LOCAL_UI="0", VERCEL="1", MODEL="fake",
                      KNOWLEDGE_DIR="knowledge-maeum", DAILY_REQUEST_CAP="10000",
                      PARTICIPANT_TICKET_SECRET=secrets.token_urlsafe(40))
    from app import cloud_store, consent, stats, storage
    prefix = "cloud-smoke-" + uuid.uuid4().hex[:12]
    sid = prefix + "-chat"
    ids = [sid, prefix + "-denied", prefix + "-raw", prefix + "-summary"]
    checks = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    def call(body):
        process = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker"],
                                 input=json.dumps(body), text=True, capture_output=True,
                                 cwd=ROOT, timeout=60, check=False)
        if process.returncode:
            raise RuntimeError("cloud worker failed; no credentials included in report")
        return json.loads(process.stdout)

    def post(path, body):
        return call({"method": "POST", "path": path, "body": body})

    try:
        version = consent.load_privacy("knowledge-maeum").consent_version
        denied = post("/api/consent", {"session_id": ids[1], "accepted": False, "consent_version": version})
        check("consent refusal stores nothing", denied["status"] == 200 and not cloud_store.conversation_exists(ids[1]))
        accepted = post("/api/consent", {"session_id": sid, "accepted": True, "consent_version": version})
        check("consent committed to cloud", accepted["status"] == 200 and cloud_store.get("session", sid) is not None)
        credentials = {key: accepted["body"][key] for key in ("session_token", "participant_id", "participant_ticket")}
        message = {"session_id": sid, **credentials, "message": "회사 일이 많아서 불안해요. 제 이름은 홍길동, 전화 010-1234-5678이에요."}
        first = post("/api/chat", message)
        second = post("/api/chat", {**message, "message": "지난달부터 잠을 잘 못 자고 출근이 힘들어요."})
        check("conversation continues in fresh processes", first["status"] == second["status"] == 200 and second["body"]["turn"] == 2)
        state = cloud_store.get("session", sid)
        serialized = json.dumps(state, ensure_ascii=False)
        check("durable context redacts direct identifiers", "010-1234-5678" not in serialized and "홍길동" not in serialized)
        bad = post("/api/chat", {**message, "session_token": "wrong"})
        check("session ownership survives restart", bad["status"] == 401)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(post, "/api/chat", {**message, "message": "산책을 해보았어요."}) for _ in range(2)]
            replies = [f.result() for f in futures]
        check("concurrent turns do not overwrite each other", sorted(r["body"].get("turn", -1) for r in replies) == [3, 4])
        before = cloud_store.get("session", sid)
        try:
            with cloud_store.session_scope(sid):
                from app import chat
                chat._sessions[sid].turns = 99
                storage.append_turn(sid, "user", "rollback marker")
                raise RuntimeError("synthetic rollback")
        except RuntimeError:
            pass
        check("state and transcript roll back together", cloud_store.get("session", sid) == before and
              all("rollback marker" not in json.dumps(p) for _, p in cloud_store.records("conversation")))
        report = stats.read_stats(session_prefix=prefix)
        check("report reads cloud records", report["totals"]["conversations"] == 1 and report["totals"]["user_turns"] == 4)
        cap = cloud_store.get("rate", "global")["daily"]["count"] + 1
        with ThreadPoolExecutor(max_workers=4) as pool:
            statuses = list(pool.map(lambda i: call({"rate": prefix, "sid": prefix + "-rate-" + str(i), "cap": cap})["status"], range(4)))
        check("global daily cap is atomic across processes", sorted(statuses) == [200, 429, 429, 429])
        check("remote administrator page stays private", call({"method": "GET", "path": "/stats.html"})["status"] == 404)
        check("retention endpoint requires secret", call({"method": "GET", "path": "/api/maintenance/retention"})["status"] == 401)
        deleted = post("/api/session/delete", {"delete_code": accepted["body"]["delete_code"]})
        check("deletion works after process restart", deleted["status"] == 200 and not cloud_store.conversation_exists(sid) and
              cloud_store.get("session", sid) is None and cloud_store.get("delete_code", sid) is None)
        blocked = post("/api/chat", message)
        check("deleted conversation cannot resume", blocked["status"] in (401, 409))
        for old_sid, age in ((ids[2], 91), (ids[3], 367)):
            day = (date.today() - timedelta(days=age)).isoformat()
            cloud_store.put("conversation", day + "/" + old_sid,
                            {"schema_version": 2, "session_id": old_sid, "participant_id": "p_" + uuid.uuid4().hex,
                             "created_at": day + "T00:00:00+00:00", "intake_snapshot": {"track": "증상"},
                             "turns": [{"seq": 0, "role": "user", "text": "synthetic old raw"},
                                       {"seq": 1, "role": "intake_summary", "text": "synthetic summary"}]})
            cloud_store.put("session", old_sid, {"history": ["synthetic context"]})
        cloud_store.purge_expired()
        raw_rows = [p for _, p in cloud_store.records("conversation") if p["session_id"] == ids[2]]
        check("90 day raw retention removes durable context", len(raw_rows) == 1 and raw_rows[0]["raw_purged_at"] and
              all(t["role"] == "intake_summary" for t in raw_rows[0]["turns"]) and cloud_store.get("session", ids[2]) is None)
        check("365 day retention removes summary", not cloud_store.conversation_exists(ids[3]) and cloud_store.get("session", ids[3]) is None)
        with cloud_store.connection() as conn:
            privileges = conn.execute("SELECT has_schema_privilege('anon','maeum','USAGE'), has_table_privilege('authenticated','maeum.records','SELECT'), relrowsecurity FROM pg_class WHERE oid='maeum.records'::regclass").fetchone()
        check("browser database roles cannot read records", privileges == (False, False, True))
        print(json.dumps({"passed": len(checks), "checks": checks, "model": "fake", "synthetic_only": True}, ensure_ascii=False, indent=2))
    finally:
        # Remove only this run's explicitly generated synthetic conversation IDs.
        for own_sid in ids:
            with cloud_store.session_scope(own_sid):
                cloud_store.delete_session(own_sid, "smoke_cleanup")


if __name__ == "__main__":
    main()
