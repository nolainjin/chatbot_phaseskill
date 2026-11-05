from pathlib import Path

import pytest

from app import chat, intake
from app.config import Settings


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge-maeum"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(chat, "_sessions", {})


def _settings(model="fake"):
    return Settings(
        anthropic_api_key="", knowledge_dir=str(KNOWLEDGE), model=model,
        trust_proxy_hops=0, daily_request_cap=500,
    )


def _primed(session_id="aligned"):
    schema = intake.load_schema(KNOWLEDGE)
    session = chat.ChatSession(
        session_id=session_id,
        turns=5,
        slots={
            "track": "정서", "chief_complaint": "공부에 집중하기 힘들어요",
            "symptom_context": "중간고사 이후부터요", "cause": "성적 걱정",
            "coping": "집에서 쉬었어요",
        },
        history=[{"role": "assistant", "content": next(
            slot.ask for slot in schema.slots if slot.id == "support"
        )}],
        last_question_slot_id="support",
    )
    chat._sessions[session_id] = session
    return schema, session


def test_real_model_question_is_replaced_by_owned_canonical_question(monkeypatch):
    schema, session = _primed()
    monkeypatch.setattr(chat.llm, "ask", lambda **kwargs: (
        "친구가 들어주었다니 다행입니다. 이 생각들이 가장 크게 올라오는 때는 언제인가요?\n"
        "```slots\n{}\n```"
    ))

    result = chat.handle_message("aligned", "친구가 들어줘요", _settings("codex-cli"))

    expectation_ask = next(slot.ask for slot in schema.slots if slot.id == "expectation")
    assert result["reply"].endswith(expectation_ask)
    assert "가장 크게 올라오는 때" not in result["reply"]
    assert session.last_question_slot_id == "expectation"
    assert session.pending_track is None
    assert session.slots["support"] == "친구가 들어줘요"


def test_stale_planned_expectation_does_not_capture_actual_timing_answer(monkeypatch):
    schema, session = _primed("legacy")
    session.slots["support"] = "친구가 들어줘요"
    session.last_question_slot_id = "expectation"
    session.history[-1] = {
        "role": "assistant", "content": "그 생각들이 가장 크게 올라오는 때는 주로 언제인가요?"
    }
    monkeypatch.setattr(chat.llm, "ask", lambda **kwargs: "말씀해 주셔서 감사합니다.\n```slots\n{}\n```")

    chat.handle_message("legacy", "저녁에 책상에 앉으면요", _settings("codex-cli"))

    assert "expectation" not in session.slots
    assert session.last_question_slot_id == "expectation"
    assert session.history[-1]["content"].endswith(
        next(slot.ask for slot in schema.slots if slot.id == "expectation")
    )


def test_study_comparison_is_emotional_not_relationship_or_support():
    result = chat.handle_message(
        "study", "공부에 집중하기 힘들고 친구들에게 따라잡힐까 불안해요", _settings()
    )
    session = chat._sessions["study"]

    assert session.slots["track"] == "정서"
    assert "support" not in session.slots
    assert result["intake"]["unfilled"][0]["id"] == "symptom_context"


def test_support_and_expectation_guards_preserve_direct_answers():
    schema = intake.load_schema(KNOWLEDGE)
    filled = {"track": "정서", "chief_complaint": "불안해요"}

    assert chat._answer_to_previous_question("없어요", schema, filled, "support") == {
        "support": "없어요"
    }
    assert chat._answer_to_previous_question("잘 모르겠어요", schema, filled, "expectation") == {
        "expectation": "잘 모르겠어요"
    }
    assert "support" not in intake.extract_fake(
        "친구가 공부를 못한다고 말했어요", schema, filled
    )
    assert intake.extract_fake("친구에게 얘기했어요", schema, filled)["support"] == "친구에게 얘기했어요"
