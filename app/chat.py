"""세션별 대화 상태 + 10턴 캡 + 지식 검색 + LLM 호출을 잇는 대화 루프.

세션 상태는 메모리 dict에 둔다. 재시작 시 소실은 프로토타입 수용 범위 —
대화 내역 영속은 Phase 3의 JSON 저장이 맡는다.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from app import intake, knowledge, llm, storage
from app.config import Settings

MAX_TURNS = 10
LIMIT_MESSAGE = f"이 세션은 대화 {MAX_TURNS}턴 한도에 도달했습니다. 새 세션으로 다시 시작해 주세요."

_PERSONA_FILENAME = "_persona.md"

# 지식 문서 내용만 근거로 답하라는 지시일 뿐, 도메인 문구는 없다 — knowledge_dir에
# _persona.md가 없는 지식셋(스왑 대상)에서 쓰는 폴백이다 (Phase 6 스왑 검증 대상).
_SYSTEM_PREAMBLE = (
    "아래 지식 문서 내용을 근거로 답하라. 문서에 없는 내용은 모른다고 답하라.\n\n"
)

# 면담 종료(MAX_TURNS 도달) 시 히스토리를 넘겨 접수 요약을 생성하는 지시.
_SUMMARY_INSTRUCTION = (
    "지금까지의 면담 대화를 접수 요약으로 정리하라. 방문 이유, 주 호소, 위기 신호, "
    "다음 단계 네 항목을 포함하라."
)

# 실모드 단일 호출 통합(D02) — 응답 생성 호출 안에 슬롯 추출 지시를 함께
# 넣는다. 모델 출력은 intake.extract_real이 신뢰 경계 검증 후 분리한다.
_EXTRACTION_INSTRUCTION = (
    "응답을 마친 뒤 마지막 줄에 ```slots 로 시작하는 fenced 코드블록을 추가하고, "
    "그 안에 이번 발화에서 새로 확인된 슬롯만 담은 JSON 객체를 출력하라. "
    '형식: ```slots\n{"슬롯id": "값"}\n```. 새로 확인된 슬롯이 없으면 빈 객체 '
    "{}를 출력하라."
)


@dataclass
class ChatSession:
    session_id: str
    turns: int = 0
    history: list[dict[str, str]] = field(default_factory=list)
    slots: dict[str, str] = field(default_factory=dict)


_sessions: dict[str, ChatSession] = {}


def _get_session(session_id: str) -> ChatSession:
    session = _sessions.get(session_id)
    if session is None:
        session = ChatSession(session_id=session_id)
        _sessions[session_id] = session
    return session


def _load_persona(knowledge_dir: str) -> str:
    """_persona.md가 있으면 그 내용을, 없으면 기존 프리앰블을 반환한다(스왑 폴백)."""
    persona_path = Path(knowledge_dir) / _PERSONA_FILENAME
    if persona_path.is_file():
        return persona_path.read_text(encoding="utf-8")
    return _SYSTEM_PREAMBLE


def _build_slot_section(
    schema: intake.Schema,
    filled: dict[str, str],
    unfilled: list[intake.Slot],
    turns_before: int,
) -> str:
    """모드 공통 슬롯 섹션 — 채워진/미충족(우선순위순)/레드플래그 규칙/턴 예산."""
    filled_text = ", ".join(
        f"{slot.label}={filled[slot.id]}" for slot in schema.slots if slot.id in filled
    )
    unfilled_text = ", ".join(slot.label for slot in unfilled)
    lines = [
        "[접수 슬롯 상태]",
        f"채워진 슬롯: {filled_text or '없음'}",
        f"미충족 슬롯(우선순위순): {unfilled_text or '없음'}",
        "레드플래그 규칙: 미충족 목록 최상단 슬롯이 레드플래그면 그 슬롯을 최우선으로 질문하라.",
        f"턴 예산: 잔여 {MAX_TURNS - turns_before}턴 — 우선순위 높은 슬롯부터 소비하라.",
    ]
    if turns_before == 0:
        lines.append(f"1턴이므로 다음 개방형 질문으로 시작하라: {schema.opening_question}")
    return "\n".join(lines)


def _fake_progress_suffix(
    schema: intake.Schema,
    new_fills: dict[str, str],
    unfilled: list[intake.Slot],
) -> str:
    """fake 모드 reply에 붙일 진행 접미사. 새 채움/다음 질문이 없으면 빈 문자열."""
    label_by_id = {slot.id: slot.label for slot in schema.slots}
    parts = []
    if new_fills:
        fills_text = ", ".join(f"{label_by_id[sid]}={value}" for sid, value in new_fills.items())
        parts.append(f"채움: {fills_text}")
    if unfilled:
        parts.append(f"다음 질문: {unfilled[0].label}")
    return f" | {' | '.join(parts)}" if parts else ""


def _intake_state(
    schema: intake.Schema,
    filled: dict[str, str],
    unfilled: list[intake.Slot],
) -> dict:
    """GUI 슬롯 패널용 상태. 스키마 활성 응답에만 additive로 실린다 —
    기존 {reply, turn, limit_reached} 계약은 그대로, 스키마 없는 지식셋
    (knowledge-alt 스왑)은 이 키 자체가 없다."""
    return {
        "filled": [
            {"id": slot.id, "label": slot.label, "value": filled[slot.id]}
            for slot in schema.slots
            if slot.id in filled
        ],
        "unfilled": [
            {"id": slot.id, "label": slot.label, "red_flag": slot.red_flag}
            for slot in unfilled
        ],
    }


def handle_message(session_id: str, message: str, settings: Settings | None = None) -> dict:
    settings = settings or Settings.from_env()
    session = _get_session(session_id)

    if session.turns >= MAX_TURNS:
        return {"reply": LIMIT_MESSAGE, "turn": session.turns, "limit_reached": True}

    # ponytail: 매 요청마다 지식 디렉토리를 다시 읽는다. 소규모 위키 전제라
    # 캐시 없이도 충분하다 — 문서 수가 늘어 느려지면 그때 캐시를 붙인다.
    docs = knowledge.search(message, knowledge.load_documents(settings.knowledge_dir))
    persona = _load_persona(settings.knowledge_dir)
    progress = f"[진행: {session.turns + 1}/{MAX_TURNS}턴]"
    doc_section = "\n\n".join(f"# {doc.title}\n{doc.body}" for doc in docs)

    schema = intake.load_schema(settings.knowledge_dir)
    new_fills: dict[str, str] = {}
    unfilled: list[intake.Slot] = []
    red_flag_ids: set[str] = set()
    if schema is None:
        # 폴백 — 스키마 없는 지식셋(knowledge-alt)은 기존 경로 그대로.
        system = f"{persona}\n\n{progress}\n\n{doc_section}"
    else:
        if settings.model == "fake":
            new_fills = intake.extract_fake(message, schema, session.slots)
            session.slots.update(new_fills)
        red_flag_ids = intake.detect_red_flags(message, schema, session.slots)
        unfilled = schema.unfilled_by_priority(session.slots, red_flag_ids)
        slot_section = _build_slot_section(schema, session.slots, unfilled, session.turns)
        sections = [persona, progress, slot_section]
        if settings.model != "fake":
            sections.append(_EXTRACTION_INSTRUCTION)
        sections.append(doc_section)
        system = "\n\n".join(sections)

    reply = llm.ask(
        system=system,
        history=session.history,
        user=message,
        doc_titles=[doc.title for doc in docs],
        settings=settings,
    )

    if schema is not None and settings.model == "fake":
        reply += _fake_progress_suffix(schema, new_fills, unfilled)
    elif schema is not None:
        # 실모드 단일 호출 통합(D02) — 응답 텍스트에 섞여온 슬롯 JSON을 신뢰
        # 경계 검증(intake.extract_real) 후 분리한다. reply는 이제 슬롯 JSON이
        # 제거된 clean 버전이라 history·storage에도 그대로 안전하게 쓴다.
        reply, real_fills = intake.extract_real(reply, schema, session.slots)
        session.slots.update(real_fills)

    storage.append_turn(session_id, "user", message)
    storage.append_turn(session_id, "assistant", reply)

    session.history.append({"role": "user", "content": message})
    session.history.append({"role": "assistant", "content": reply})
    session.turns += 1

    if session.turns >= MAX_TURNS:
        if schema is not None:
            # 채워진 슬롯이 이미 세션 상태에 있으므로 LLM을 부를 이유가 없다 —
            # 결정론 생성이라 fake 모드에서도 동일하게 돈다(CAP08).
            summary_json = intake.build_summary_json(schema, session.slots)
            storage.append_turn(
                session_id, "intake_summary", json.dumps(summary_json, ensure_ascii=False)
            )
        else:
            try:
                summary = llm.ask(
                    system=_SUMMARY_INSTRUCTION,
                    history=session.history,
                    user=_SUMMARY_INSTRUCTION,
                    doc_titles=[],
                    settings=settings,
                )
                storage.append_turn(session_id, "intake_summary", summary)
            except Exception:
                pass  # 요약 실패가 본 대화 저장까지 유실시키지 않도록 격리

    result = {"reply": reply, "turn": session.turns, "limit_reached": False}
    if schema is not None:
        # 실모드는 extract_real이 unfilled 계산 이후에 슬롯을 채우므로,
        # 패널 상태는 최종 session.slots 기준으로 다시 계산한다.
        result["intake"] = _intake_state(
            schema, session.slots, schema.unfilled_by_priority(session.slots, red_flag_ids)
        )
    return result
