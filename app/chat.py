"""세션별 대화 상태 관리 + 10턴 캡 + 지식 검색 + LLM 호출.

세션 상태는 메모리 dict다. 재시작 시 소실은 프로토타입 수용 범위 —
대화 내역 영속은 Phase 3 JSON 저장이 담당한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app import knowledge, llm
from app.config import Settings

MAX_TURNS = 10
LIMIT_MESSAGE = "이 세션은 대화 10턴 한도에 도달했습니다. 새 세션으로 다시 시작해 주세요."

_SYSTEM_PREAMBLE = (
    "너는 아래 지식 문서 내용만 근거로 답하는 도우미다. "
    "문서에 없는 내용은 모른다고 답해라.\n\n"
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
    # 캐시 없이도 충분하고, 파일 수가 늘어 느려지면 그때 캐시를 붙인다.
    docs = knowledge.search(message, knowledge.load_documents(settings.knowledge_dir))
    doc_context = "\n\n".join(f"# {doc.title}\n{doc.body}" for doc in docs)
    system = _SYSTEM_PREAMBLE + doc_context

    reply = llm.ask(
        system=system,
        history=session.history,
        user=message,
        doc_titles=[doc.title for doc in docs],
        settings=settings,
    )

    session.history.append({"role": "user", "content": message})
    session.history.append({"role": "assistant", "content": reply})
    session.turns += 1

    return {"reply": reply, "turn": session.turns, "limit_reached": False}
