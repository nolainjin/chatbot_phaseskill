"""Test-link HTTP authorization with isolated auth/DB adapters; no live DB."""
from contextlib import contextmanager
import re

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app import portal


@pytest.fixture
def isolated_portal(monkeypatch):
    statements, scopes, audits = [], [], []

    class Connection:
        def execute(self, sql, args):
            statements.append((sql, args))

    @contextmanager
    def connect():
        yield Connection()

    def session(conn, request):
        if request.headers.get("X-Test-Role") == "anonymous":
            raise HTTPException(401, "Login required")
        return {"user_id": request.headers.get("X-Test-Role", "issuer"),
                "token_hash": "synthetic-session", "csrf": "synthetic-csrf"}

    def context(conn, user, org, permission, token):
        scopes.append((user, org, permission, token))
        if user != "issuer" or org != "A" or permission != "link:issue":
            raise HTTPException(403, "No institution permission")

    def registrar(conn, request):
        raise HTTPException(403, "No global administrator permission")

    monkeypatch.setenv("PORTAL_ORIGIN", "http://testserver")
    monkeypatch.setattr(portal.store, "connect", connect)
    monkeypatch.setattr(portal.auth, "connect", connect)
    monkeypatch.setattr(portal.auth, "session", session)
    monkeypatch.setattr(portal.store, "context", context)
    monkeypatch.setattr(portal.store, "audit", lambda *args: audits.append(args[1:]))
    monkeypatch.setattr(portal.portal_email, "registrar", registrar)
    app = FastAPI()
    app.include_router(portal.router)
    client = TestClient(app)
    client.headers.update({"Origin": "http://testserver", "X-CSRF-Token": "synthetic-csrf"})
    return client, statements, scopes, audits


def test_issuer_gets_unique_synthetic_links_without_global_admin(isolated_portal):
    client, statements, scopes, audits = isolated_portal
    first = client.post("/api/portal/institutions/testbed", json={"org_id": "A", "management_id": "REAL-1"})
    second = client.post("/api/portal/institutions/testbed", json={"org_id": "A"})
    assert first.status_code == second.status_code == 200
    a, b = first.json(), second.json()
    assert a["synthetic"] is True
    assert re.fullmatch(r"TEST-[A-F0-9]{12}", a["management_id"])
    assert a["management_id"] != b["management_id"]
    assert a["url"].startswith("http://testserver/#intake=")
    assert a["url"] != b["url"]
    assert all(scope[1:3] == ("A", "link:issue") for scope in scopes)
    assert statements[0][1][3] == a["management_id"]
    assert statements[0][1][2] not in a["url"]
    assert len(audits) == 2 and audits[0][2] == "link_issue"
    assert client.post("/api/portal/testbed", json={"org_id": "A"}).status_code == 403


@pytest.mark.parametrize("role,org,expected", [("anonymous", "A", 401), ("summary", "A", 403), ("issuer", "B", 403)])
def test_unauthorized_requests_make_no_writes(isolated_portal, role, org, expected):
    client, statements, scopes, audits = isolated_portal
    result = client.post("/api/portal/institutions/testbed", json={"org_id": org}, headers={"X-Test-Role": role})
    assert result.status_code == expected
    assert not statements and not audits


@pytest.mark.parametrize("headers", [{"Origin": "https://untrusted.example"}, {"X-CSRF-Token": "wrong"}])
def test_real_csrf_check_is_retained(isolated_portal, headers):
    client, statements, scopes, audits = isolated_portal
    assert client.post("/api/portal/institutions/testbed", json={"org_id": "A"}, headers=headers).status_code == 403
    assert not statements and not scopes and not audits


@pytest.mark.parametrize("org", [None, "", {}, "x" * 129])
def test_invalid_org_is_rejected(isolated_portal, org):
    client, statements, scopes, audits = isolated_portal
    assert client.post("/api/portal/institutions/testbed", json={"org_id": org}).status_code == 400
    assert not statements and not audits
