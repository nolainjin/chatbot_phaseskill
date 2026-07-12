"""Phase 6(fake e2e 4종 + 스왑 회귀) 검증 — task 성공 기준 그 자체.

fake 모드(MODEL=fake, API 키 불필요)로 handle_message를 시나리오별 다턴 구동해
CAP 원장의 어드버서리얼 플래그가 요구하는 단언 수준을 지킨다: 위기 시나리오는
"레드플래그가 다른 슬롯보다 먼저 질문된다"는 순서 단언(CAP22 — 위기 트랙만
태우고 통과 처리하는 fake-satisfy 차단), 혼합 시나리오는 "2슬롯이 실제로
동시에 채워졌다"는 개수 단언(CAP23).
"""

import json
from datetime import date
from pathlib import Path

from app import chat
from app.config import Settings
from app.intake import load_schema

REPO_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = str(REPO_ROOT / "knowledge")
KNOWLEDGE_ALT_DIR = str(REPO_ROOT / "knowledge-alt")

# 어떤 슬롯 signals와도 겹치지 않는 안전한 다턴 채움용 필러 발화.
_FILLER = "그냥 이야기하고 싶어요"


def _settings(knowledge_dir: str = KNOWLEDGE_DIR) -> Settings:
    return Settings(
        anthropic_api_key="",
        knowledge_dir=knowledge_dir,
        model="fake",
        trust_proxy_hops=0,
        daily_request_cap=500,
    )


def _run_to_summary(session_id: str, first_message: str, settings: Settings | None = None) -> dict:
    """1턴째 first_message로 시작해 MAX_TURNS까지 필러로 채운 뒤 저장된 요약 JSON을 반환한다."""
    settings = settings or _settings()
    chat.handle_message(session_id, first_message, settings)
    for _ in range(chat.MAX_TURNS - 1):
        chat.handle_message(session_id, _FILLER, settings)

    day_dir = Path("data/conversations") / date.today().isoformat()
    turns = json.loads((day_dir / f"{session_id}.json").read_text(encoding="utf-8"))
    summary_text = next(t["text"] for t in turns if t["role"] == "intake_summary")
    return json.loads(summary_text)


def test_emotional_track_scenario_opens_with_question_and_summarizes_track(monkeypatch, tmp_path):
    """① 정서 — 1턴 시스템 프롬프트 opening_question 포함 단언(CAP12) + 10턴 소진 후
    요약 JSON track=정서 단언."""
    monkeypatch.chdir(tmp_path)
    captured = []

    def fake_ask(system, history, user, doc_titles, settings):
        captured.append(system)
        return "[fake] 응답"

    monkeypatch.setattr(chat.llm, "ask", fake_ask)

    session_id = "e2e-emotional"
    summary = _run_to_summary(session_id, "우울해서 잠을 못 자요")

    schema = load_schema(KNOWLEDGE_DIR)
    assert schema.opening_question in captured[0]
    assert chat._sessions[session_id].slots["track"] == "정서"
    assert summary["track"] == "정서"


def test_relationship_track_scenario_summarizes_track(monkeypatch, tmp_path):
    """② 관계 — 동일 구조로 track=관계 경로 검증(요약 JSON track=관계 단언)."""
    monkeypatch.chdir(tmp_path)

    session_id = "e2e-relationship"
    summary = _run_to_summary(session_id, "남편과 사이가 안 좋아요")

    assert chat._sessions[session_id].slots["track"] == "관계"
    assert summary["track"] == "관계"


def test_crisis_track_asks_red_flag_slot_before_lower_priority_slots():
    """③ 위기 — 레드플래그 슬롯 우선 질문 순서 단언(CAP22).

    "자해할 계획이 있어요" 한 발화가 track=위기와 chief_complaint를 채우는 동시에
    crisis_plan_means(red_flag)의 signal("계획")도 감지한다. crisis_plan_means는
    track이 이번 턴에야 채워지는 바람에 추출 시점엔 아직 비활성이라 extract_fake가
    채우지 않으므로 미충족 상태로 남고, unfilled_by_priority가 이를 최상단에 둔다.
    """
    session_id = "e2e-crisis"
    result = chat.handle_message(session_id, "자해할 계획이 있어요", _settings())

    session = chat._sessions[session_id]
    assert session.slots["track"] == "위기"
    assert session.slots["chief_complaint"] == "자해할 계획이 있어요"
    assert "crisis_plan_means" not in session.slots
    assert "다음 질문: 자해 계획·수단" in result["reply"]


def test_mixed_utterance_fills_two_slots_at_once():
    """④ 혼합 — 한 발화에서 트랙+지지체계 2슬롯 동시 충족 단언(CAP23).

    "남편과 가족 문제로 너무 힘들어요"는 "남편"으로 track=관계, "가족"으로
    support=지지체계를 동시에 매칭한다 — 슬롯 하나만 채우고 통과시키는
    fake-satisfy를 개수·값 단언으로 차단한다.
    """
    session_id = "e2e-mixed"
    result = chat.handle_message(session_id, "남편과 가족 문제로 너무 힘들어요", _settings())

    session = chat._sessions[session_id]
    assert session.slots == {
        "track": "관계",
        "chief_complaint": "남편과 가족 문제로 너무 힘들어요",
        "support": "가족",
    }
    assert "상담 트랙=관계" in result["reply"]
    assert "지지체계=가족" in result["reply"]

    # GUI 슬롯 패널용 additive 필드 — 채움/미충족 라벨이 스키마와 일치해야 한다.
    filled_labels = {s["label"]: s["value"] for s in result["intake"]["filled"]}
    assert filled_labels == {
        "상담 트랙": "관계",
        "호소 문제": "남편과 가족 문제로 너무 힘들어요",
        "지지체계": "가족",
    }
    assert result["intake"]["unfilled"][0]["label"] == "관계 대상·기간"


def test_fake_schema_reply_is_interview_like_not_doc_stub():
    """상담 스키마 fake 모드는 문서 제목 스텁이 아니라 초기면담 질문으로 보여야 한다."""
    session_id = "e2e-fake-interview-reply"
    result = chat.handle_message(session_id, "우울해서 잠을 못 자요", _settings())

    visible_reply = result["reply"].split(" | ", 1)[0]
    assert not visible_reply.startswith("[fake]")
    assert "참고 문서" not in visible_reply
    assert "언제부터" in visible_reply
    assert chat._sessions[session_id].slots["chief_complaint"] == "우울해서 잠을 못 자요"


def test_later_crisis_signal_escalates_track_for_safety():
    """초기 정서 트랙 이후에도 자해·자살 신호가 나오면 위기 트랙으로 승격한다."""
    session_id = "e2e-crisis-escalation"
    chat.handle_message(session_id, "우울해서 잠을 못 자요", _settings())
    result = chat.handle_message(session_id, "자해할 계획이 있어요", _settings())

    assert chat._sessions[session_id].slots["track"] == "위기"
    assert result["intake"]["unfilled"][0]["label"] == "자해 계획·수단"
    assert result["intake"]["unfilled"][0]["red_flag"] is True
    assert "119" in result["reply"]


def test_later_relationship_signal_escalates_from_emotion_without_support_false_positive():
    """정서 폴백 뒤 구체적 관계 신호는 승격하되, 단순 지지체계 언급은 승격하지 않는다."""
    rel_session = "e2e-relationship-escalation"
    chat.handle_message(rel_session, "우울해서 잠을 못 자요", _settings())
    rel_result = chat.handle_message(rel_session, "남편과 갈등 때문에 힘들어요", _settings())

    assert chat._sessions[rel_session].slots["track"] == "관계"
    assert rel_result["intake"]["unfilled"][0]["label"] == "관계 대상·기간"

    support_session = "e2e-support-no-track-flip"
    chat.handle_message(support_session, "우울해서 잠을 못 자요", _settings())
    chat.handle_message(support_session, "친구에게 얘기해봤어요", _settings())

    assert chat._sessions[support_session].slots["track"] == "정서"
    assert chat._sessions[support_session].slots["support"] == "친구"

def test_track_priority_relationship_wins_over_emotion():
    """트랙 판정 우선순위(위기 > 관계 > 정서) 회귀 방어.

    "남편과 갈등 때문에 잠을 못 자요"는 관계 신호(남편·갈등)와 정서 신호(잠)가
    섞인 발화 — 스키마 선언 순서(= 판정 우선순위)에 따라 관계로 확정돼야 한다.
    근거: knowledge/_intake_schema.md 판단 기록(2026-07-12 우선순위 역전).
    """
    session_id = "e2e-priority"
    chat.handle_message(session_id, "남편과 갈등 때문에 잠을 못 자요", _settings())

    assert chat._sessions[session_id].slots["track"] == "관계"


def test_knowledge_alt_swap_keeps_stub_reply_without_progress_suffix():
    """스왑 회귀(CAP18) — knowledge-alt(스키마 없음) 구동 시 기존 스텁 형식 유지,
    진행 접미사가 붙지 않음을 단언."""
    result = chat.handle_message(
        "e2e-swap-alt", "원두 보관법 알려줘", _settings(KNOWLEDGE_ALT_DIR)
    )

    assert result["reply"].startswith("[fake]")
    assert "채움:" not in result["reply"]
    # 스키마 없는 지식셋은 intake 키 자체가 없어야 GUI 패널이 뜨지 않는다.
    assert "intake" not in result
    assert "다음 질문:" not in result["reply"]
