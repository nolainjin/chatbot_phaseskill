from pathlib import Path

from app import chat, knowledge
from app.config import Settings
from app.intake import load_schema

REPO_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_MATH_DIR = str(REPO_ROOT / "knowledge-math")

def _settings() -> Settings:
    return Settings(
        anthropic_api_key="",
        knowledge_dir=KNOWLEDGE_MATH_DIR,
        model="fake",
        trust_proxy_hops=0,
        daily_request_cap=500,
    )

def test_math_pack_uses_coaching_fallback_instead_of_intake():
    schema = load_schema(KNOWLEDGE_MATH_DIR)
    assert schema is None

    captured: dict[str, str] = {}

    def fake_ask(**kwargs):
        captured.update(kwargs)
        return "질문과 관련된 개념을 문서 근거로 함께 살펴볼게요."

    chat._sessions.pop("math-coaching", None)
    original_ask = chat.llm.ask
    chat.llm.ask = fake_ask
    try:
        result = chat.handle_message(
            "math-coaching", "미분에서 기울기가 왜 필요한지 모르겠어요.", _settings()
        )
    finally:
        chat.llm.ask = original_ask

    assert result["reply"] == "질문과 관련된 개념을 문서 근거로 함께 살펴볼게요."
    assert "intake" not in result
    assert "PNK 수학" in captured["system"]
    assert "접수" not in captured["system"]
    assert captured["doc_titles"]


def test_math_documents_load_excluding_reserved():
    docs = knowledge.load_documents(KNOWLEDGE_MATH_DIR)
    # PNK 방법론 7편 + 태그북 TB1~TB14 = 21편. "_" 예약 파일은 제외된다.
    assert len(docs) == 21
    titles = {doc.title for doc in docs}
    assert "PNK수학의 방향성" in titles
    assert not any(doc.path.name.startswith("_") for doc in docs)


def test_math_pack_prompt_and_ui_text_are_coaching_only():
    math_dir = Path(KNOWLEDGE_MATH_DIR)
    text = "\n".join(
        (math_dir / name).read_text(encoding="utf-8")
        for name in ("_persona.md", "_tone.md", "_safety_protocol.md")
    )

    assert "접수" not in text
    assert "면접" not in text
    assert "보호자" not in text
    assert "전문기관" not in text
    assert "위기" not in text
    assert "자해" not in text
    assert "자살" not in text


def test_math_fake_reply_contains_grounded_coaching_excerpt():
    chat._sessions.pop("math-fake-coaching", None)
    result = chat.handle_message(
        "math-fake-coaching", "미분에서 기울기의 의미를 설명해 주세요.", _settings()
    )

    assert result["reply"].startswith("[fake] 학습 코칭 근거:")
    assert "핵심:" in result["reply"]
    assert "intake" not in result
