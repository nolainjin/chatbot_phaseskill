"""대구 마음 이야기 입구 팩의 복사 경계와 실제 fake 대화 경로를 검증한다."""

import json
from datetime import date
from pathlib import Path

import pytest

from app import chat
from app.config import Settings
from app.intake import extract_fake, load_schema

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = REPO_ROOT / "knowledge"
PACK_DIR = REPO_ROOT / "knowledge-maeum"
CONNECTION_SLOTS = {
    "area": [
        "중구", "동구", "서구", "남구", "북구", "수성구", "달서구", "달성군",
        "군위군", "대구 밖", "말하지 않음",
    ],
    "age_band": ["10대", "20대", "30대", "40대", "50대", "60대 이상", "말하지 않음"],
    "contact_pref": ["전화", "방문", "온라인·문자", "아직 모름"],
}


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


def test_schema_loads_with_three_connection_slots(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    schema = load_schema(Path("knowledge-maeum"))

    assert schema is not None
    assert [slot.id for slot in schema.slots[-3:]] == list(CONNECTION_SLOTS)
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
    assert schema.slots[:-3] == original.slots
    track = schema.slots[0]
    assert track.values == ["위기", "중독", "관계", "정서"]
    assert list(track.signals) == ["위기", "중독", "관계", "정서"]
    assert [slot.id for slot in schema.slots if slot.red_flag] == ["crisis_plan_means"]
    assert original.ui == {}
    assert schema.ui == {
        "title": "마음 이야기 입구",
        "subtitle": "마음에 걸리는 이야기를 정리하고 알맞은 기관을 찾아봐요",
        "intro": "안녕하세요. 편한 만큼만 이야기해 주세요. 이름이나 연락처는 쓰지 않아도 됩니다.",
        "privacy_summary": "개인정보 처리와 기록 삭제 안내",
        "lock_notice": "원문 90일·요약 365일 보관, 삭제 코드로 내 기록 지우기",
    }


@pytest.mark.parametrize("slot_id,values", CONNECTION_SLOTS.items())
def test_connection_slots_are_optional_last_and_disabled_in_crisis(slot_id, values):
    schema = load_schema(PACK_DIR)
    slot = next(slot for slot in schema.slots if slot.id == slot_id)
    original_max_priority = max(slot.priority for slot in load_schema(SOURCE_DIR).slots)

    assert slot.values == values
    assert set(slot.signals) == set(values)
    assert slot.required is False
    assert slot.priority > original_max_priority
    assert slot.unless == "track=위기"
    assert "말하고 싶지 않으면 넘어가도" in slot.ask
    assert slot.is_active({"track": "정서"})
    assert not slot.is_active({"track": "위기"})
    assert slot.extract == "when_asked"
    for value in values:
        assert slot_id not in extract_fake(value, schema, {"track": "정서"})
        assert extract_fake(value, schema, {"track": "정서"}, slot_id)[slot_id] == value
    if slot_id == "area":
        assert slot.signals == {value: [value] for value in values}


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

    assert load_schema(PACK_DIR).opening_question in result["reply"]
    assert result["turn"] == 1
    assert result["intake"]["unfilled"][0]["id"] == "track"


def _reach_area_question(session_id, settings):
    first = chat.handle_message(session_id, "우울해서 잠을 못 자요", settings)
    assert first["intake"]["unfilled"][0]["id"] == "symptom_context"
    for message in (
        "두 달 전부터 시작됐고 일상에서 집중이 어려워요",
        "산책을 해봤어요",
        "친구에게 말했어요",
        "어떤 도움을 받을 수 있을지 알고 싶어요",
    ):
        result = chat.handle_message(session_id, message, settings)
    assert chat._sessions[session_id].slots["track"] == "정서"
    assert result["intake"]["unfilled"][0]["id"] == "area"
    assert "말하고 싶지 않으면 넘어가도" in result["reply"]


def test_emotional_conversation_fills_connection_slots_and_snapshot(maeum_settings, tmp_path):
    session_id = "maeum-emotional"
    _reach_area_question(session_id, maeum_settings)

    area_result = chat.handle_message(session_id, "수성구에 살아요", maeum_settings)
    assert chat._sessions[session_id].slots["area"] == "수성구"
    assert area_result["intake"]["unfilled"][0]["id"] == "age_band"
    assert {item["id"]: item["value"] for item in area_result["intake"]["filled"]}["area"] == "수성구"

    age_result = chat.handle_message(session_id, "스물여덟이에요", maeum_settings)
    assert chat._sessions[session_id].slots["age_band"] == "20대"
    assert age_result["intake"]["unfilled"][0]["id"] == "contact_pref"

    result = chat.handle_message(session_id, "온라인·문자가 편해요", maeum_settings)
    assert result["turn"] == 8
    assert result["limit_reached"] is False
    assert result["intake"]["unfilled"] == []
    path = tmp_path / "data" / "conversations" / date.today().isoformat() / f"{session_id}.json"
    snapshot = json.loads(path.read_text(encoding="utf-8"))["intake_snapshot"]
    assert {slot_id: snapshot["slots"][slot_id] for slot_id in CONNECTION_SLOTS} == {
        "area": "수성구", "age_band": "20대", "contact_pref": "온라인·문자",
    }


@pytest.mark.parametrize("after_emotional", [False, True])
def test_crisis_route_keeps_safety_first_and_never_asks_area(maeum_settings, after_emotional):
    session_id = "maeum-crisis"
    if after_emotional:
        _reach_area_question(session_id, maeum_settings)

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
        assert not set(CONNECTION_SLOTS) & {item["id"] for item in response["intake"]["unfilled"]}
        for slot in schema.slots[-3:]:
            assert slot.ask not in response["reply"]
        assert "거주 구·군" not in response["reply"]
    assert not set(CONNECTION_SLOTS) & set(session.slots)


@pytest.mark.parametrize("message", [
    "남편이 전화를 안 받아서 매일 다퉈요",
    "요즘 우울해서 문자도 답장 못하고 쉰다는 핑계로 누워만 있어요",
    "회사 상사가 방문 일정을 바꿔서 불안하고 잠을 못 자요",
])
def test_incidental_connection_words_do_not_fill_optional_slots(maeum_settings, message):
    schema = load_schema(PACK_DIR)
    fills = extract_fake(message, schema, {})
    assert not set(CONNECTION_SLOTS) & set(fills)
    chat.handle_message("incidental", message, maeum_settings)
    assert not set(CONNECTION_SLOTS) & set(chat._sessions["incidental"].slots)


@pytest.mark.parametrize("slot_id,message,value", [
    ("area", "수성구요", "수성구"),
    ("age_band", "30대예요", "30대"),
    ("contact_pref", "전화가 편해요", "전화"),
    ("area", "넘어갈게요", "말하지 않음"),
    ("age_band", "넘어갈게요", "말하지 않음"),
    ("contact_pref", "넘어갈게요", "아직 모름"),
    ("area", "글쎄요", "말하지 않음"),
    ("age_band", "글쎄요", "말하지 않음"),
    ("contact_pref", "글쎄요", "아직 모름"),
])
def test_direct_connection_answer_is_accepted_only_after_its_question(maeum_settings, slot_id, message, value):
    session_id = "direct-answer"
    _reach_area_question(session_id, maeum_settings)
    session = chat._sessions[session_id]
    for prior, answer in (("area", "수성구요"), ("age_band", "30대예요")):
        if session.last_question_slot_id == slot_id:
            break
        chat.handle_message(session_id, answer, maeum_settings)
    assert session.last_question_slot_id == slot_id
    result = chat.handle_message(session_id, message, maeum_settings)
    assert session.slots[slot_id] == value
    assert slot_id not in {s["id"] for s in result["intake"]["unfilled"]}


def test_real_extraction_cannot_bypass_when_asked():
    from app.intake import extract_real
    schema = load_schema(PACK_DIR)
    reply = '답변\n```slots\n{"area":"수성구","age_band":"30대","contact_pref":"전화"}\n```'
    assert extract_real(reply, schema, {"track": "정서"}) == ("답변", {})
    assert extract_real(reply, schema, {"track": "정서"}, "수성구요", "area") == ("답변", {"area": "수성구"})
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
