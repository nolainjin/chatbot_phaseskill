from pathlib import Path

from app import chat
from app.config import Settings
from app.intake import extract_real, load_schema

KNOWLEDGE_DIR = str(Path(__file__).resolve().parent.parent / "knowledge")


def _settings() -> Settings:
    return Settings(
        anthropic_api_key="",
        knowledge_dir=KNOWLEDGE_DIR,
        model="fake",
        trust_proxy_hops=0,
        daily_request_cap=500,
    )


def test_relationship_duration_answer_does_not_fill_coping_slot(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    session_id = "relationship-duration-not-coping"

    first = chat.handle_message(session_id, "남편과 사이가 안 좋아서 너무 힘들어요", _settings())
    assert first["intake"]["unfilled"][0]["id"] == "relationship_target"

    second = chat.handle_message(session_id, "남편과의 관계예요.", _settings())
    assert chat._sessions[session_id].slots["relationship_target"] == "남편"
    assert second["intake"]["unfilled"][0]["id"] == "relationship_duration"

    duration_answer = "벌써 4개월째예요. 잠을 못 자고 일에도 영향이 있어요."
    third = chat.handle_message(session_id, duration_answer, _settings())
    slots = chat._sessions[session_id].slots

    assert slots["relationship_duration"] == duration_answer
    assert "coping" not in slots
    assert third["intake"]["unfilled"][0]["id"] == "coping"

    coping_answer = "산책을 해봤어요."
    fourth = chat.handle_message(session_id, coping_answer, _settings())

    assert slots["coping"] == coping_answer
    assert fourth["intake"]["unfilled"][0]["id"] == "support"


def test_real_extraction_rejects_duration_only_value_for_coping():
    schema = load_schema(KNOWLEDGE_DIR)
    assert schema is not None
    message = "벌써 4개월째예요. 잠을 못 자고 일에도 영향이 있어요."
    raw = '답변\n```slots\n{"coping": "' + message + '"}\n```'

    _, fills = extract_real(
        raw,
        schema,
        {"track": "관계", "chief_complaint": "남편과 사이가 안 좋아요", "relationship_target": "남편"},
        message,
    )

    assert fills == {}


def test_real_extraction_rejects_target_only_value_for_relationship_duration():
    schema = load_schema(KNOWLEDGE_DIR)
    assert schema is not None
    message = "남편과의 관계예요."
    raw = '답변\n```slots\n{"relationship_duration": "' + message + '"}\n```'

    _, fills = extract_real(
        raw,
        schema,
        {"track": "관계", "chief_complaint": "남편과 사이가 안 좋아요", "relationship_target": "남편"},
        message,
    )

    assert fills == {}
