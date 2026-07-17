import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """TestClient 피크스처."""
    return TestClient(app)


def test_config_with_schema(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_DIR", "knowledge")
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {"mode": "intake", "intake_schema": True, "ui": {}}


def test_config_with_starter_pack_schema(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_DIR", "knowledge-alt")
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {"mode": "intake", "intake_schema": True, "ui": {}}


def test_config_without_schema_fixture(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_DIR", "tests/fixtures/knowledge-fallback")
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {"mode": "coaching", "intake_schema": False, "ui": {}}


def test_config_with_math_pack_exposes_coaching_mode(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_DIR", "knowledge-math")
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert data == {"mode": "coaching", "intake_schema": False, "ui": {}}
