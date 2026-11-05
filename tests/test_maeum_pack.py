"""대구 마음 이야기 입구 팩의 복사 경계와 실제 fake 대화 경로를 검증한다."""

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from app import chat
from app.config import Settings
from app.intake import extract_fake, load_schema

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = REPO_ROOT / "knowledge"
PACK_DIR = REPO_ROOT / "knowledge-maeum"
REMOVED_SLOTS = {"area", "age_band", "contact_pref"}


@pytest.fixture
def maeum_settings(monkeypatch, tmp_path):
    # 기존 e2e처럼 저장은 임시 cwd에 격리하고 팩은 절대 경로로 선택한다.
    monkeypatch.setenv("MODEL", "fake")
    monkeypatch.setenv("KNOWLEDGE_DIR", str(PACK_DIR))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("TRUST_PROXY_HOPS", "0")
    monkeypatch.setenv("DAILY_REQUEST_CAP", "500")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(chat, "_sessions", {})
    settings = Settings.from_env()
    assert settings.model == "fake"
    assert Path(settings.knowledge_dir) == PACK_DIR
    return settings


def test_schema_loads_with_minimal_center_slots(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    schema = load_schema(Path("knowledge-maeum"))
    assert schema is not None
    assert not REMOVED_SLOTS & {slot.id for slot in schema.slots}
    assert "cause" in {slot.id for slot in schema.slots}
    assert schema.handoff_mode == "center"
    assert schema.opening_question != load_schema(SOURCE_DIR).opening_question
    assert "상담을 받으러" not in schema.opening_question


def test_all_source_files_are_copied_and_only_persona_and_schema_change():
    source_files = {path.relative_to(SOURCE_DIR) for path in SOURCE_DIR.rglob("*") if path.is_file()}
    pack_files = {path.relative_to(PACK_DIR) for path in PACK_DIR.rglob("*") if path.is_file()}

    assert pack_files == source_files | {Path("_validation_scenario.json"), Path("_privacy.md"), Path("연결-지도.yaml")}
    for relative in source_files - {Path("_persona.md"), Path("_intake_schema.md")}:
        assert (PACK_DIR / relative).read_bytes() == (SOURCE_DIR / relative).read_bytes(), relative

    original_persona = (SOURCE_DIR / "_persona.md").read_text(encoding="utf-8")
    persona = (PACK_DIR / "_persona.md").read_text(encoding="utf-8")
    identity_section = original_persona.split("## 말투 정체성 경계", 1)[1].split("## ", 1)[0]
    assert identity_section in persona


def test_existing_slots_and_crisis_flags_are_preserved():
    original = load_schema(SOURCE_DIR)
    schema = load_schema(PACK_DIR)

    # dataclass 전체 비교로 values, signals, red_flag, when/unless까지 보호한다.
    # 센터 팩의 의도적 학업 표현 보강과 when_asked 차이만 허용한다.
    expected = []
    for slot in original.slots:
        if slot.id == "cause":
            continue
        updates = {}
        if slot.id in {"coping", "support", "expectation"}:
            updates["priority"] = slot.priority + 1
        if slot.id == "expectation":
            updates["extract"] = "when_asked"
        if slot.id == "track":
            signals = {key: list(values) for key, values in slot.signals.items()}
            insert_at = signals["정서"].index("성적")
            signals["정서"][insert_at:insert_at] = ["공부", "집중"]
            updates["signals"] = signals
        if slot.id == "chief_complaint":
            signals = list(slot.signals)
            insert_at = signals.index("성적")
            signals[insert_at:insert_at] = ["공부", "집중"]
            updates["signals"] = signals
        expected.append(replace(slot, **updates))
    assert [slot for slot in schema.slots if slot.id != "cause"] == expected
    track = schema.slots[0]
    assert track.values == ["위기", "중독", "관계", "정서"]
    assert list(track.signals) == ["위기", "중독", "관계", "정서"]
    assert [slot.id for slot in schema.slots if slot.red_flag] == ["crisis_plan_means"]
    assert original.ui == {}
    assert schema.ui == {
        "title": "마음 이야기 입구",
        "handoff_mode": "center",
        "subtitle": "센터에 전할 이야기를 편한 만큼 정리해요",
        "intro": "안녕하세요. 편한 만큼만 이야기해 주세요. 이름이나 연락처는 쓰지 않아도 됩니다.",
        "privacy_summary": "개인정보 처리와 기록 삭제 안내",
        "lock_notice": "원문 90일·요약 365일 보관, 삭제 코드로 내 기록 지우기",
    }


@pytest.mark.parametrize("track,active", [("정서", True), ("관계", True), ("위기", False), ("중독", False)])
def test_cause_is_only_active_in_emotional_and_relationship_tracks(track, active):
    schema = load_schema(PACK_DIR)
    cause = next(slot for slot in schema.slots if slot.id == "cause")
    assert cause.capture == "full_message"
    assert cause.extract == "when_asked"
    assert cause.is_active({"track": track}) is active


@pytest.mark.parametrize(
    "message,expected_track",
    [
        ("술을 못 끊어서 가족과 갈등이 생겼어요", "중독"),
        ("술을 못 끊겠고 죽고 싶어요", "위기"),
        ("가족과 갈등 때문에 불안해요", "관계"),
    ],
)
def test_track_priority_is_unchanged(message, expected_track):
    assert extract_fake(message, load_schema(PACK_DIR), {})["track"] == expected_track


def test_opening_uses_pack_question(maeum_settings):
    result = chat.handle_message("maeum-opening", "안녕하세요", maeum_settings)

    assert load_schema(PACK_DIR).opening_question not in result["reply"]
    assert "안녕하세요" not in result["reply"].split(" | ", 1)[0]
    assert chat._sessions["maeum-opening"].slots["chief_complaint"] == "안녕하세요"
    assert result["turn"] == 1
    assert result["intake"]["unfilled"][0]["id"] == "track"


def _reach_closing_question(session_id, settings):
    first = chat.handle_message(session_id, "우울해서 잠을 못 자요", settings)
    assert first["intake"]["unfilled"][0]["id"] == "symptom_context"
    for message in (
        "두 달 전부터 시작됐고 일상에서 집중이 어려워요",
        "잘 모르겠어요",
        "산책을 해봤어요",
        "친구에게 말했어요",
        "어떤 도움을 받을 수 있을지 알고 싶어요",
    ):
        result = chat.handle_message(session_id, message, settings)
    assert chat._sessions[session_id].slots["track"] == "정서"
    assert result["intake"]["unfilled"] == []
    assert result["closing"]["stage"] == "select"
    assert "마지막으로 센터" in result["reply"]


def test_emotional_conversation_saves_cause_and_center_handoff(maeum_settings, tmp_path):
    session_id = "maeum-emotional"
    _reach_closing_question(session_id, maeum_settings)
    result = chat.handle_message(session_id, "없음, 이대로 보내기", maeum_settings)
    assert result["conversation_ended"] is True
    assert result["handoff"] == {"mode": "center", "sent": True}
    path = tmp_path / "data" / "conversations" / date.today().isoformat() / f"{session_id}.json"
    snapshot = json.loads(path.read_text(encoding="utf-8"))["intake_snapshot"]
    assert snapshot["slots"]["cause"] == "잘 모르겠어요"
    assert not REMOVED_SLOTS & set(snapshot["slots"])
    assert snapshot["center_requests"] == []


@pytest.mark.parametrize("after_emotional", [False, True])
def test_crisis_route_keeps_safety_first_and_never_asks_area(maeum_settings, after_emotional):
    session_id = "maeum-crisis"
    if after_emotional:
        _reach_closing_question(session_id, maeum_settings)

    result = chat.handle_message(session_id, "죽고 싶어요", maeum_settings)
    session = chat._sessions[session_id]
    assert session.slots["track"] == "위기"
    assert session.crisis_ever_detected is True
    assert result["intake"]["unfilled"][0]["id"] == "crisis_plan_means"
    assert result["intake"]["unfilled"][0]["red_flag"] is True
    for number in ("109", "1588-9191", "119"):
        assert number in result["reply"]

    schema = load_schema(PACK_DIR)
    for response in (result, chat.handle_message(session_id, "수성구에 살아요", maeum_settings)):
        assert not REMOVED_SLOTS & {item["id"] for item in response["intake"]["unfilled"]}
        cause = next(slot for slot in schema.slots if slot.id == "cause")
        assert cause.ask not in response["reply"]
        assert "거주 구·군" not in response["reply"]
    assert not REMOVED_SLOTS & set(session.slots)


@pytest.mark.parametrize("message", [
    "남편이 전화를 안 받아서 매일 다퉈요",
    "요즘 우울해서 문자도 답장 못하고 쉰다는 핑계로 누워만 있어요",
    "회사 상사가 방문 일정을 바꿔서 불안하고 잠을 못 자요",
])
def test_incidental_connection_words_do_not_fill_optional_slots(maeum_settings, message):
    schema = load_schema(PACK_DIR)
    fills = extract_fake(message, schema, {})
    assert not REMOVED_SLOTS & set(fills)
    chat.handle_message("incidental", message, maeum_settings)
    assert not REMOVED_SLOTS & set(chat._sessions["incidental"].slots)


def test_real_extraction_cannot_fill_removed_slots():
    from app.intake import extract_real
    schema = load_schema(PACK_DIR)
    reply = '답변\n```slots\n{"area":"수성구","age_band":"30대","contact_pref":"전화"}\n```'
    assert extract_real(reply, schema, {"track": "정서"}) == ("답변", {})
    assert extract_real(reply, schema, {"track": "정서"}, "수성구요", "area") == ("답변", {})
    assert chat._answer_to_previous_question("전화", schema, {}, None) == {}


@pytest.mark.parametrize("extract", ["always", "", None, True, ["when_asked"]])
def test_unknown_extract_is_a_runtime_and_strict_validation_error(tmp_path, extract):
    import yaml
    from app.intake import SchemaExtractError
    from app.knowledge_pack import validate_pack
    schema = {"intake_schema": {"version": "1", "opening_question": "질문", "slots": [
        {"id": "test", "label": "질문", "extract": extract}
    ]}}
    (tmp_path / "_intake_schema.md").write_text("```yaml\n" + yaml.safe_dump(schema) + "```\n", encoding="utf-8")
    with pytest.raises(SchemaExtractError):
        load_schema(tmp_path)
    result = validate_pack(tmp_path)
    assert any(issue.code == "SLOT_EXTRACT_VALUE" for issue in result.errors)
