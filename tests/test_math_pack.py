"""knowledge-math(PNK 수학 학습 코칭) 지식셋 검증.

수학 팩은 지식 문서 교체(knowledge-alt)와 달리 스키마·페르소나·톤·개인정보
경계까지 전부 교체하는 완전한 커스터마이징 예제다. 여기서는 (1) 팩이
온전히 로드되는지, (2) 수학 트랙 흐름이 fake 모드로 끝까지 돌아가는지,
(3) 수학학원 화면에 상담형 위기 고지가 노출되지 않는지를 고정한다.
"""

import json
from datetime import date
from pathlib import Path

from app import chat, knowledge
from app.config import Settings
from app.intake import load_schema

REPO_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_MATH_DIR = str(REPO_ROOT / "knowledge-math")

_FILLER = "그냥 이야기하고 싶어요"


def _settings() -> Settings:
    return Settings(
        anthropic_api_key="",
        knowledge_dir=KNOWLEDGE_MATH_DIR,
        model="fake",
        trust_proxy_hops=0,
        daily_request_cap=500,
    )


def _run_to_summary(session_id: str, first_message: str) -> dict:
    settings = _settings()
    chat.handle_message(session_id, first_message, settings)
    for _ in range(chat.MAX_TURNS - 1):
        chat.handle_message(session_id, _FILLER, settings)

    day_dir = Path("data/conversations") / date.today().isoformat()
    turns = json.loads((day_dir / f"{session_id}.json").read_text(encoding="utf-8"))["turns"]
    summary_text = next(t["text"] for t in turns if t["role"] == "intake_summary")
    return json.loads(summary_text)


def test_math_schema_loads_with_ui_and_tracks():
    schema = load_schema(KNOWLEDGE_MATH_DIR)
    assert schema is not None
    track = next(slot for slot in schema.slots if slot.id == "track")
    assert track.values == ["개념", "문제풀이", "학습습관"]
    assert track.allow_override_values is None
    assert schema.ui["title"] == "PNK 수학 학습 코치"
    assert schema.ui["stepper_labels"] == ["고민 영역", "상황 파악", "코칭 준비"]


def test_math_documents_load_excluding_reserved():
    docs = knowledge.load_documents(KNOWLEDGE_MATH_DIR)
    # PNK 방법론 7편 + 태그북 TB1~TB14 = 21편. "_" 예약 파일은 제외된다.
    assert len(docs) == 21
    titles = {doc.title for doc in docs}
    assert "PNK수학의 방향성" in titles
    assert not any(doc.path.name.startswith("_") for doc in docs)


def test_problem_solving_track_fills_stuck_point_and_summarizes(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = _settings()
    session_id = "math-e2e-problem"

    chat.handle_message(
        session_id, "문제를 보면 어떻게 접근해야 할지 몰라서 손도 못 대요.", settings
    )
    assert chat._sessions[session_id].slots["track"] == "문제풀이"
    assert "chief_complaint" in chat._sessions[session_id].slots

    chat.handle_message(session_id, "어떻게 시작해야 할지 접근 방법을 모르겠어요.", settings)
    assert chat._sessions[session_id].slots["stuck_point"] == "접근 방법"

    for _ in range(chat.MAX_TURNS - 2):
        chat.handle_message(session_id, _FILLER, settings)
    day_dir = Path("data/conversations") / date.today().isoformat()
    turns = json.loads((day_dir / f"{session_id}.json").read_text(encoding="utf-8"))["turns"]
    summary = json.loads(next(t["text"] for t in turns if t["role"] == "intake_summary"))
    assert summary["track"] == "문제풀이"


def test_math_pack_does_not_expose_counseling_disclosure_copy():
    schema = load_schema(KNOWLEDGE_MATH_DIR)
    assert schema is not None
    joined_ui = json.dumps(schema.ui, ensure_ascii=False)
    slot_ids = {slot.id for slot in schema.slots}

    assert "보호자" not in joined_ui
    assert "전문기관" not in joined_ui
    assert "자신이나 타인" not in joined_ui
    assert "위기" not in next(slot for slot in schema.slots if slot.id == "track").values
    assert "crisis_plan_means" not in slot_ids
    assert "crisis_attempt_history" not in slot_ids


def test_fake_intro_uses_schema_ui_intro(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    result = chat.handle_message("math-e2e-intro", "안녕하세요", _settings())
    assert "수학 학습 코칭 전 접수 대화" in result["reply"]
    assert "상담" not in result["reply"]
    assert "보호자" not in result["reply"]
    assert "전문기관" not in result["reply"]
