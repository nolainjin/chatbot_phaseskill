from pathlib import Path

from app import chat, knowledge
from app.config import Settings
from app.intake import load_schema


REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = REPO_ROOT / "knowledge-self-directed"


def _settings() -> Settings:
    return Settings(
        anthropic_api_key="",
        knowledge_dir=str(PACK_DIR),
        model="fake",
        trust_proxy_hops=0,
        daily_request_cap=500,
    )


def test_self_directed_pack_is_schema_less_and_contains_learning_models():
    documents = knowledge.load_documents(PACK_DIR)
    titles = {document.title for document in documents}

    assert load_schema(PACK_DIR) is None
    assert "자기주도학습 순환모델" in titles
    assert "AI와 자기조절학습" in titles
    assert "학습전략과 피드백" in titles


def test_self_directed_pack_fake_chat_returns_grounded_learning_guidance():
    chat._sessions.pop("self-directed-pack-test", None)

    result = chat.handle_message(
        "self-directed-pack-test",
        "자기주도학습 순환모델에서 목표 계획 모니터링 성찰은 어떤 순서인가요?",
        _settings(),
    )

    assert result["reply"].startswith("[fake] 학습 코칭 근거: 자기주도학습 순환모델")
    assert "계획" in result["reply"] or "모니터링" in result["reply"]
    assert "intake" not in result


def test_self_directed_pack_routes_research_provenance_questions_to_source_map():
    chat._sessions.pop("self-directed-source-test", None)

    result = chat.handle_message(
        "self-directed-source-test",
        "자기주도학습 논문 출처 DOI 검증상태를 알려 주세요.",
        _settings(),
    )

    assert result["reply"].startswith("[fake] 학습 코칭 근거: 자기주도학습 논문 출처와 검증상태")
    assert "검증" in result["reply"]


def test_self_directed_pack_prompt_is_coaching_only():
    persona = (PACK_DIR / "_persona.md").read_text(encoding="utf-8")

    assert "자기주도학습" in persona
    assert "학생 대신 과제를 완성하지 않는다" in persona
    assert "접수" not in persona
