from pathlib import Path

from app.knowledge import load_documents, search

REPO_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"
KNOWLEDGE_ALT_DIR = REPO_ROOT / "knowledge-alt"


def test_load_documents_parses_frontmatter():
    docs = load_documents(KNOWLEDGE_DIR)
    assert len(docs) >= 5

    by_stem = {doc.path.stem: doc for doc in docs}
    reset_doc = by_stem["password-reset"]
    assert reset_doc.title == "비밀번호 재설정 방법"
    assert "비밀번호" in reset_doc.tags
    assert "비밀번호" in reset_doc.body


def test_load_documents_directory_swap():
    """KNOWLEDGE_DIR만 바꿔도 로직 수정 없이 완전히 다른 도메인을 읽는다
    (CAP06 지식 스왑 전제)."""
    base_docs = load_documents(KNOWLEDGE_DIR)
    alt_docs = load_documents(KNOWLEDGE_ALT_DIR)

    assert len(alt_docs) >= 5
    base_titles = {doc.title for doc in base_docs}
    alt_titles = {doc.title for doc in alt_docs}
    assert base_titles.isdisjoint(alt_titles)


def test_search_ranks_matching_document_first():
    docs = load_documents(KNOWLEDGE_DIR)
    results = search("비밀번호를 잊어버렸어요", docs, top_n=1)
    assert len(results) == 1
    assert results[0].path.stem == "password-reset"


def test_search_respects_top_n():
    docs = load_documents(KNOWLEDGE_ALT_DIR)
    results = search("원두 로스팅 그라인더 보관", docs, top_n=2)
    assert len(results) <= 2


def test_search_no_match_returns_empty():
    docs = load_documents(KNOWLEDGE_DIR)
    assert search("존재하지않는아무말대잔치xyz", docs) == []
