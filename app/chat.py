"""세션별 대화 상태 + 10턴 캡 + 지식 검색 + LLM 호출을 잇는 대화 루프.

세션 상태는 메모리 dict에 둔다. 재시작 시 소실은 프로토타입 수용 범위 —
대화 내역 영속은 Phase 3의 JSON 저장이 맡는다.
"""

from dataclasses import dataclass, field

from app import knowledge, llm, storage
from app.config import Settings

MAX_TURNS = 10
LIMIT_MESSAGE = f"이 세션은 대화 {MAX_TURNS}턴 한도에 도달했습니다. 새 세션으로 다시 시작해 주세요."

# 지식 문서 내용만 근거로 답하라는 지시일 뿐, 도메인 문구는 없다 — knowledge_dir을
# 바꿔 다른 분야로 스왑해도 이 프리앰블은 그대로 쓴다 (Phase 6 스왑 검증 대상).
_SYSTEM_PREAMBLE = (
    "아래 지식 문서 내용을 근거로 답하라. 문서에 없는 내용은 모른다고 답하라.\n\n"
)


@dataclass
class ChatSession:
    session_id: str
    turns: int = 0
    history: list[dict[str, str]] = field(default_factory=list)


_sessions: dict[str, ChatSession] = {}


def _get_session(session_id: str) -> ChatSession:
    session = _sessions.get(session_id)
    if session is None:
        session = ChatSession(session_id=session_id)
        _sessions[session_id] = session
    return session


def handle_message(session_id: str, message: str, settings: Settings | None = None) -> dict:
    settings = settings or Settings.from_env()
    session = _get_session(session_id)

    if session.turns >= MAX_TURNS:
        return {"reply": LIMIT_MESSAGE, "turn": session.turns, "limit_reached": True}

    # ponytail: 매 요청마다 지식 디렉토리를 다시 읽는다. 소규모 위키 전제라
    # 캐시 없이도 충분하다 — 문서 수가 늘어 느려지면 그때 캐시를 붙인다.
    docs = knowledge.search(message, knowledge.load_documents(settings.knowledge_dir))
    system = _SYSTEM_PREAMBLE + "\n\n".join(f"# {doc.title}\n{doc.body}" for doc in docs)

    reply = llm.ask(
        system=system,
        history=session.history,
        user=message,
        doc_titles=[doc.title for doc in docs],
        settings=settings,
    )

    storage.append_turn(session_id, "user", message)
    storage.append_turn(session_id, "assistant", reply)

    session.history.append({"role": "user", "content": message})
    session.history.append({"role": "assistant", "content": reply})
    session.turns += 1

    return {"reply": reply, "turn": session.turns, "limit_reached": False}
