"""Claude API 호출.

MODEL 설정이 "fake"면 Anthropic을 호출하지 않고 검색된 문서 제목을 인용하는
오프라인 스텁 응답을 돌려준다 — API 키 없이 테스트/스모크를 돌리기 위한
스위치다.
"""

import anthropic

from app.config import Settings

MAX_TOKENS = 1024


def ask(
    system: str,
    history: list[dict[str, str]],
    user: str,
    doc_titles: list[str],
    settings: Settings,
) -> str:
    if settings.model == "fake":
        if not doc_titles:
            return "[fake] 관련 문서를 찾지 못했습니다."
        return f"[fake] 참고 문서: {', '.join(doc_titles)}"

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.model,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=history + [{"role": "user", "content": user}],
    )
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""
