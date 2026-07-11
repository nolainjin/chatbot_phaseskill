"""CAP06("지식 데이터만 교체하면 다른 분야 챗봇으로 전환") 실증 테스트.

코드(app/chat.py, app/knowledge.py)는 그대로 두고 Settings.knowledge_dir 값만
knowledge -> knowledge-alt 로 바꿔 같은 질문을 handle_message에 두 번 흘려보낸다.
LLM은 MODEL=fake 스텁이라 검색된 문서 제목을 그대로 인용하므로, 인용된 제목이
디렉토리에 따라 갈리는지 보면 "로직/콘텐츠 분리"가 주장이 아니라 동작으로
증명된다.
"""

from pathlib import Path

from app import chat
from app.config import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = str(REPO_ROOT / "knowledge")
KNOWLEDGE_ALT_DIR = str(REPO_ROOT / "knowledge-alt")

# 두 지식셋 모두의 본문에 등장하는 공통 단어 -- 같은 질문을 두 도메인에 동시에
# 던져도 각 도메인에서 실제로 매치가 나오도록 고른 단어다(지식/상담: 3건 매치,
# knowledge-alt/커피: 1건 매치, 서로 겹치지 않음).
QUESTION = "방법 알려줘"


def _settings(knowledge_dir: str) -> Settings:
    return Settings(
        anthropic_api_key="",
        knowledge_dir=knowledge_dir,
        model="fake",
        trust_proxy_hops=0,
        daily_request_cap=500,
    )


def test_knowledge_dir_swap_changes_cited_docs_without_code_change():
    base_result = chat.handle_message("swap-e2e-base", QUESTION, _settings(KNOWLEDGE_DIR))
    alt_result = chat.handle_message("swap-e2e-alt", QUESTION, _settings(KNOWLEDGE_ALT_DIR))

    # 기본 지식셋(상담) 구동 -> 상담 도메인 문서가 인용되고, alt(커피) 문서는 없어야 한다.
    assert "상담 목표 설정 방법" in base_result["reply"]
    assert "원두 보관법" not in base_result["reply"]

    # KNOWLEDGE_DIR만 knowledge-alt로 바꿔 재구동(코드 무수정) -> 같은 질문인데
    # 이번엔 커피 도메인 문서가 인용되고, 상담 도메인 문서는 사라져야 한다.
    assert "원두 보관법" in alt_result["reply"]
    assert "상담 목표 설정 방법" not in alt_result["reply"]
