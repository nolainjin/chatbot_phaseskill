"""UI-01 browser fixture: synthetic data only; no DB, model or auth services.

Run: python3 scripts/gui-smoke/ui01-fixture.py --port 8802
26 synthetic cases: 22 expired, 23 HTTP 500, 24 HTTP 401, 25 HTTP 403,
26 delayed response. Organization B has report-only permission.
"""
import argparse
import json
import mimetypes
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

STATIC = Path(__file__).resolve().parents[2] / "static"
NOW = "2026-11-05T03:00:00Z"
ORGS = [
    {"id": "synthetic-a", "name": "합성 A 기관", "permissions": ["report:read", "raw:read", "review:write"]},
    {"id": "synthetic-b", "name": "합성 B 기관", "permissions": ["report:read"]},
]


def case(number):
    return {"id": str(number), "management_id": f"TEST-UI01-{number:02}",
            "status": "complete", "review_status": "unreviewed", "updated_at": NOW,
            "created_at": NOW, "version": 1, "reviews": []}


def report(number):
    return {**case(number), "raw_expired": number == 22,
            "summary": {"slots": {"chief_complaint": "합성 사례: 발표 전 걱정이 있습니다.",
                                   "expectation": "걱정을 다루는 방법을 배우고 싶습니다."}},
            "slot_labels": {"chief_complaint": "호소 문제", "expectation": "상담 기대"},
            "sources": {"chief_complaint": [{"day": "2026-11-05", "seq": 1}]}}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/api/portal/auth/logout" or self.path.endswith("/review"):
            self.send({})
        else:
            self.send({"detail": "fixture endpoint not implemented"}, 404)

    def do_GET(self):
        parsed = urlsplit(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        if path == "/api/portal/me":
            return self.send({"csrf": "synthetic-only", "state": "verified", "organizations": ORGS,
                              "registrar": False, "account_changes": False})
        if path == "/api/portal/summary":
            return self.send({"total": 26, "complete": 26, "unreviewed": 26})
        if path == "/api/portal/devices":
            return self.send([])
        if path == "/api/portal/intakes":
            search = query.get("search", [""])[0]
            offset = int(query.get("offset", [0])[0])
            items = [case(n) for n in range(1, 27) if search in case(n)["management_id"]]
            return self.send({"items": items[offset:offset + 20]})
        if path.startswith("/api/portal/intakes/"):
            parts = path.split("/")
            number = int(parts[4])
            if path.endswith("/transcript"):
                return self.send({"documents": [{"day": "2026-11-05", "turns": [
                    {"seq": 1, "role": "user", "text": "합성 원문: 발표 전 걱정이 있습니다."}]}]})
            if number in (23, 24, 25):
                return self.send({"detail": "합성 오류 응답"}, {23: 500, 24: 401, 25: 403}[number])
            if number == 26:
                time.sleep(1.5)
            return self.send(report(number))
        if path == "/api/config":
            return self.send({"mode": "intake", "intake_schema": True, "consent_required": False,
                              "ui": {"title": "마음 접수 · 합성 화면", "greeting": "요즘 마음에 걸리는 일이 있나요?"}})
        relative = "portal/index.html" if path == "/portal" else "index.html" if path == "/" else path.lstrip("/")
        target = (STATIC / relative).resolve()
        if not target.is_relative_to(STATIC) or not target.is_file():
            return self.send({"detail": "not found"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target)[0] or "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(target.read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8802)
    args = parser.parse_args()
    print(f"Synthetic UI fixture: http://127.0.0.1:{args.port}/portal", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
