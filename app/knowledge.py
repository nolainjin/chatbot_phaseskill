"""지식베이스 로더 + 키워드 검색.

지식은 YAML 프론트매터가 붙은 마크다운 파일이다. 어떤 디렉토리를 읽을지는
호출부(app.config.Settings.knowledge_dir)가 정하며, 이 모듈 자체는 디렉토리
경로를 파라미터로만 받는다 — 그래야 지식 데이터 교체(Phase 6 스왑 검증)가
로직 수정 없이 가능하다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?\n)---\s*\n?(.*)\Z", re.DOTALL)


@dataclass
class Document:
    path: Path
    title: str
    tags: list[str] = field(default_factory=list)
    body: str = ""
    meta: dict = field(default_factory=dict)


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """'---'로 감싼 YAML 프론트매터와 본문을 분리한다. 프론트매터가 없으면
    빈 dict + 원문 전체를 본문으로 취급한다."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text.strip()
    raw_meta, body = match.groups()
    meta = yaml.safe_load(raw_meta) or {}
    return meta, body.strip()


def load_documents(knowledge_dir: str | Path) -> list[Document]:
    directory = Path(knowledge_dir)
    documents: list[Document] = []
    for md_file in sorted(directory.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        meta, body = _split_frontmatter(text)
        documents.append(
            Document(
                path=md_file,
                title=str(meta.get("title", md_file.stem)),
                tags=list(meta.get("tags") or []),
                body=body,
                meta=meta,
            )
        )
    return documents


def search(query: str, documents: list[Document], top_n: int = 3) -> list[Document]:
    """질문 단어가 제목/태그/본문에 등장하는 빈도로 점수를 매기는 단순 키워드
    매칭. 벡터DB 없이 소규모 위키 전제를 충족하는 최소 구현."""
    words = [w.lower() for w in re.findall(r"\w+", query)]
    if not words:
        return []

    def score(doc: Document) -> int:
        haystack = f"{doc.title} {' '.join(doc.tags)} {doc.body}".lower()
        return sum(haystack.count(word) for word in words)

    scored = [(score(doc), doc) for doc in documents]
    scored = [item for item in scored if item[0] > 0]
    scored.sort(key=lambda item: item[0], reverse=True)
    return [doc for _, doc in scored[:top_n]]
