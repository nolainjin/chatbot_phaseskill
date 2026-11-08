"""Answer classification in center mode (2026-11-09): reply → grounded quotes → slots.

H1 an off-topic reply must not count as the answer to the asked slot,
H2 information given before its question must not be asked again,
H3 one message with several facts must be split across slots.
All model calls are stubbed; no network or model process is used.
"""

import json
import logging
from pathlib import Path

import pytest

from app import answer_classifier, chat, intake, llm
from app.config import Settings

PACK = str(Path(__file__).resolve().parent.parent / "knowledge-maeum")
REPLY = "말씀해 주셔서 고마워요.\n```slots\n{}\n```"


def _settings():
    return Settings(anthropic_api_key="test-key", knowledge_dir=PACK, model="claude-test",
                    trust_proxy_hops=0, daily_request_cap=500)


def _schema():
    return intake.load_schema(PACK)


def _payload(*items, answered="yes"):
    """items: (key, quote[, status[, explicit[, aspect]]])."""
    rows = []
    defaults = (None, None, "answered", True, None)
    for item in items:
        key, quote, status, explicit, aspect = tuple(item) + defaults[len(item):]
        rows.append({"slot": key, "quote": quote, "status": status, "correction": False, "explicit": explicit,
                     "aspect": aspect or ("both" if key == "onset_impact" else "none")})
    return json.dumps({"answered_asked": answered, "items": rows}, ensure_ascii=False)


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.setattr(chat, "_sessions", {})
    calls = {"classify": [], "ask": []}
    queue = []

    def classify(system, user, settings, json_schema=None):
        calls["classify"].append({"system": system, "user": user, "schema": json_schema})
        response = queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def ask(**kwargs):
        calls["ask"].append(kwargs)
        return REPLY

    monkeypatch.setattr(llm, "classify", classify)
    monkeypatch.setattr(llm, "ask", ask)
    return queue, calls


def _session(session_id, **slots):
    session = chat._get_session(session_id)
    session.slots.update(slots)
    return session


def test_parse_and_grounding_reject_invented_content():
    keys = answer_classifier.catalog(_schema())
    with pytest.raises(answer_classifier.ClassifyError):
        answer_classifier.parse("응답", keys)
    with pytest.raises(answer_classifier.ClassifyError):
        answer_classifier.parse('{"answered_asked":"yes","items":[{"slot":"track","quote":"x",'
                                '"status":"answered","correction":false}]}', keys)
    message = "두세 달 됐고   밥맛이 없어요."
    assert answer_classifier.grounded_quote("두세 달 됐고 밥맛이 없어요.", message) == "두세 달 됐고 밥맛이 없어요"
    assert answer_classifier.grounded_quote("석 달 됐어요", message) is None
    assert set(keys) == {"chief_complaint", "onset_impact", "relationship_target", "cause",
                         "coping", "support", "expectation"}


def test_multi_information_opening_is_split_and_not_asked_again(stub):
    queue, calls = stub
    message = "요즘 회의만 생각하면 숨이 막혀요. 석 달 전 부서를 옮긴 뒤로 그래요. 요가를 해 봤어요."
    queue.append(_payload(("chief_complaint", "요즘 회의만 생각하면 숨이 막혀요"), ("onset_impact", "석 달 전"),
                          ("cause", "부서를 옮긴 뒤로 그래요"), ("coping", "요가를 해 봤어요")))
    session = _session("multi", track="정서")
    result = chat.handle_message("multi", message, _settings())

    assert session.slots["chief_complaint"] == "요즘 회의만 생각하면 숨이 막혀요"
    assert session.slots["symptom_context"] == "석 달 전"
    assert session.slots["cause"] == "부서를 옮긴 뒤로 그래요"
    assert session.slots["coping"] == "요가를 해 봤어요"
    assert session.slot_evidence["cause"]["method"] == "classifier"
    next_ids = [item["id"] for item in result["intake"]["unfilled"]]
    assert next_ids[0] == "support"
    assert not {"symptom_context", "cause", "coping"} & set(next_ids)
    # The reply prompt keeps the production extraction/safety instructions.
    assert chat._EXTRACTION_INSTRUCTION in calls["ask"][0]["system"]
    assert chat._CRISIS_ESCALATION_INSTRUCTION in calls["ask"][0]["system"]
    assert "직전 질문 항목: chief_complaint" in calls["classify"][0]["user"]


def test_offtopic_reply_is_reasked_once_then_left_unconfirmed(stub):
    queue, _ = stub
    schema = _schema()
    symptom = next(slot for slot in schema.slots if slot.id == "symptom_context")
    session = _session("offtopic", track="정서", chief_complaint="회의가 무서워요")
    session.history.append({"role": "assistant", "content": "그렇군요. " + symptom.ask})
    session.last_question_slot_id = "symptom_context"

    queue.append(_payload(("cause", "부서를 옮긴 게 컸어요"), answered="no"))
    first = chat.handle_message("offtopic", "부서를 옮긴 게 컸어요", _settings())
    assert "symptom_context" not in session.slots
    assert session.slots["cause"] == "부서를 옮긴 게 컸어요"
    assert session.slot_misses == {"symptom_context": 1}
    assert symptom.reask in first["reply"]

    queue.append(_payload(answered="no"))
    second = chat.handle_message("offtopic", "상담은 몇 번 받아요?", _settings())
    assert "symptom_context" not in session.slots
    assert session.skipped_slots == {"symptom_context"}
    assert second["intake"]["unfilled"][0]["id"] == "coping"
    assert symptom.ask not in second["reply"] and symptom.reask not in second["reply"]
    assert intake.build_summary_json(schema, session.slots)["unfilled"]["symptom_context"] == "미확인"


def test_quotes_wait_for_track_and_land_when_it_is_known(stub):
    queue, _ = stub
    session = _session("pending")
    queue.append(_payload(("chief_complaint", "그냥 요즘 다 버거워요"), ("onset_impact", "두세 달 됐어요")))
    first = chat.handle_message("pending", "그냥 요즘 다 버거워요. 두세 달 됐어요.", _settings())
    assert first["intake"]["unfilled"][0]["id"] == "track"
    assert [item["quote"] for item in session.pending_slot_items] == ["두세 달 됐어요"]

    queue.append(_payload(answered="no"))
    second = chat.handle_message("pending", "기분 쪽이요. 우울하고 불안해요.", _settings())
    assert session.slots["track"] == "정서"
    assert session.slots["symptom_context"] == "두세 달 됐어요"
    assert session.slot_evidence["symptom_context"]["source_turn"] == 1
    assert session.pending_slot_items == []
    assert second["intake"]["unfilled"][0]["id"] == "cause"


def test_timing_alone_asks_only_the_missing_part_once(stub):
    queue, _ = stub
    schema = _schema()
    symptom = next(slot for slot in schema.slots if slot.id == "symptom_context")
    session = _session("parts", track="정서")
    queue.append(_payload(("chief_complaint", "사람 만나는 게 무서워요"),
                          ("onset_impact", "몇 달째", "answered", True, "timing")))
    first = chat.handle_message("parts", "몇 달째 사람 만나는 게 무서워요.", _settings())
    assert session.slots["symptom_context"] == "몇 달째"
    assert first["intake"]["unfilled"][0]["id"] == "symptom_context"
    # The slot panel shows a part still to ask once, as the next question.
    assert "symptom_context" not in [item["id"] for item in first["intake"]["filled"]]
    assert symptom.ask_impact in first["reply"] and symptom.ask not in first["reply"]

    queue.append(_payload(answered="no"))
    second = chat.handle_message("parts", "상담은 몇 번 받아요?", _settings())
    assert session.slot_followups["symptom_context"] == "done"
    assert session.slot_misses == {}
    assert second["intake"]["unfilled"][0]["id"] == "cause"


def test_passing_mention_does_not_fill_another_question(stub):
    queue, _ = stub
    session = _session("passing", track="정서", chief_complaint="불안해요", symptom_context="한 달")
    session.history.append({"role": "assistant", "content": "그렇군요. 계기가 있을까요?"})
    session.last_question_slot_id = "cause"
    queue.append(_payload(("cause", "이사 오고 나서"), ("support", "동네가 낯설어서", "answered", False)))
    result = chat.handle_message("passing", "이사 오고 나서 동네가 낯설어서 그런 것 같아요.", _settings())
    assert session.slots["cause"] == "이사 오고 나서"
    assert "support" not in session.slots
    assert "support" in [item["id"] for item in result["intake"]["unfilled"]]


def test_relationship_target_from_any_wording_is_not_asked_again(stub):
    queue, _ = stub
    session = _session("target")
    queue.append(_payload(("chief_complaint", "매일 싸워서 집에 있기가 힘들어요"),
                          ("relationship_target", "엄마")))
    result = chat.handle_message("target", "엄마랑 매일 싸워서 집에 있기가 힘들어요.", _settings())
    assert session.slots["track"] == "관계"
    assert session.slots["relationship_target"] == "엄마"
    assert result["intake"]["unfilled"][0]["id"] == "relationship_duration"


def test_declined_answer_is_recorded_once(stub):
    queue, _ = stub
    session = _session("declined", track="정서", chief_complaint="불안해요", symptom_context="한 달")
    session.history.append({"role": "assistant", "content": "그렇군요. 계기가 있을까요?"})
    session.last_question_slot_id = "cause"
    queue.append(_payload(("cause", "그건 말하고 싶지 않아요", "declined")))
    result = chat.handle_message("declined", "그건 말하고 싶지 않아요.", _settings())
    assert session.slots["cause"] == "그건 말하고 싶지 않아요"
    assert session.slot_evidence["cause"]["status"] == "declined"
    assert result["intake"]["unfilled"][0]["id"] == "coping"


def test_missing_complaint_is_asked_before_the_track(stub):
    queue, _ = stub
    session = _session("hello")
    schema = _schema()
    chief = next(slot for slot in schema.slots if slot.id == "chief_complaint")
    queue.append(_payload(answered="no"))
    result = chat.handle_message("hello", "안녕하세요", _settings())
    assert "chief_complaint" not in session.slots
    assert result["intake"]["unfilled"][0]["id"] == "chief_complaint"
    assert chief.reask in result["reply"]


def test_classifier_failure_keeps_previous_capture_and_is_marked(stub, caplog):
    queue, _ = stub
    session = _session("failover", track="정서", chief_complaint="불안해요")
    session.history.append({"role": "assistant", "content": "그렇군요. 계기가 있을까요?"})
    session.last_question_slot_id = "cause"
    queue.append(llm.ModelBackendError("model backend unavailable: APITimeoutError"))
    with caplog.at_level(logging.WARNING, logger="app.chat"):
        chat.handle_message("failover", "이직한 뒤로 그래요", _settings())
    assert session.slots["cause"] == "이직한 뒤로 그래요"
    assert session.slot_evidence["cause"]["method"] == "fallback"
    assert "answer classification failover" in caplog.text
    assert "이직" not in caplog.text


def test_all_ungrounded_quotes_fall_back_instead_of_storing_paraphrase(stub):
    queue, _ = stub
    session = _session("ungrounded", track="정서", chief_complaint="불안해요")
    session.history.append({"role": "assistant", "content": "그렇군요. 계기가 있을까요?"})
    session.last_question_slot_id = "cause"
    queue.append(_payload(("cause", "직장 변화로 인한 스트레스")))
    chat.handle_message("ungrounded", "이직한 뒤로 그래요", _settings())
    assert session.slots["cause"] == "이직한 뒤로 그래요"
    assert session.slot_evidence["cause"]["method"] == "fallback"


def test_reply_call_cannot_overwrite_classified_free_text(stub, monkeypatch):
    queue, calls = stub
    monkeypatch.setattr(llm, "ask", lambda **kwargs: (
        '알겠어요.\n```slots\n{"track":"정서","coping":"모델이 지어낸 대처"}\n```'))
    session = _session("owner")
    queue.append(_payload(("chief_complaint", "잠을 못 자요")))
    chat.handle_message("owner", "잠을 못 자요", _settings())
    assert session.slots["track"] == "정서"
    assert "coping" not in session.slots


def test_retry_after_reply_failure_counts_once_and_keeps_one_pending_copy(stub, monkeypatch):
    queue, _ = stub
    replies = iter([llm.ModelBackendError("model backend unavailable: APITimeoutError"), REPLY])

    def ask(**kwargs):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(llm, "ask", ask)
    session = _session("retry")
    payload = _payload(("onset_impact", "두세 달 됐어요"), answered="no")
    queue.extend([payload, payload])
    message = "안녕하세요. 두세 달 됐어요."
    first = chat.handle_message("retry", message, _settings(), request_id="retry-classified-0001")
    assert first["processing_status"] == "retryable"
    second = chat.handle_message("retry", message, _settings(), request_id="retry-classified-0001")
    assert "processing_status" not in second
    assert session.turns == 1
    assert session.slot_misses == {"chief_complaint": 1}
    assert [item["quote"] for item in session.pending_slot_items] == ["두세 달 됐어요"]


def test_crisis_and_cli_models_do_not_classify(stub):
    queue, calls = stub
    session = _session("crisis", track="위기", chief_complaint="힘들어요")
    session.crisis_ever_detected = True
    chat.handle_message("crisis", "잘 모르겠어요", _settings())
    assert calls["classify"] == []
    assert not chat._uses_answer_classifier(chat._get_session("cli"), _schema(),
                                            Settings(anthropic_api_key="", knowledge_dir=PACK, model="codex-cli",
                                                     trust_proxy_hops=0, daily_request_cap=500))


# Independent review (Codex Astra, 2026-11-09) reproductions -------------------------------

def test_quotes_come_from_the_redacted_wording(stub):
    queue, calls = stub
    session = _session("redact")
    queue.append(_payload(("chief_complaint", "그냥 다 버거워요"), ("relationship_target", "홍길동")))
    chat.handle_message("redact", "그냥 다 버거워요. 힘들게 하는 사람 이름은 홍길동입니다.", _settings())
    assert "홍길동" not in calls["classify"][0]["user"]
    assert session.slots["chief_complaint"] == "그냥 다 버거워요"
    stored = json.dumps([session.slots, session.pending_slot_items], ensure_ascii=False)
    assert "홍길동" not in stored


def test_reply_call_crisis_escalation_keeps_plan_and_means(stub, monkeypatch):
    queue, _ = stub
    monkeypatch.setattr(llm, "ask", lambda **kwargs: (
        '많이 지치셨겠어요.\n```slots\n{"track":"위기","crisis_plan_means":"방 안에 끈을 준비해 뒀어요"}\n```'))
    session = _session("escalate", track="정서", chief_complaint="힘들어요")
    queue.append(_payload(answered="no"))
    result = chat.handle_message("escalate", "곧 마지막 페이지를 덮으려고요. 방 안에 끈을 준비해 뒀어요.", _settings())
    assert session.slots["track"] == "위기"
    assert session.slots["crisis_plan_means"] == "방 안에 끈을 준비해 뒀어요"
    assert "109" in result["reply"] and "119" in result["reply"]


def test_correction_is_kept_next_to_what_it_corrects(stub):
    queue, _ = stub
    session = _session("correct", track="정서", chief_complaint="불안해요", symptom_context="한 달 전부터")
    session.history.append({"role": "assistant", "content": "그렇군요. 계기가 있을까요?"})
    session.last_question_slot_id = "cause"
    payload = json.loads(_payload(("onset_impact", "두 달 전부터 그랬어요")))
    payload["items"][0]["correction"] = True
    queue.append(json.dumps(payload, ensure_ascii=False))
    chat.handle_message("correct", "한 달이 아니라 두 달 전부터 그랬어요.", _settings())
    assert session.slots["symptom_context"] == "한 달 전부터 / 정정: 두 달 전부터 그랬어요"


def test_pending_quotes_land_even_when_this_turn_falls_back(stub):
    queue, _ = stub
    session = _session("pending-fallback")
    queue.append(_payload(("chief_complaint", "그냥 요즘 다 버거워요"), ("onset_impact", "두세 달 됐어요")))
    chat.handle_message("pending-fallback", "그냥 요즘 다 버거워요. 두세 달 됐어요.", _settings())
    queue.append(llm.ModelBackendError("model backend unavailable: APITimeoutError"))
    result = chat.handle_message("pending-fallback", "기분 쪽이요. 우울하고 불안해요.", _settings())
    assert session.slots["track"] == "정서"
    assert session.slots["symptom_context"] == "두세 달 됐어요"
    assert result["intake"]["unfilled"][0]["id"] == "cause"


def test_pending_quote_keeps_its_own_source_after_a_failed_reply(stub, monkeypatch):
    queue, _ = stub
    replies = iter([llm.ModelBackendError("model backend unavailable: APITimeoutError"), REPLY, REPLY])

    def ask(**kwargs):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(llm, "ask", ask)
    session = _session("provenance")
    queue.append(_payload(("chief_complaint", "그냥 요즘 다 버거워요"), ("onset_impact", "두세 달 됐어요")))
    first = chat.handle_message("provenance", "그냥 요즘 다 버거워요. 두세 달 됐어요.", _settings(),
                                request_id="provenance-0001")
    assert first["processing_status"] == "retryable"
    first_source = session.pending_slot_items[0]["source"]
    queue.extend([_payload(answered="no"), _payload(answered="no")])
    chat.handle_message("provenance", "글쎄요.", _settings(), request_id="provenance-0002")
    chat.handle_message("provenance", "기분 쪽이요. 우울하고 불안해요.", _settings(), request_id="provenance-0003")
    assert session.slots["symptom_context"] == "두세 달 됐어요"
    assert session.slot_evidence["symptom_context"]["source"] == first_source
    assert session.slot_evidence["symptom_context"]["source_turn"] == 1


@pytest.mark.parametrize("bad", [[], {}])
def test_non_string_slot_key_is_a_classification_error(bad):
    keys = answer_classifier.catalog(_schema())
    raw = json.dumps({"answered_asked": "no", "items": [{"slot": bad, "quote": "x", "status": "answered",
                                                        "correction": False, "explicit": True, "aspect": "none"}]})
    with pytest.raises(answer_classifier.ClassifyError):
        answer_classifier.parse(raw, keys)


# Re-review (Codex Astra, thread 01a1bbf4) -------------------------------------------------

def test_correction_back_to_an_earlier_value_is_kept(stub):
    queue, _ = stub
    session = _session("recorrect", track="정서", chief_complaint="불안해요",
                       symptom_context="한 달 전부터 / 정정: 두 달 전부터")
    session.history.append({"role": "assistant", "content": "그렇군요. 계기가 있을까요?"})
    session.last_question_slot_id = "cause"
    payload = json.loads(_payload(("onset_impact", "한 달 전부터", "answered", True, "timing")))
    payload["items"][0]["correction"] = True
    queue.append(json.dumps(payload, ensure_ascii=False))
    chat.handle_message("recorrect", "다시 생각해 보니 한 달 전부터예요.", _settings())
    assert session.slots["symptom_context"] == "한 달 전부터 / 정정: 두 달 전부터 / 정정: 한 달 전부터"


def test_slot_answered_before_this_turn_gets_no_follow_up(stub):
    queue, _ = stub
    schema = _schema()
    coping = next(slot for slot in schema.slots if slot.id == "coping")
    # A session saved before slot_aspects/slot_followups existed: the timing slot already has a value.
    session = _session("legacy", track="정서", chief_complaint="불안해요", symptom_context="한 달 전부터 잠을 못 자요",
                       cause="이사")
    session.history.append({"role": "assistant", "content": "그렇군요. " + coping.ask})
    session.last_question_slot_id = "coping"
    queue.append(_payload(("coping", "산책했어요"), ("onset_impact", "두 달 전부터예요", "answered", True, "timing")))
    result = chat.handle_message("legacy", "산책했어요. 한 달이 아니라 두 달 전부터예요.", _settings())
    assert session.slot_followups.get("symptom_context") == "done"
    assert result["intake"]["unfilled"][0]["id"] == "support"
