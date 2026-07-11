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

이 챗봇의 핵심 제약은 "지식 데이터만 교체하면 다른 분야 챗봇으로 전환"이다 (origin §3, CAP05/CAP06). 그래서 첫 phase는 챗봇 로직이 아니라 지식 콘텐츠를 읽는 레이어를 만든다. 지식은 마크다운 파일 + YAML 프론트매터(title, tags 등 메타데이터)이고, 어떤 디렉토리를 읽을지는 KNOWLEDGE_DIR 환경변수 하나로 정해진다. 스왑 실증(Phase 6)을 위해 서로 다른 도메인 샘플 지식셋 2벌을 처음부터 만들어 둔다.

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
- `app/config.py`는 환경변수를 한곳에서 읽는다: ANTHROPIC_API_KEY, KNOWLEDGE_DIR(기본 `knowledge`), MODEL(기본 `claude-haiku-4-5`), TRUST_PROXY_HOPS(기본 0), DAILY_REQUEST_CAP(기본 500).
- 샘플 지식셋: `knowledge/`(기본 도메인)와 `knowledge-alt/`(전혀 다른 도메인) 각 5개 이상 문서. 도메인이 확연히 달라야 Phase 6 스왑 검증이 의미가 있다.
- 파이썬 실행 환경은 리포 루트 `.venv`로 고정하고 전체 의존성(fastapi, uvicorn, anthropic, pyyaml, pytest, httpx)을 requirements.txt에 미리 적는다.

## 체크리스트

- [x] python3 -m venv .venv 생성 후 .venv/bin/pip install -r requirements.txt 성공 — requirements.txt에 전체 의존성 선기재(fastapi, uvicorn, anthropic, pyyaml, pytest, httpx)
- [x] app/knowledge.py: KNOWLEDGE_DIR 환경변수가 가리키는 디렉토리에서 *.md 로딩, YAML 프론트매터 파싱 (PyYAML)
- [x] 키워드 기반 검색 함수: 질문어를 제목/태그/본문과 매칭해 상위 N개 문서 반환
- [x] 샘플 지식셋 2벌: knowledge/ (기본 도메인) + knowledge-alt/ (다른 도메인, 스왑 검증용) 각 5개 이상 문서
- [x] .env.example에 ANTHROPIC_API_KEY/KNOWLEDGE_DIR/MODEL/TRUST_PROXY_HOPS/DAILY_REQUEST_CAP 명시, .gitignore에 .env·data/·.venv/ 포함
- [x] tests/test_knowledge.py: 프론트매터 파싱·디렉토리 교체·검색 테스트 통과

## 영향 범위

신규 리포 첫 phase라 기존 코드 영향 없음. 이후 모든 phase가 이 로더와 .venv에 의존한다. 롤백 = 디렉토리 삭제.

## 검증

```bash
.venv/bin/python -m pytest tests/test_knowledge.py -q
```

## 실행 결과

### 1회차 (2026-07-11 13:05 KST) — completed
**상태**: completed
**소요 시간**: 약 20분
**진행 모델**: Claude `sonnet`

#### 요약
지식 로더(app/knowledge.py) + 설정 모듈(app/config.py) + 서로 다른 도메인 샘플 지식셋 2벌(사내 IT 헬프데스크 / 홈카페 원두 가이드)을 새로 만들었다. .venv 생성 후 requirements.txt 설치가 성공했고, pytest 5건이 모두 통과했다.

#### 변경 파일
- `app/__init__.py` (new, +0 lines)
- `app/config.py` (new, +29 lines)
- `app/knowledge.py` (new, +72 lines)
- `requirements.txt` (new, +6 lines)
- `.env.example` (new, +5 lines)
- `.gitignore` (new, +6 lines)
- `README.md` (new, +35 lines)
- `tests/test_knowledge.py` (new, +48 lines)
- `knowledge/vpn-setup.md` (new, +16 lines)
- `knowledge/password-reset.md` (new, +16 lines)
- `knowledge/printer-setup.md` (new, +15 lines)
- `knowledge/remote-work.md` (new, +15 lines)
- `knowledge/laptop-issue.md` (new, +15 lines)
- `knowledge-alt/roasting-levels.md` (new, +14 lines)
- `knowledge-alt/brew-methods.md` (new, +14 lines)
- `knowledge-alt/grinder-guide.md` (new, +15 lines)
- `knowledge-alt/milk-steaming.md` (new, +14 lines)
- `knowledge-alt/bean-storage.md` (new, +15 lines)

> 라인 수는 각 신규(untracked) 파일에 `wc -l` 실측값(+N/-0 형식)을 사용했다.

#### 검증 결과
- [x] python3 -m venv .venv && .venv/bin/pip install -r requirements.txt: `.venv/bin/pip install -r requirements.txt` -> pass (설치 완료, 캐시 역직렬화 경고만 있고 에러 없음)
- [x] tests/test_knowledge.py 5건 (프론트매터 파싱·디렉토리 스왑·검색 top_n·검색 0건): `.venv/bin/python -m pytest tests/test_knowledge.py -q` -> pass (`5 passed in 0.17s`)
- [x] (추가 스모크) app.config.Settings 기본값 로딩: `.venv/bin/python -c "from app.config import Settings; ..."` -> pass (`CONFIG_SMOKE_OK`)
- [x] (추가 스모크) knowledge-alt/ 5개 문서 로딩: `.venv/bin/python -c "from app.knowledge import load_documents; ..."` -> pass (`ALT_LOAD_OK`, 5개 문서 확인)

#### 추가 발견사항
없음.

#### 질문 / 결정 사항
없음.

#### 사용 도구
Read 6회, Write 14회, Edit 2회, Bash 8회.
