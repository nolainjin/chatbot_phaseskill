"""Synthetic regressions for evidence-bound closing analysis and confirmation."""

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import chat, closing, intake, llm, main, ratelimit, storage
from app.config import Settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(chat, "_sessions", {})
    monkeypatch.setenv("KNOWLEDGE_DIR", str(ROOT / "knowledge-maeum"))
    monkeypatch.setenv("MODEL", "fake")


def _ready():
    session = chat._get_session("semantic")
    session.turns = 9
    session.closing_started = True
    session.slots = {"track": "정서", "chief_complaint": "불안해요"}
    return session


def test_talking_preference_is_not_coping_substring():
    schema = intake.load_schema(ROOT / "knowledge-maeum")
    for message in (
        "상담사가 먼저 대화를 걸어 줬으면 해요",
        "상담사가 차분히 들어주면 좋겠어요",
        "상담사가 먼저 대화를 걸어서 편하게 해주면 좋겠어요",
        "산책을 해보고 싶어요",
        "상담에서는 불안을 다루는 방법을 배우고 싶어요.",
        "불안을 줄이는 방법을 알고 싶어요.",
    ):
        assert "coping" not in intake.extract_fake(message, schema, {"track": "정서"})
    assert intake.extract_fake("산책해봤어요", schema, {"track": "정서"})["coping"] == "산책해봤어요"
    assert closing.deterministic_category("상담사가 먼저 대화를 걸어 줬으면 해요") == "counselor_preference"


def test_free_text_requires_confirmation_before_delivery():
    session = _ready()
    result = chat.handle_message("semantic", "화요일 저녁 7시가 좋아요")
    assert result["closing"]["stage"] == "confirm"
    assert result["processing_status"] == "confirmation_required"
    assert session.handoff is None and session.center_requests == []
    sent = chat.handle_message("semantic", "이대로 보내기")
    assert sent["handoff"]["sent"]
    assert session.center_requests == [{"label": "상담 가능한 요일·시간", "text": "화요일 저녁 7시가 좋아요"}]


def test_strict_semantic_failure_preserves_input_and_is_retryable(monkeypatch):
    session = _ready()
    settings = replace(Settings.from_env(), model="codex-cli")
    monkeypatch.setattr(llm, "ask_strict", lambda **kw: (_ for _ in ()).throw(RuntimeError("timeout")))
    result = chat.handle_message("semantic", "부드럽게 진행해 주세요", settings)
    assert result["processing_status"] == "retryable" and result["retryable"]
    assert session.handoff is None and session.center_requests == []
    assert session.history[-1]["content"] == "부드럽게 진행해 주세요"


def test_model_evidence_must_be_actual_substring(monkeypatch):
    settings = replace(Settings.from_env(), model="codex-cli")
    monkeypatch.setattr(llm, "ask_strict", lambda **kw:
                        '```json\n{"items":[{"category":"coping","evidence":"산책했어요"}],'
                        '"needs_clarification":false}\n```')
    with pytest.raises(ValueError, match="source evidence"):
        closing.analyze("부드럽게 진행해 주세요", settings)


def test_real_analysis_keeps_multiple_evidence_bound_items(monkeypatch):
    message = "화요일 저녁이 좋고 주차가 가능한지 궁금해요"
    settings = replace(Settings.from_env(), model="codex-cli")
    monkeypatch.setattr(llm, "ask_strict", lambda **kw:
        '```json\n{"items":['
        '{"category":"preferred_time","evidence":"화요일 저녁이 좋고"},'
        '{"category":"center_question","evidence":"주차가 가능한지 궁금해요"}'
        '],"needs_clarification":false}\n```')
    assert [item["category"] for item in closing.analyze(message, settings)["items"]] == [
        "preferred_time", "center_question"]


def test_uncertain_analysis_asks_for_clarification_instead_of_retry(monkeypatch):
    _ready()
    settings = replace(Settings.from_env(), model="codex-cli")
    monkeypatch.setattr(llm, "ask_strict", lambda **kw:
                        '```json\n{"items":[],"needs_clarification":true}\n```')
    result = chat.handle_message("semantic", "그건 좀 그런 것 같아요", settings)
    assert result["closing"]["stage"] == "answer"
    assert result["processing_status"] == "saved"
    assert "더 구체적으로" in result["reply"]


def test_category_correction_preserves_other_draft_items(monkeypatch):
    session = _ready()
    session.closing_draft = {"label": "추가 전달 내용", "text": "기존", "items": [
        {"category": "preferred_time", "label": "시간", "text": "화요일 저녁", "source_text": "화요일 저녁"},
        {"category": "center_question", "label": "질문", "text": "주차가 되나요", "source_text": "주차가 되나요"},
    ]}
    session.closing_revision = True
    monkeypatch.setattr(closing, "analyze", lambda *a, **k: {"needs_clarification": False, "items": [
        {"category": "preferred_time", "evidence": "정정할게요, 토요일 오전이에요"}
    ]})
    result = chat.handle_message("semantic", "정정할게요, 토요일 오전이에요")
    items = result["closing"]["draft"]["items"]
    assert [(item["category"], item["text"]) for item in items] == [
        ("center_question", "주차가 되나요"),
        ("preferred_time", "정정할게요, 토요일 오전이에요"),
    ]


def test_selected_time_label_does_not_mislabel_semantic_counselor_item():
    analysis = {"items": [{"category": "counselor_preference", "evidence": "여성 상담사를 원해요"}],
                "corrections": [], "needs_clarification": False}
    item = chat._closing_items(analysis, "상담 가능한 요일·시간", 1)[0]
    assert item["label"] == "상담사에게 바라는 점"


def test_general_free_text_supplement_keeps_previous_value_and_revision():
    session = chat._get_session("supplement")
    session.slots["coping"] = "산책을 해봤어요"
    fills = {"coping": "일기도 써봤어요"}
    chat._record_slot_evidence(session, fills, "일기도 써봤어요")
    assert fills["coping"] == "산책을 해봤어요 / 일기도 써봤어요"


def test_slot_evidence_never_concatenates_closed_track_value():
    session = chat._get_session("closed-enum")
    session.slots["track"] = "정서"
    fills = {"track": "위기"}
    chat._record_slot_evidence(session, fills, "죽고 싶어요")
    assert fills == {"track": "위기"}
    assert session.slot_evidence["track"]["value"] == "위기"


def test_revision_summary_keeps_pointer_but_drops_raw_text():
    session = _ready()
    session.slot_revisions = [{
        "field": "coping", "before": "raw-before", "after": "raw-after",
        "source_text": "raw-source", "source_turn": 7,
        "source": {"day": "2026-11-05", "seq": 4, "role": "user"},
    }]
    schema = intake.load_schema(ROOT / "knowledge-maeum")
    revision = chat._session_summary(session, schema)["slot_revisions"][0]
    assert revision == {"field": "coping", "source_turn": 7,
                        "source": {"day": "2026-11-05", "seq": 4, "role": "user"}}
    projected = __import__("app.portal_store", fromlist=["projected_summary"]).projected_summary(
        {"slot_revisions": [revision]})
    assert projected["slot_revisions"] == [revision]


def test_api_request_id_replays_once_and_rejects_different_body(monkeypatch):
    monkeypatch.setattr(main, "_rate_limiter", ratelimit.RateLimiter())
    with TestClient(main.app) as client:
        consent = client.post("/api/consent", json={"session_id": "idem", "accepted": True,
                              "consent_version": "maeum-2026-11-05"}).json()
        payload = {"session_id": "idem", "session_token": consent["session_token"],
                   "message": "불안해요", "request_id": "request-0001"}
        first = client.post("/api/chat", json=payload)
        replay = client.post("/api/chat", json=payload)
        assert first.status_code == replay.status_code == 200
        assert first.json() == replay.json()
        assert chat._sessions["idem"].turns == 1
        assert client.post("/api/chat", json={**payload, "message": "다른 내용"}).status_code == 409


def test_retryable_request_id_reanalyzes_without_duplicate_user_turn(monkeypatch):
    monkeypatch.setattr(main, "_rate_limiter", ratelimit.RateLimiter())
    monkeypatch.setenv("MODEL", "codex-cli")
    monkeypatch.setattr(llm, "ask_strict", lambda **kw: (_ for _ in ()).throw(RuntimeError("timeout")))
    with TestClient(main.app) as client:
        consent = client.post("/api/consent", json={"session_id": "retry-idem", "accepted": True,
                              "consent_version": "maeum-2026-11-05"}).json()
        session = chat._sessions["retry-idem"]
        session.turns = 9
        session.closing_started = True
        session.slots = {"track": "정서", "chief_complaint": "불안해요"}
        payload = {"session_id": "retry-idem", "session_token": consent["session_token"],
                   "message": "부드럽게 진행해 주세요", "request_id": "retry-0001"}
        assert client.post("/api/chat", json=payload).json()["processing_status"] == "retryable"
        assert client.post("/api/chat", json=payload).json()["processing_status"] == "retryable"
        assert [turn for turn in session.history if turn["role"] == "user"] == [
            {"role": "user", "content": payload["message"]}
        ]


def test_retryable_request_id_then_success_reuses_original_user_turn(monkeypatch):
    monkeypatch.setattr(main, "_rate_limiter", ratelimit.RateLimiter())
    monkeypatch.setenv("MODEL", "codex-cli")
    calls = iter([
        RuntimeError("timeout"),
        '```json\n{"items":[{"category":"counselor_preference",'
        '"evidence":"부드럽게 진행해 주세요"}],"needs_clarification":false}\n```',
    ])

    def strict(**kwargs):
        value = next(calls)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(llm, "ask_strict", strict)
    with TestClient(main.app) as client:
        consent = client.post("/api/consent", json={"session_id": "retry-success", "accepted": True,
                              "consent_version": "maeum-2026-11-05"}).json()
        session = chat._sessions["retry-success"]
        session.turns = 9
        session.closing_started = True
        session.slots = {"track": "정서", "chief_complaint": "불안해요"}
        payload = {"session_id": "retry-success", "session_token": consent["session_token"],
                   "message": "부드럽게 진행해 주세요", "request_id": "retry-success-0001"}
        assert client.post("/api/chat", json=payload).json()["processing_status"] == "retryable"
        succeeded = client.post("/api/chat", json=payload).json()
        assert succeeded["processing_status"] == "confirmation_required"
        assert [turn for turn in session.history if turn["role"] == "user"] == [
            {"role": "user", "content": payload["message"]}
        ]
        assert session.turns == 10
        assert session.closing_draft["items"][0]["source"]["role"] == "user"
        assert session.closing_draft["items"][0]["source_turn"] == 10


def test_failed_revision_blocks_send_until_retry_or_explicit_cancel(monkeypatch):
    session = _ready()
    session.closing_draft = {"label": "추가 전달 내용", "text": "화요일", "items": [
        {"category": "preferred_time", "label": "시간", "text": "화요일", "source_text": "화요일"},
    ]}
    settings = replace(Settings.from_env(), model="codex-cli")
    monkeypatch.setattr(llm, "ask_strict", lambda **kw: (_ for _ in ()).throw(RuntimeError("timeout")))
    failed = chat.handle_message("semantic", "정정할게요, 토요일이에요", settings, request_id="revision-0001")
    assert failed["processing_status"] == "retryable"
    blocked = chat.handle_message("semantic", "이대로 보내기", settings, request_id="revision-send-0001")
    assert session.handoff is None
    assert "아직 전달할 수 없어요" in blocked["reply"]


@pytest.mark.parametrize("failure", [RuntimeError("timeout"), llm.ModelOutputTooLarge("large")])
def test_general_model_failures_preserve_input_as_retryable(monkeypatch, failure):
    settings = replace(Settings.from_env(), model="codex-cli")
    monkeypatch.setattr(llm, "ask", lambda **kw: (_ for _ in ()).throw(failure))
    result = chat.handle_message("general-failure", "오늘 불안해요", settings,
                                 request_id="general-failure-0001")
    assert result["processing_status"] == "retryable"
    assert result["retryable"] is True
    session = chat._sessions["general-failure"]
    assert [turn for turn in session.history if turn["role"] == "user"] == [
        {"role": "user", "content": "오늘 불안해요"}
    ]


def test_malformed_slot_envelope_is_retryable_not_guardrail_success(monkeypatch):
    settings = replace(Settings.from_env(), model="codex-cli")
    monkeypatch.setattr(llm, "ask", lambda **kw: "답변\n```slots\n{broken}\n")
    result = chat.handle_message("malformed-output", "오늘 불안해요", settings,
                                 request_id="malformed-output-0001")
    assert result["processing_status"] == "retryable"


def test_plain_none_response_does_not_implicitly_send():
    schema = intake.load_schema(ROOT / "knowledge-maeum")
    assert chat._closing_choice("없어요", schema) == (None, False)
    session = _ready()
    result = chat.handle_message("semantic", "없어요")
    assert session.handoff is None
    assert result["closing"]["stage"] == "confirm"
    assert [choice["action"] for choice in result["quick_replies"]] == ["add", "send"]
    assert "‘확인한 내용 전달하기’를 눌러야" in result["reply"]


def test_pending_analysis_without_draft_still_blocks_new_send_request(monkeypatch):
    session = _ready()
    settings = replace(Settings.from_env(), model="codex-cli")
    monkeypatch.setattr(llm, "ask_strict", lambda **kw: (_ for _ in ()).throw(RuntimeError("timeout")))
    assert chat.handle_message("semantic", "부드럽게 진행해 주세요", settings,
                               request_id="pending-no-draft-1")["processing_status"] == "retryable"
    blocked = chat.handle_message("semantic", "이대로 보내기", settings,
                                  request_id="pending-no-draft-send")
    assert session.handoff is None and "아직 전달할 수 없어요" in blocked["reply"]
    cancelled = chat.handle_message("semantic", "수정 취소", settings,
                                    request_id="pending-no-draft-cancel")
    assert session.closing_analysis_pending is None
    assert cancelled["closing"]["stage"] == "select"


def test_real_duplicate_fill_does_not_erase_fake_merged_previous_value(monkeypatch):
    session = chat._get_session("real-supplement")
    session.slots = {"track": "정서", "coping": "산책을 해봤어요"}
    session.last_question_slot_id = "coping"
    settings = replace(Settings.from_env(), model="codex-cli")
    monkeypatch.setattr(llm, "ask", lambda **kw:
        '알겠어요.\n```slots\n{"coping":"일기도 써봤어요"}\n```')
    chat.handle_message("real-supplement", "일기도 써봤어요", settings)
    assert session.slots["coping"] == "산책을 해봤어요 / 일기도 써봤어요"


def test_retry_repeated_supplement_keeps_combined_previous_value():
    session = chat._get_session("retry-merge")
    session.slots["coping"] = "산책을 해봤어요 / 일기도 써봤어요"
    fills = {"coping": "일기도 써봤어요"}
    chat._record_slot_evidence(session, fills, "일기도 써봤어요")
    assert fills["coping"] == "산책을 해봤어요 / 일기도 써봤어요"


def test_real_timeout_then_same_request_success_keeps_old_and_supplement(monkeypatch):
    session = chat._get_session("retry-real-merge")
    session.slots = {"track": "정서", "coping": "산책을 해봤어요"}
    session.last_question_slot_id = "coping"
    settings = replace(Settings.from_env(), model="codex-cli")
    responses = iter([
        llm.ModelBackendError("timeout"),
        '알겠어요.\n```slots\n{"coping":"일기도 써봤어요"}\n```',
    ])

    def ask(**kwargs):
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(llm, "ask", ask)
    request_id = "retry-real-merge-0001"
    first = chat.handle_message("retry-real-merge", "일기도 써봤어요", settings,
                                request_id=request_id)
    assert first["processing_status"] == "retryable"
    chat.handle_message("retry-real-merge", "일기도 써봤어요", settings,
                        request_id=request_id)
    assert session.slots["coping"] == "산책을 해봤어요 / 일기도 써봤어요"
    assert session.turns == 1
    assert session.slot_evidence["coping"]["source_turn"] == 1


def test_local_request_write_failure_leaves_no_partial_turn_and_can_retry(monkeypatch):
    monkeypatch.setattr(main, "_rate_limiter", ratelimit.RateLimiter())
    original = storage._write_private_json
    failed = False

    def fail_once(path, payload):
        nonlocal failed
        if not failed and any(turn.get("role") == "assistant" for turn in payload.get("turns", [])):
            failed = True
            raise OSError("synthetic atomic write failure")
        return original(path, payload)

    with TestClient(main.app, raise_server_exceptions=False) as client:
        consent = client.post("/api/consent", json={"session_id": "atomic-request", "accepted": True,
                              "consent_version": "maeum-2026-11-05"}).json()
        session = chat._sessions["atomic-request"]
        session.turns = 9
        session.closing_started = True
        session.slots = {"track": "정서", "chief_complaint": "불안해요"}
        monkeypatch.setattr(storage, "_write_private_json", fail_once)
        payload = {"session_id": "atomic-request", "session_token": consent["session_token"],
                   "message": "이대로 보내기", "request_id": "atomic-request-0001"}
        assert client.post("/api/chat", json=payload).status_code == 500
        saved = next(Path("data/conversations").glob("*/atomic-request.json"))
        assert not any(turn.get("text") == payload["message"]
                       for turn in __import__("json").loads(saved.read_text())["turns"])
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 200 and response.json()["processing_status"] == "delivered"
        turns = __import__("json").loads(saved.read_text())["turns"]
        assert sum(turn.get("text") == payload["message"] for turn in turns) == 1
