from pathlib import Path
import json

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


@pytest.mark.parametrize(
    ("slot_id", "track", "answer"),
    [
        ("symptom_context", "정서", "불안할 때 산책하고 잠깐 쉬어 봤어요."),
        ("relationship_duration", "관계", "두 달 전부터 잠을 설쳤어요."),
    ],
)
def test_timing_fields_only_extract_answers_to_their_own_question(slot_id, track, answer):
    schema = intake.load_schema(KNOWLEDGE)
    filled = {"track": track, "chief_complaint": "불안해요"}
    slot = next(item for item in schema.slots if item.id == slot_id)
    raw = "알겠어요.\n```slots\n" + json.dumps({slot_id: answer}, ensure_ascii=False) + "\n```"

    assert slot.extract == "when_asked"
    assert slot_id not in intake.extract_fake(answer, schema, filled, "coping")
    assert intake.extract_real(raw, schema, filled, answer, "coping")[1] == {}
    assert intake.extract_fake(answer, schema, filled, slot_id)[slot_id] == answer
    assert intake.extract_real(raw, schema, filled, answer, slot_id)[1] == {
        slot_id: answer
    }


@pytest.mark.parametrize(
    ("model", "slot_id", "track", "extra_slots", "original"),
    [
        ("fake", "symptom_context", "정서", {}, "한 달 전부터 잠을 설쳤어요."),
        ("codex-cli", "symptom_context", "정서", {}, "한 달 전부터 잠을 설쳤어요."),
        ("fake", "relationship_duration", "관계", {"relationship_target": "배우자"}, "일 년 정도 이어졌어요."),
        ("codex-cli", "relationship_duration", "관계", {"relationship_target": "배우자"}, "일 년 정도 이어졌어요."),
    ],
)
def test_coping_answer_does_not_replace_timing_value_or_source(
    monkeypatch, model, slot_id, track, extra_slots, original
):
    schema = intake.load_schema(KNOWLEDGE)
    coping_ask = next(slot.ask for slot in schema.slots if slot.id == "coping")
    answer = "불안할 때 산책하고 잠깐 쉬어 봤어요."
    old_evidence = {
        "status": "answered", "value": original, "source_text": original,
        "source_turn": 2, "source": {"day": "2026-11-05", "seq": 2},
    }
    session = chat.ChatSession(
        session_id=f"source-{model}-{slot_id}",
        turns=4,
        slots={
            "track": track, "chief_complaint": "불안해요", slot_id: original,
            "cause": "잘 모르겠어요", **extra_slots,
        },
        slot_evidence={slot_id: dict(old_evidence)},
        history=[{"role": "assistant", "content": coping_ask}],
        last_question_slot_id="coping",
    )
    chat._sessions[session.session_id] = session
    monkeypatch.setattr(chat.llm, "ask", lambda **kwargs: (
        "알겠어요.\n```slots\n"
        + json.dumps({slot_id: answer, "coping": answer}, ensure_ascii=False)
        + "\n```"
    ))

    chat.handle_message(session.session_id, answer, _settings(model))

    assert session.slots[slot_id] == original
    assert session.slot_evidence[slot_id] == old_evidence
    assert session.slots["coping"] == answer
    assert session.slot_evidence["coping"]["source_text"] == answer


@pytest.mark.parametrize(
    ("answer", "asked_slot"),
    [
        ("불안할 때 산책하고 잠깐 쉬어 봤어요.", "coping"),
        ("상담에서 불안을 다루는 방법을 배우고 싶어요.", "expectation"),
    ],
)
def test_existing_chief_complaint_rejects_other_question_fake_and_real_proposals(
    answer, asked_slot
):
    schema = intake.load_schema(KNOWLEDGE)
    filled = {"track": "정서", "chief_complaint": "기존 호소"}
    raw = "알겠어요.\n```slots\n" + json.dumps(
        {"chief_complaint": answer}, ensure_ascii=False
    ) + "\n```"

    assert "chief_complaint" not in intake.extract_fake(
        answer, schema, filled, asked_slot
    )
    assert intake.extract_real(raw, schema, filled, answer, asked_slot)[1] == {}


def test_chief_complaint_still_accepts_opening_and_direct_question_answers():
    schema = intake.load_schema(KNOWLEDGE)
    opening = "불안해서 힘들어요."
    opening_raw = "알겠어요.\n```slots\n" + json.dumps(
        {"chief_complaint": opening}, ensure_ascii=False
    ) + "\n```"
    opening_filled = {"track": "정서"}

    assert intake.extract_fake(opening, schema, opening_filled)["chief_complaint"] == opening
    assert intake.extract_real(opening_raw, schema, opening_filled, opening)[1][
        "chief_complaint"
    ] == opening

    correction = "기존 내용이 아니라 불면 때문에 힘들어요."
    correction_raw = "알겠어요.\n```slots\n" + json.dumps(
        {"chief_complaint": correction}, ensure_ascii=False
    ) + "\n```"
    existing = {"track": "정서", "chief_complaint": "기존 호소"}

    assert intake.extract_fake(
        correction, schema, existing, "chief_complaint"
    )["chief_complaint"] == correction
    assert intake.extract_real(
        correction_raw, schema, existing, correction, "chief_complaint"
    )[1]["chief_complaint"] == correction


@pytest.mark.parametrize(
    ("model", "asked_slot", "answer"),
    [
        ("fake", "coping", "불안할 때 산책하고 잠깐 쉬어 봤어요."),
        ("codex-cli", "expectation", "상담에서 불안을 다루는 방법을 배우고 싶어요."),
    ],
)
def test_other_question_keeps_chief_value_source_and_revision(
    monkeypatch, model, asked_slot, answer
):
    schema = intake.load_schema(KNOWLEDGE)
    asked = next(slot.ask for slot in schema.slots if slot.id == asked_slot)
    old_evidence = {
        "status": "answered", "value": "기존 호소", "source_text": "기존 호소",
        "source_turn": 1, "source": {"day": "2026-11-05", "seq": 1},
    }
    old_revision = {
        "field": "chief_complaint", "before": "초기 호소", "after": "기존 호소",
        "source_turn": 1, "source": {"day": "2026-11-05", "seq": 1},
    }
    slots = {
        "track": "정서", "chief_complaint": "기존 호소",
        "symptom_context": "한 달 전부터 집중이 어려워요.",
        "cause": "잘 모르겠어요", "support": "친구가 알고 있어요",
    }
    if asked_slot == "expectation":
        slots["coping"] = "일기를 썼어요"
    session = chat.ChatSession(
        session_id=f"chief-source-{model}", turns=5, slots=slots,
        slot_evidence={"chief_complaint": dict(old_evidence)},
        slot_revisions=[dict(old_revision)],
        history=[{"role": "assistant", "content": asked}],
        last_question_slot_id=asked_slot,
    )
    chat._sessions[session.session_id] = session
    monkeypatch.setattr(chat.llm, "ask", lambda **kwargs: (
        "알겠어요.\n```slots\n"
        + json.dumps({"chief_complaint": answer, asked_slot: answer}, ensure_ascii=False)
        + "\n```"
    ))

    chat.handle_message(session.session_id, answer, _settings(model))

    assert session.slots["chief_complaint"] == "기존 호소"
    assert session.slot_evidence["chief_complaint"] == old_evidence
    assert session.slot_revisions == [old_revision]
    assert session.slots[asked_slot] == answer
