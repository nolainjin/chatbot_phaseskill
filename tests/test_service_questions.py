"""Second round (2026-11-09): questions about the service, '없음' answers, family-fear notes,
mixed first messages, and the closing step that used to loop on "다시 시도".

All model calls are stubbed; no network or model process is used.
"""

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from app import answer_classifier, chat, closing, cloud_store, consent, intake, llm, portal_store, service_questions
from app.config import Settings

PACK = str(Path(__file__).resolve().parent.parent / "knowledge-maeum")
REPLY = "말씀해 주셔서 고마워요.\n```slots\n{}\n```"
APPROVED_FAMILY = ("이 대화는 네모네모 상담센터 담당자만 확인해요. 이 서비스가 엄마나 다른 가족에게 내용을 보내지는 않아요. "
                   "다만 자신이나 다른 사람을 해칠 위험이 있거나 학대가 의심될 때, 법적 요청이 있을 때는 비밀보장에 "
                   "예외가 생길 수 있어요. 센터가 보호자에게 연락하는 기준이 궁금하면 ‘센터에 묻고 싶은 것’으로 남겨 둘 수 있어요.")


def _settings(model="claude-test"):
    return Settings(anthropic_api_key="test-key", knowledge_dir=PACK, model=model,
                    trust_proxy_hops=0, daily_request_cap=500)


def _schema():
    return intake.load_schema(PACK)


def _slot(slot_id):
    return next(slot for slot in _schema().slots if slot.id == slot_id)


def _payload(*items, answered="yes", topic="none", question="", track="none", attention=()):
    rows = [{"slot": key, "quote": quote, "status": status, "correction": False, "explicit": True,
             "aspect": aspect} for key, quote, status, aspect in
            (tuple(item) + ("answered", "none")[len(item) - 2:] for item in items)]
    return json.dumps({"answered_asked": answered, "items": rows,
                       "service_question": {"topic": topic, "quote": question}, "primary_track": track,
                       "attention": [{"quote": quote, "reason": "family_fear"} for quote in attention]},
                      ensure_ascii=False)


@pytest.fixture
def stub(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(chat, "_sessions", {})
    monkeypatch.setenv("KNOWLEDGE_DIR", PACK)
    queue = []

    def classify(system, user, settings, json_schema=None):
        response = queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(llm, "classify", classify)
    monkeypatch.setattr(llm, "ask", lambda **kwargs: REPLY)
    return queue


def _asked(session_id, slot_id, text, **slots):
    session = chat._get_session(session_id)
    session.slots.update(slots)
    session.history.append({"role": "assistant", "content": "그렇군요. " + text})
    session.last_question_slot_id = slot_id
    return session


def _answer(topic, message="", center=None):
    return service_questions.compose(topic, _schema(), center=center, message=message,
                                     privacy=consent.load_privacy(PACK, _settings()))


@pytest.mark.parametrize("message, topic", [
    ("근데 이거 엄마한테 내용이 전달되거나 그러진 않죠?", "family"),
    ("이거 부모님도 볼 수 있어요?", "family"),
    ("혹시 이거 가족한테도 연락이 가나요?", "family"),
    ("이 이야기는 누가 보게 되나요?", "who_sees"),
    ("나중에 이 내용 지울 수도 있어요?", "deletion"),
    ("이거 얼마 동안 저장돼요?", "retention"),
    ("보내면 그 다음엔 어떻게 돼요?", "next_steps"),
    ("이거 꼭 다 대답해야 돼요?", "skip_ok"),
    ("지금 저랑 얘기하는 거 사람이에요?", "ai"),
    ("상담비는 얼마예요?", "center_matter"),
    ("엄마가 제 휴대폰을 봐요", None),
    ("엄마랑 학교에 가요", None),
    ("엄마 때문에 아무것도 하기 무서워요", None),
    ("상담에서 불안을 줄이고 싶어요", None),
])
def test_keyword_topic_and_statements(message, topic):
    assert service_questions.detect(message) == topic


def test_answers_fill_center_family_and_days():
    schema = _schema()
    assert set(schema.service_answers) == set(service_questions.TOPICS)
    assert _answer("family", "근데 이거 엄마한테 내용이 전달되거나 그러진 않죠?", "네모네모 상담센터") == APPROVED_FAMILY
    assert service_questions.family_phrase("부모님도 볼 수 있어요?") == "부모님이나 다른 가족에게"
    assert service_questions.family_phrase("남편이 알게 되나요?") == "남편이나 다른 가족에게"
    assert service_questions.family_phrase("가족한테 가나요?") == "가족에게"
    assert service_questions.family_phrase("이거 누가 봐요?") == "가족에게"
    assert "90일" in _answer("retention") and "365일" in _answer("retention")
    assert "7일" in _answer("deletion")
    assert _answer("who_sees").startswith("이 대화는 접수를 맡긴 센터 담당자만")
    for topic in service_questions.TOPICS:
        assert "{" not in _answer(topic, "엄마도 봐요?")
    assert _answer(None) is None and _answer("weather") is None


def test_parse_accepts_new_fields_and_rejects_bad_ones():
    keys = answer_classifier.catalog(_schema())
    parsed = answer_classifier.parse(_payload(("coping", "아니", "none"), topic="family", question="엄마도 봐요",
                                              track="정서", attention=["엄마 때문에 무서워요"]), keys)
    assert parsed["service_question"] == {"topic": "family", "quote": "엄마도 봐요"}
    assert parsed["primary_track"] == "정서" and parsed["items"][0]["status"] == "none"
    old_shape = json.dumps({"answered_asked": "no", "items": []})
    assert answer_classifier.parse(old_shape, keys)["service_question"] is None
    for bad in ({"service_question": {"topic": "weather", "quote": ""}}, {"primary_track": "위기"},
                {"attention": [{"quote": "x", "reason": "other"}]}):
        with pytest.raises(answer_classifier.ClassifyError):
            answer_classifier.parse(json.dumps({"answered_asked": "no", "items": [], **bad}), keys)


def test_mid_intake_question_is_answered_and_the_waiting_part_is_asked_again(stub):
    symptom = _slot("symptom_context")
    session = _asked("q1", "symptom_context", symptom.ask_impact, track="정서", chief_complaint="불안해요",
                     symptom_context="몇 달째")
    session.slot_followups["symptom_context"] = "impact"
    session.slot_aspects["symptom_context"] = ["timing"]
    message = "근데 이거 엄마도 볼 수 있어요?"
    stub.append(_payload(answered="no", topic="family", question=message))
    result = chat.handle_message("q1", message, _settings())
    assert result["reply"] == _answer("family", message) + "\n\n" + symptom.ask_impact
    assert session.slot_followups["symptom_context"] == "impact"  # the one-time part is not used up
    assert session.slot_misses == {} and session.slots["symptom_context"] == "몇 달째"
    assert session.last_question_slot_id == "symptom_context"


def test_question_with_an_answer_moves_on(stub):
    cause = _slot("cause")
    session = _asked("q2", "cause", cause.ask, track="정서", chief_complaint="불안해요",
                     symptom_context="석 달 전부터 / 배가 아파요")
    message = "가족한테 알려지는 건 아니죠? 아무튼 계기는 보고서 실수였던 것 같아요."
    stub.append(_payload(("cause", "계기는 보고서 실수였던 것 같아요"), topic="family",
                         question="가족한테 알려지는 건 아니죠?"))
    result = chat.handle_message("q2", message, _settings())
    assert session.slots["cause"] == "계기는 보고서 실수였던 것 같아요"
    assert result["reply"].startswith(_answer("family", message))
    assert _slot("coping").ask in result["reply"] and session.last_question_slot_id == "coping"


def test_keyword_path_answers_without_storing_the_question(stub):
    symptom = _slot("symptom_context")
    session = _asked("q3", "symptom_context", symptom.ask, track="정서", chief_complaint="불안해요")
    message = "근데 이거 엄마도 볼 수 있어요?"
    result = chat.handle_message("q3", message, _settings("fake"))
    assert result["reply"].startswith(_answer("family", message))
    assert symptom.ask in result["reply"]
    assert "symptom_context" not in session.slots and session.last_question_slot_id == "symptom_context"


def test_bare_none_is_stored_as_owned_wording_and_gives_way_to_a_real_answer(stub):
    coping = _slot("coping")
    session = _asked("n1", "coping", coping.ask, track="정서", chief_complaint="불안해요",
                     symptom_context="석 달 전부터 / 배가 아파요", cause="실수")
    stub.append(_payload(("coping", "아니")))  # the model kept the bare word as an answer
    chat.handle_message("n1", "아니", _settings())
    assert session.slots["coping"] == coping.none_value == "해 본 대처 없음"
    stub.append(_payload(("support", "없어요", "none")))
    chat.handle_message("n1", "없어요", _settings())
    assert session.slots["support"] == _slot("support").none_value
    placed = answer_classifier.place([{"key": "coping", "quote": "산책은 해 봤어요", "status": "answered",
                                       "explicit": True, "aspect": "none"}],
                                     _schema(), dict(session.slots), {}, None)
    assert placed.fills["coping"] == "산책은 해 봤어요"
    kept = answer_classifier.place([{"key": "coping", "quote": "딱히요", "status": "none", "explicit": True,
                                     "aspect": "none"}], _schema(), {**session.slots, "coping": "산책"}, {}, None)
    assert "coping" not in kept.fills


def test_family_fear_is_noted_whole_with_its_source(stub):
    coping = _slot("coping")
    session = _asked("f1", "coping", coping.ask, track="정서", chief_complaint="불안해요",
                     symptom_context="석 달 전부터 / 배가 아파요", cause="실수")
    message = "아니.. 엄마때문에 아무것도 하기 무서워요"
    stub.append(_payload(("coping", "아니", "none"), ("onset_impact", "아무것도 하기 무서워요", "answered", "impact"),
                         attention=["엄마때문에 아무것도 하기 무서워요"]))
    chat.handle_message("f1", message, _settings())
    assert session.slots["coping"] == "해 본 대처 없음"
    assert session.attention_notes == [{"text": "엄마때문에 아무것도 하기 무서워요", "reason": "family_fear",
                                        "source_turn": 1}]
    evidence = session.slot_evidence["attention:0"]
    assert evidence["label"] == "상담사 확인 필요" and evidence["source"]["role"] == "user"
    summary = chat._session_summary(session, _schema())
    assert summary["attention_notes"] == [{"text": "엄마때문에 아무것도 하기 무서워요", "reason": "family_fear"}]


def test_keyword_net_notes_family_fear_once_when_the_model_misses_it(stub):
    coping = _slot("coping")
    session = _asked("f2", "coping", coping.ask, track="정서", chief_complaint="불안해요")
    stub.append(_payload(("coping", "아니요", "none")))
    chat.handle_message("f2", "아니요.. 엄마 때문에 뭘 해 보기가 겁나요.", _settings())
    assert [note["text"] for note in session.attention_notes] == ["엄마 때문에 뭘 해 보기가 겁나요."]
    chat.handle_message("f2", "엄마 때문에 뭘 해 보기가 겁나요.", _settings("fake"))
    assert len(session.attention_notes) == 1


def test_keyword_net_takes_sentences_from_the_redacted_wording(stub):
    session = _asked("f3", "coping", _slot("coping").ask, track="정서", chief_complaint="불안해요")
    chat.handle_message("f3", "제 이름은 김민수인데 아빠가 무서워요. 010-1234-5678로 연락 오면 집에 있기가 겁나요.",
                        _settings("fake"))
    joined = " ".join(note["text"] for note in session.attention_notes)
    assert "김민수" not in joined and "010-1234-5678" not in joined
    assert "[redacted-name]" in joined and "[redacted-phone]" in joined


@pytest.mark.parametrize("track, expected", [("정서", "정서"), ("관계", "관계"), ("unclear", None)])
def test_mixed_first_message_lets_the_classifier_pick_the_track(stub, track, expected):
    session = chat._get_session("t1")
    message = "밤에 잠이 안 오고 무기력하고, 친구들이랑도 사이가 안좋아요."
    stub.append(_payload(("chief_complaint", "밤에 잠이 안 오고 무기력하고"),
                         ("chief_complaint", "친구들이랑도 사이가 안좋아요"), answered="yes", track=track))
    result = chat.handle_message("t1", message, _settings())
    assert session.slots.get("track") == expected
    assert session.slots["chief_complaint"] == "밤에 잠이 안 오고 무기력하고 / 친구들이랑도 사이가 안좋아요"
    if expected is None:
        assert _slot("track").ask in result["reply"]
    else:
        assert session.track_inferred is (expected != "관계")


def _closing(session_id="c1"):
    session = chat._get_session(session_id)
    session.turns = 6
    session.closing_started = True
    session.slots = {"track": "정서", "chief_complaint": "불안해요"}
    return session


def test_closing_question_is_answered_not_retried(stub):
    session = _closing()
    message = "근데 이거 엄마한테 내용이 전달되거나 그러진 않죠?"
    stub.append(json.dumps({"items": [], "corrections": [], "needs_clarification": False,
                            "service_question": {"topic": "family", "quote": message}}, ensure_ascii=False))
    result = chat.handle_message("c1", message, _settings())
    assert result["processing_status"] == "saved" and not result.get("retryable")
    assert result["reply"].startswith(_answer("family", message) + "\n\n" + _schema().closing["question"])
    assert session.center_requests == [] and session.closing_draft is None
    assert session.history[-1]["role"] == "assistant"


def test_closing_with_nothing_to_forward_is_not_an_error(stub):
    session = _closing()
    stub.append(json.dumps({"items": [], "corrections": [], "needs_clarification": False,
                            "service_question": {"topic": "none", "quote": ""}}))
    result = chat.handle_message("c1", "음..", _settings())
    assert result["processing_status"] == "saved"
    assert result["reply"].startswith("괜찮아요. " + _schema().closing["question"])
    assert session.closing_analysis_pending is None


def test_unclear_closing_note_does_not_block_the_offered_send(stub):
    session = _closing()
    stub.append(json.dumps({"items": [], "corrections": [], "needs_clarification": True,
                            "service_question": {"topic": "none", "quote": ""}}))
    asked = chat.handle_message("c1", "음..", _settings())
    assert "더 구체적으로" in asked["reply"] and asked["quick_replies"][-1]["action"] == "send"
    sent = chat.handle_message("c1", "확인한 내용 전달하기", _settings())
    assert sent["handoff"]["sent"] and session.center_requests == []


def test_question_after_choosing_a_center_note_becomes_that_note(stub):
    session = _closing()
    chat.handle_message("c1", "센터에 묻고 싶은 것", _settings())
    message = "엄마한테 연락이 가나요?"
    stub.append(json.dumps({"items": [], "corrections": [], "needs_clarification": False,
                            "service_question": {"topic": "family", "quote": message}}, ensure_ascii=False))
    result = chat.handle_message("c1", message, _settings())
    assert result["closing"]["stage"] == "confirm"
    assert session.closing_draft["items"][0]["label"] == "센터에 묻고 싶은 것"
    assert session.closing_draft["items"][0]["text"] == message


def test_fake_closing_answers_service_questions_and_forwards_center_matters(stub):
    session = _closing()
    result = chat.handle_message("c1", "이거 선생님 말고 누가 또 봐요?", _settings("fake"))
    assert result["reply"].startswith(_answer("who_sees")) and session.closing_draft is None
    result = chat.handle_message("c1", "주차는 되나요?", _settings("fake"))
    assert session.closing_draft["items"][0]["category"] == "center_question"
    assert closing.analyze("음..", _settings("fake"))["service_topic"] is None


def test_attention_notes_are_redacted_in_cloud_state_and_dropped_after_retention(monkeypatch):
    monkeypatch.setattr(chat, "_sessions", {})
    saved = {}

    @contextmanager
    def transaction(_name):
        yield

    monkeypatch.setenv("MAEUM_DATABASE_URL", "postgresql://unused")
    monkeypatch.delenv("PORTAL_ENABLED", raising=False)
    monkeypatch.setattr(cloud_store, "transaction", transaction)
    monkeypatch.setattr(cloud_store, "get", lambda kind, key, default=None: None)
    monkeypatch.setattr(cloud_store, "put", lambda kind, key, value: saved.setdefault(key, value))
    with cloud_store.session_scope("redact-1"):
        session = chat._get_session("redact-1")
        session.attention_notes.append({"text": "아빠가 010-1234-5678로 전화하면 무서워요", "reason": "family_fear"})
    assert "010-1234-5678" not in json.dumps(saved["redact-1"]["attention_notes"], ensure_ascii=False)
    retained = portal_store.retained_summary({"slots": {"track": "정서"}, "attention_notes": [{"text": "x"}]})
    assert "attention_notes" not in retained


# --- independent review (Codex, 3rd) regressions ---------------------------------------------

def test_owned_answer_keeps_the_hotline_the_model_pointed_to(stub, monkeypatch):
    symptom = _slot("symptom_context")
    session = _asked("r0", "symptom_context", symptom.ask, track="정서", chief_complaint="불안해요")
    monkeypatch.setattr(llm, "ask", lambda **kwargs: "지금 많이 위험하게 들려요. 109에 바로 연락해 주세요.\n```slots\n{}\n```")
    message = "오늘 밤 다 끝낼 거예요. 가족한테 알려지나요?"
    stub.append(_payload(answered="no", topic="family", question="가족한테 알려지나요?"))
    result = chat.handle_message("r0", message, _settings())
    assert result["reply"].startswith(_answer("family", message))
    for required in ("109", "1577-0199", "1588-9191", "119"):
        assert required in result["reply"]
    assert session.slots.get("track") == "정서"


def test_keyword_path_keeps_an_answer_said_with_the_question(stub):
    symptom = _slot("symptom_context")
    session = _asked("r1", "symptom_context", symptom.ask, track="정서", chief_complaint="불안해요")
    message = "한 달 전부터예요. 엄마한테도 전달되나요?"
    result = chat.handle_message("r1", message, _settings("fake"))
    assert session.slots["symptom_context"] == "한 달 전부터예요."
    assert result["reply"].startswith(_answer("family", message))


def test_fake_closing_reads_the_note_beside_a_question(stub):
    session = _closing()
    message = "평일 저녁에 가능해요. 그리고 엄마한테 연락 가나요?"
    result = chat.handle_message("c1", message, _settings("fake"))
    assert session.closing_draft["items"][0]["text"] == "평일 저녁에 가능해요."
    assert result["reply"].startswith(_answer("family", message))


def test_family_fear_at_the_closing_step_is_noted_with_its_source(stub):
    session = _closing()
    chat.handle_message("c1", "엄마 때문에 무서워요.", _settings("fake"))
    assert [note["text"] for note in session.attention_notes] == ["엄마 때문에 무서워요."]
    assert session.slot_evidence["attention:0"]["source"]["role"] == "user"


def test_short_model_quote_grows_to_its_whole_sentence(stub):
    session = _asked("r4", "coping", _slot("coping").ask, track="정서", chief_complaint="불안해요")
    stub.append(_payload(("coping", "아니요", "none"), attention=["무서워요"]))
    chat.handle_message("r4", "아니요. 엄마 때문에 무서워요.", _settings())
    assert [note["text"] for note in session.attention_notes] == ["엄마 때문에 무서워요."]


def test_service_questions_do_not_use_up_the_track_question(stub):
    track = _slot("track")
    session = _asked("r5", "track", track.ask, chief_complaint="잠도 안 오고 친구랑도 사이가 안 좋아요")
    for question in ("이거 누가 봐요?", "이거 얼마 동안 저장돼요?", "이거 지울 수 있나요?"):
        result = chat.handle_message("r5", question, _settings("fake"))
        assert track.ask in result["reply"]
    assert session.track_questions == 0 and "track" not in session.slots


def test_question_after_choosing_another_note_is_answered_not_forwarded(stub):
    session = _closing()
    chat.handle_message("c1", "상담 가능한 요일·시간", _settings())
    message = "엄마한테 연락이 가나요?"
    stub.append(json.dumps({"items": [], "corrections": [], "needs_clarification": False,
                            "service_question": {"topic": "family", "quote": message}}, ensure_ascii=False))
    result = chat.handle_message("c1", message, _settings())
    assert result["reply"].startswith(_answer("family", message))
    assert session.closing_draft is None and session.closing_pending == "상담 가능한 요일·시간"


def test_attention_source_survives_a_failed_reply_and_its_retry(stub, monkeypatch):
    session = _asked("r7", "coping", _slot("coping").ask, track="정서", chief_complaint="불안해요")

    def failing(**kwargs):
        raise RuntimeError("timeout")

    monkeypatch.setattr(llm, "ask", failing)
    stub.append(_payload(("coping", "아니요", "none")))
    failed = chat.handle_message("r7", "아니요. 아빠가 무서워요.", _settings(), request_id="req-retry-0001")
    assert failed["processing_status"] == "retryable"
    assert session.slot_evidence["attention:0"]["source"]["role"] == "user"
    monkeypatch.setattr(llm, "ask", lambda **kwargs: REPLY)
    stub.append(_payload(("coping", "아니요", "none")))
    chat.handle_message("r7", "아니요. 아빠가 무서워요.", _settings(), request_id="req-retry-0001")
    assert len(session.attention_notes) == 1 and "source" in session.slot_evidence["attention:0"]


def test_placeholder_typo_never_reaches_the_screen(tmp_path):
    import shutil

    from app import knowledge_pack

    class Broken:
        service_answers = {"retention": "원문은 {raw_day}일 보관해요."}

    assert service_questions.compose("retention", Broken()) is None
    pack = tmp_path / "pack"
    shutil.copytree(PACK, pack)
    schema_file = pack / "_intake_schema.md"
    schema_file.write_text(schema_file.read_text(encoding="utf-8").replace("{raw_days}일, 요약", "{raw_day}일, 요약"),
                           encoding="utf-8")
    codes = [issue.code for issue in knowledge_pack.validate_pack(pack).errors]
    assert "SCHEMA_SERVICE_ANSWERS" in codes


# --- confirmation review (Codex, 4th) regressions --------------------------------------------

@pytest.mark.parametrize("model_reply", [
    "지금 위험하게 들려요. 109에 바로 연락해 주세요.",
    "집이 위험하면 112에 바로 신고해 주세요.",
])
def test_hotline_the_model_gave_survives_an_ordinary_turn(stub, monkeypatch, model_reply):
    symptom = _slot("symptom_context")
    _asked("h0", "symptom_context", symptom.ask, track="정서", chief_complaint="불안해요")
    monkeypatch.setattr(llm, "ask", lambda **kwargs: model_reply + "\n```slots\n{}\n```")
    stub.append(_payload(("onset_impact", "한 달째", "answered", "timing")))
    message = "한 달째예요. 요즘은 아무것도 하기 싫어요"
    assert not intake.crisis_signal_present(message, _schema())  # the ordinary path, not the crisis route
    result = chat.handle_message("h0", message, _settings())
    for required in ("109", "1577-0199", "1588-9191", "119"):
        assert required in result["reply"]


def test_counting_words_are_not_hotlines():
    assert not chat._mentions_hotline("109일째 이어지고 있다고 하셨어요")
    assert chat._mentions_hotline("112에 신고해 주세요") and chat._mentions_hotline("1388로 연락해요")


@pytest.mark.parametrize("message, kept", [
    ("한 달 전부터예요.엄마한테도 전달되나요?", "한 달 전부터예요."),
    ("한 달 전부터 힘든데 엄마한테도 전달되나요?", "한 달 전부터 힘든데"),
    ("한 달 전부터 힘들고, 엄마한테도 전달되나요?", "한 달 전부터 힘들고,"),
])
def test_answer_beside_a_question_survives_without_spaces_or_in_one_sentence(message, kept):
    assert service_questions.strip_questions(message) == kept


def test_short_quote_does_not_pull_in_an_unrelated_sentence(stub):
    session = _asked("h3", "coping", _slot("coping").ask, track="정서", chief_complaint="불안해요")
    stub.append(_payload(("coping", "아니요", "none"), attention=["무서워요"]))
    chat.handle_message("h3", "아니요. 학교가 무서워요. 엄마 때문에 무서워요.", _settings())
    assert session.slot_evidence["coping"]["method"] == "classifier"  # the model's quote was used
    assert [note["text"] for note in session.attention_notes] == ["엄마 때문에 무서워요."]


def test_unclear_but_substantive_note_is_kept_when_sent(stub):
    session = _closing()
    message = "그건 좀 그런 것 같아요"
    stub.append(json.dumps({"items": [], "corrections": [], "needs_clarification": True,
                            "service_question": {"topic": "none", "quote": ""}}))
    asked = chat.handle_message("c1", message, _settings())
    assert "더 구체적으로" in asked["reply"]
    sent = chat.handle_message("c1", "확인한 내용 전달하기", _settings())
    assert sent["handoff"]["sent"] and session.center_requests == [{"label": "센터에 전할 내용", "text": message}]


@pytest.mark.parametrize("broken", ["원문은 {raw_days일 보관해요.", "원문은 {raw_days}}일 보관해요.", "{0} 보관"])
def test_malformed_braces_are_rejected_not_raised(broken):
    class Broken:
        service_answers = {"retention": broken}

    assert service_questions.unknown_fields(broken)
    assert service_questions.compose("retention", Broken()) is None


# --- server-side refusal fallback for Opus/Sonnet classification ------------------------------

@pytest.mark.parametrize("classify_model, expect_beta", [
    ("claude-opus-5-5", True), ("claude-sonnet-5-5", True), ("claude-haiku-5-5", False), ("", False)])
def test_classification_on_opus_or_sonnet_asks_for_the_server_fallback(monkeypatch, classify_model, expect_beta):
    from types import SimpleNamespace

    import anthropic
    seen = {}
    response = SimpleNamespace(stop_reason="end_turn", model=classify_model or "claude-haiku-5-5",
                               content=[SimpleNamespace(type="text", text='{"ok":true}')])

    class Endpoint:
        def __init__(self, name):
            self.name = name

        def create(self, **kwargs):
            seen.update(endpoint=self.name, **kwargs)
            return response

    class Client:
        def __init__(self, **kwargs):
            self.messages = Endpoint("messages")
            self.beta = SimpleNamespace(messages=Endpoint("beta"))

    monkeypatch.setattr(anthropic, "Anthropic", Client)
    settings = Settings(anthropic_api_key="k", knowledge_dir=PACK, model="claude-haiku-5-5", trust_proxy_hops=0,
                        daily_request_cap=500, classify_model=classify_model, classify_effort="low")
    assert llm.classify("s", "u", settings, {"type": "object"}) == '{"ok":true}'
    assert seen["model"] == (classify_model or "claude-haiku-5-5")
    assert (seen["endpoint"] == "beta") is expect_beta
    if expect_beta:
        assert seen["fallbacks"] == "default" and seen["betas"] == [llm.SERVER_FALLBACK_BETA]
    else:
        assert "fallbacks" not in seen and "betas" not in seen


def test_reflection_that_only_announces_a_check_is_not_kept():
    # Seen in a replay: the model raised a home-safety check, then the owned question moved on.
    question = "이번 상담에서 어떤 도움을 가장 기대하시나요?"
    reply = "집에서 몸이 다치거나 안전이 위협받는다고 느끼는 일이 있었는지도 함께 확인하고 싶어요. " + question
    assert chat._center_reply_for_slot(reply, _slot("expectation"), question) == "말씀해 주셔서 감사합니다. " + question
    kept = chat._center_reply_for_slot("엄마의 기대가 무겁게 느껴지셨겠어요. " + question, _slot("expectation"), question)
    assert kept == "엄마의 기대가 무겁게 느껴지셨겠어요. " + question
