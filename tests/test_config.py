"""GET /api/config 엔드포인트 테스트."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """TestClient 피크스처."""
    return TestClient(app)


def test_config_with_schema(client, monkeypatch):
    """intake 스키마가 있는 지식셋에서 intake_schema=true."""
    monkeypatch.setenv("KNOWLEDGE_DIR", "knowledge")
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {"intake_schema": True}


def test_config_without_schema(client, monkeypatch):
    """스키마가 없는 지식셋(knowledge-alt)에서 intake_schema=false."""
    monkeypatch.setenv("KNOWLEDGE_DIR", "knowledge-alt")
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {"intake_schema": False}
