"""지식베이스 로더 + 키워드 검색.

지식은 마크다운 파일 + YAML 프론트매터(SecondBrain wiki 스키마 호환:
type/aliases/author/date/tags[/cluster])다. title 키는 없을 수 있으므로
본문 H1 → 파일명 stem 순으로 폴백한다. 스키마에 없는 키는 meta에 보존한다.

RAG/벡터DB는 쓰지 않는다 — 소규모 위키 전제라 키워드 매칭으로 충분하고,
부족해지면 그때 교체한다.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclass
class Document:
    title: str
    tags: list
    body: str
    path: Path
    meta: dict = field(default_factory=dict)


def _split_frontmatter(text: str) -> tuple:
    """'---' 구분 프론트매터를 분리한다. 없으면 (빈 dict, 원문 전체)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    _, fm_raw, body = parts
    meta = yaml.safe_load(fm_raw) or {}
    return meta, body.lstrip("\n")


def _resolve_title(meta: dict, body: str, path: Path) -> str:
    if meta.get("title"):
        return str(meta["title"])
    match = _H1_RE.search(body)
    if match:
        return match.group(1).strip()
    return path.stem


def load_documents(knowledge_dir) -> list:
    """knowledge_dir 안의 *.md를 전부 읽어 Document 목록으로 반환한다.

    "_"로 시작하는 파일(예: _persona.md)은 페르소나·메타 용도로 예약되어
    검색 대상에서 제외한다.
    """
    directory = Path(knowledge_dir)
    documents = []
    for md_file in sorted(directory.glob("*.md")):
        if md_file.name.startswith("_"):
            continue
        text = md_file.read_text(encoding="utf-8")
        meta, body = _split_frontmatter(text)
        title = _resolve_title(meta, body, md_file)
        tags = meta.get("tags") or []
        extra_meta = {k: v for k, v in meta.items() if k not in ("title", "tags")}
        documents.append(
            Document(title=title, tags=tags, body=body, path=md_file, meta=extra_meta)
        )
    return documents


def search(query: str, documents: list, top_n: int = 3) -> list:
    """질문어가 제목/태그/본문에 등장하는 빈도로 상위 top_n 문서를 반환한다."""
    words = [w.lower() for w in _WORD_RE.findall(query)]
    if not words:
        return []

    scored = []
    for doc in documents:
        title = doc.title.lower()
        haystack = " ".join([title, " ".join(doc.tags), doc.body.lower()])
        title_score = 100 * sum(title.count(word) for word in words)
        score = title_score + sum(haystack.count(word) for word in words)
        if score > 0:
            scored.append((score, doc))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [doc for _, doc in scored[:top_n]]
