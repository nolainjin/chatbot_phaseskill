---
phase: 1
title: 지식베이스 로더 + 프로젝트 뼈대
status: completed
depends_on: []
scope:
  - app/__init__.py
  - app/config.py
  - app/knowledge.py
  - knowledge/
  - knowledge-alt/
  - tests/test_knowledge.py
  - requirements.txt
  - .env.example
  - .gitignore
  - README.md
intervention_likely: false
intervention_reason: ""
executor: sonnet
load_bearing: ""
e2e_refs: []
e2e_triggers: []
phase_context:
  baseline: "missing"
  adoption: "bootstrap"
  coverage: "standard"
  enforcement_during_run: "warn"
  materialize_at: "finalization"
---

# Phase 1: 지식베이스 로더 + 프로젝트 뼈대

> **범위**: Backend
> **난이도**: S
> **의존성**: 없음
> **영향 파일**: `app/knowledge.py` (신규), `requirements.txt` (신규)

## 배경

이 챗봇의 핵심 제약은 "지식 데이터만 교체하면 다른 분야 챗봇으로 전환"이다 (origin §3, CAP05/CAP06). 그래서 첫 phase는 챗봇 로직이 아니라 지식 콘텐츠를 읽는 레이어를 만든다. 지식은 마크다운 파일 + YAML 프론트매터이고, 어떤 디렉토리를 읽을지는 KNOWLEDGE_DIR 환경변수 하나로 정해진다. 스왑 실증(Phase 6)을 위해 서로 다른 도메인 샘플 지식셋 2벌을 처음부터 만들어 둔다.

사용자 확정(2026-07-11, intake open questions): 첫 챗봇 도메인은 **상담 초기 면담**이고, 프론트매터 스키마는 SecondBrain wiki(`/Volumes/부부공용/SecondBrain/wiki/`)를 레퍼런스로 한다 — 키: `type / aliases / author / date / tags [/ cluster]`, 제목은 프론트매터가 아닌 본문 H1. 따라서 로더는 title 키에 의존하면 안 된다(부재 시 파일명 stem 또는 H1 폴백, 미지정 키는 meta로 보존).

프로젝트 전체 의존성도 이 phase에서 선기재한다. 뒤 phase들이 requirements.txt를 다시 건드리지 않게 하기 위함이다 (spec review O2).

## 심볼 인벤토리

- `app.knowledge.load_documents`
  - [NEW]
- `app.knowledge.search`
  - [NEW]
- `app.config.Settings`
  - [NEW]

## 설계

의사코드 수준의 흐름:

```
load_documents(knowledge_dir):
    for md_file in knowledge_dir/*.md:
        frontmatter, body = split_frontmatter(md_file)   # '---' 구분, PyYAML 파싱
        yield Document(title, tags, body, path)

search(query, documents, top_n=3):
    점수 = 질문 단어가 제목/태그/본문에 등장하는 빈도 (단순 키워드 매칭)
    return 상위 top_n 문서
```

- RAG/벡터DB는 넣지 않는다. 소규모 위키 전제(intake assumption)라 키워드 매칭이면 충분하고, 부족해지면 그때 교체한다.
- 프론트매터는 SecondBrain 스키마 호환: title 부재 시 파일명 stem(H1 있으면 H1 우선) 폴백, tags 부재 허용, 미지정 키(type/aliases/author/date/cluster 등)는 meta dict에 보존.
- `app/config.py`는 환경변수를 한곳에서 읽는다: ANTHROPIC_API_KEY, KNOWLEDGE_DIR(기본 `knowledge`), MODEL(기본 `claude-haiku-4-5`), TRUST_PROXY_HOPS(기본 0), DAILY_REQUEST_CAP(기본 500).
- 샘플 지식셋: `knowledge/`(**상담 초기 면담** — 첫 챗봇 도메인, 사용자 확정)와 `knowledge-alt/`(전혀 다른 도메인) 각 5개 이상 문서, 둘 다 SecondBrain 프론트매터 스키마로 작성. 도메인이 확연히 달라야 Phase 6 스왑 검증이 의미가 있다.
- 파이썬 실행 환경은 리포 루트 `.venv`로 고정하고 전체 의존성(fastapi, uvicorn, anthropic, pyyaml, pytest, httpx)을 requirements.txt에 미리 적는다.

## 체크리스트

- [x] python3 -m venv .venv 생성 후 .venv/bin/pip install -r requirements.txt 성공 — requirements.txt에 전체 의존성 선기재(fastapi, uvicorn, anthropic, pyyaml, pytest, httpx)
- [x] app/knowledge.py: KNOWLEDGE_DIR 환경변수가 가리키는 디렉토리에서 *.md 로딩, YAML 프론트매터 파싱 (PyYAML) — SecondBrain 스키마 호환(title 부재 시 H1→파일명 stem 폴백, 미지정 키 meta 보존)
- [x] 키워드 기반 검색 함수: 질문어를 제목/태그/본문과 매칭해 상위 N개 문서 반환
- [x] 샘플 지식셋 2벌: knowledge/ (상담 초기 면담 도메인 — 사용자 확정 2026-07-11) + knowledge-alt/ (다른 도메인, 스왑 검증용) 각 5개 이상 문서, SecondBrain 프론트매터 스키마(type/aliases/author/date/tags) 준수
- [x] .env.example에 ANTHROPIC_API_KEY/KNOWLEDGE_DIR/MODEL/TRUST_PROXY_HOPS/DAILY_REQUEST_CAP 명시, .gitignore에 .env·data/·.venv/ 포함
- [x] tests/test_knowledge.py: 프론트매터 파싱(title 부재 폴백 포함)·디렉토리 교체·검색 테스트 통과

## 영향 범위

신규 리포 첫 phase라 기존 코드 영향 없음. 이후 모든 phase가 이 로더와 .venv에 의존한다. 롤백 = 디렉토리 삭제.

## 검증

```bash
.venv/bin/python -m pytest tests/test_knowledge.py -q
```

> 참고: 1회차 실행 결과(2026-07-11, 커밋 829fa33)는 사용자 요청으로 폐기 — intake open questions 답변(상담 도메인·SecondBrain 스키마) 반영 후 재실행 예정.

## 실행 결과

### 2회차 (2026-07-11 00:00 KST) — completed
**상태**: completed
**소요 시간**: 약 15분
**진행 모델**: Claude sonnet

#### 요약
지식베이스 로더(`app/knowledge.py`)와 설정 모듈(`app/config.py`)을 새로 만들고, SecondBrain 프론트매터 스키마(title 없이 H1/파일명 stem 폴백, 미지정 키 meta 보존)를 따르는 상담 초기 면담 샘플 지식셋(`knowledge/`, 6개 문서)과 커피 브루잉 샘플 지식셋(`knowledge-alt/`, 6개 문서)을 작성했다. `.venv` + `requirements.txt`, `.env.example`, `.gitignore`, `README.md`까지 프로젝트 뼈대를 갖췄고 pytest 5건 모두 통과했다.

#### 변경 파일
- `app/__init__.py` (new, +0/-0)
- `app/config.py` (new, +23/-0)
- `app/knowledge.py` (new, +81/-0)
- `requirements.txt` (new, +6/-0)
- `.env.example` (new, +14/-0)
- `.gitignore` (new, +6/-0)
- `README.md` (new, +49/-0)
- `tests/test_knowledge.py` (new, +90/-0)
- `knowledge/초기-면담-목적과-구조.md` (new, +24/-0)
- `knowledge/라포-형성-기법.md` (new, +23/-0)
- `knowledge/비밀보장-원칙과-예외.md` (new, +22/-0)
- `knowledge/위기-상황-스크리닝.md` (new, +25/-0)
- `knowledge/접수-면접-질문지-구성.md` (new, +23/-0)
- `knowledge/상담-목표-설정.md` (new, +21/-0)
- `knowledge-alt/원두-로스팅-단계.md` (new, +22/-0)
- `knowledge-alt/드립-커피-추출-원리.md` (new, +22/-0)
- `knowledge-alt/원두-보관법.md` (new, +20/-0)
- `knowledge-alt/그라인더-선택-가이드.md` (new, +21/-0)
- `knowledge-alt/물-온도와-맛의-관계.md` (new, +20/-0)
- `knowledge-alt/프렌치프레스-사용법.md` (new, +23/-0)

#### 검증 결과
- [x] python3 -m venv .venv && .venv/bin/pip install -r requirements.txt: 성공 (fastapi/uvicorn/anthropic/pyyaml/pytest/httpx 전부 설치)
- [x] `.venv/bin/python -m pytest tests/test_knowledge.py -q`: `5 passed in 0.02s`

#### 추가 발견사항
없음. (1회차에서 보고된 starlette+httpx TestClient deprecation 경고는 이번 phase 범위에서 재현되지 않음 — FastAPI TestClient는 Phase 2에서 처음 쓰이므로 그때 확인 필요.)

#### 질문 / 결정 사항
없음.

#### Commit
- `664167b` feat(knowledge): Phase 1 — 지식베이스 로더 + 프로젝트 뼈대 (review pass, simplify 변경 0, 검증 재실행 pass)
