"""GET /api/config 엔드포인트 테스트."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """TestClient 피크스처."""
    return TestClient(app)


def test_config_with_schema(client, monkeypatch):
    """intake 스키마가 있는 지식셋에서 intake_schema=true. ui 미선언이면 빈 dict."""
    monkeypatch.setenv("KNOWLEDGE_DIR", "knowledge")
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {"intake_schema": True, "ui": {}}


def test_config_without_schema(client, monkeypatch):
    """스키마가 없는 지식셋(knowledge-alt)에서 intake_schema=false."""
    monkeypatch.setenv("KNOWLEDGE_DIR", "knowledge-alt")
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {"intake_schema": False, "ui": {}}


def test_config_with_schema_ui(client, monkeypatch):
    """ui 섹션을 선언한 지식셋(knowledge-math)은 스키마 소유 문구를 그대로 내려준다."""
    monkeypatch.setenv("KNOWLEDGE_DIR", "knowledge-math")
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert data["intake_schema"] is True
    assert data["ui"]["title"] == "PNK 수학 학습 코치"
    assert len(data["ui"]["chips"]) == 4
    assert "track" in data["ui"]["contextual_replies"]
