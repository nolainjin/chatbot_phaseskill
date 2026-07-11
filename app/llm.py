"""Claude API 연동.

MODEL 설정값이 "fake"이면 Anthropic 클라이언트를 아예 만들지 않고 검색된
문서 제목을 인용하는 오프라인 스텁 응답을 돌려준다 — 테스트·스모크가 API
키 없이도 돌아가게 하기 위한 스위치다 (app/config.py Settings.model).
"""

from __future__ import annotations

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
        if doc_titles:
            return f"[fake] 참고 문서: {', '.join(doc_titles)}"
        return "[fake] 관련 문서를 찾지 못했습니다."

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    messages = history + [{"role": "user", "content": user}]
    response = client.messages.create(
        model=settings.model,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=messages,
    )
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""
