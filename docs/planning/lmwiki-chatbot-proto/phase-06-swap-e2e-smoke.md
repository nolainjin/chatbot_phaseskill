---
phase: 6
title: 지식 스왑 e2e + 로컬 통합 스모크
status: completed
depends_on: [3, 4, 5]
scope:
  - tests/test_swap_e2e.py
  - scripts/smoke_local.sh
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

# Phase 6: 지식 스왑 e2e + 로컬 통합 스모크

> **범위**: Backend
> **난이도**: S
> **의존성**: Phase 3, 4, 5
> **영향 파일**: `tests/test_swap_e2e.py` (신규), `scripts/smoke_local.sh` (신규)

## 배경

"지식 데이터만 교체하면 다른 분야 챗봇으로 전환"(CAP06)은 이 프로젝트에서 가장 fake-satisfy되기 쉬운 능력이다 — 코드상 분리됐다고 주장만 하고 실제 스왑 증명을 건너뛰기 쉽다(capabilities.md 적대적 플래그 1순위). 이 phase가 그 증명이다. 아울러 채팅→저장→배치→rate limit 전 구간을 한 번에 도는 로컬 스모크를 만들어 통합 회귀선을 깐다.

프로젝트에 E2E 카탈로그(docs/e2e/)가 없어 e2e_refs는 빈 값이며, 이 로컬 테스트·스모크가 그 역할을 대신한다.

## 심볼 인벤토리

(없음)

## 설계

```
test_swap_e2e.py (LLM mock):
    1) KNOWLEDGE_DIR=knowledge 로 앱 구동 → 질문 → 프롬프트 컨텍스트에 기본 도메인 문서가 실림
    2) KNOWLEDGE_DIR=knowledge-alt 로 재구동 (코드 무수정) → 같은 질문 →
       alt 도메인 문서가 실리고 기본 도메인 문서는 실리지 않음
    → 로직/콘텐츠 분리가 '주장'이 아니라 동작으로 증명됨

smoke_local.sh (MODEL=fake, 임시 포트):
    uvicorn 기동 → /api/chat 3턴 → data/conversations/오늘/*.json 존재 확인
    → load_to_sqlite.py --date 오늘 실행 → sqlite3 조회로 행 수 확인
    → 새 세션 6개 연속 시작 → 6번째가 429인지 확인
    → 하나라도 실패하면 종료코드 1
```

## 체크리스트

- [x] tests/test_swap_e2e.py: 로직 무수정 상태에서 KNOWLEDGE_DIR=knowledge-alt 구동 시 다른 도메인 문서가 프롬프트 컨텍스트에 실림을 검증 (LLM mock)
- [x] scripts/smoke_local.sh: MODEL=fake로 서버 기동→채팅→JSON 저장 확인→배치 실행→SQLite 조회→6번째 세션 429 확인 전 구간 스모크
- [x] 스모크 실패 시 비 0 종료코드

## 영향 범위

앱 코드는 수정하지 않는다(테스트·스크립트만 추가). 스모크가 실패하면 Phase 2~5 구현의 회귀를 뜻하므로 해당 phase로 되돌아간다.

## 검증

```bash
.venv/bin/python -m pytest tests/test_swap_e2e.py -q && bash scripts/smoke_local.sh
```

## 실행 결과

### 1회차 (2026-07-11 17:33 KST) — completed

**상태**: completed
**소요 시간**: 약 20분
**진행 모델**: Claude sonnet

#### 요약

`tests/test_swap_e2e.py`는 `app/chat.py`·`app/knowledge.py` 코드를 전혀 건드리지 않고 `Settings.knowledge_dir`만 `knowledge` → `knowledge-alt`로 바꿔 `chat.handle_message`를 두 번 호출해, MODEL=fake 스텁이 인용하는 문서 제목이 도메인에 따라 완전히 갈리는지(상담 도메인 제목은 alt 쪽에서 사라지고 커피 도메인 제목이 그 자리를 대체) 확인했다. `scripts/smoke_local.sh`는 매 실행마다 새 임시 디렉토리를 cwd로 삼아 uvicorn을 기동해 `data/ratelimit.json`·`data/conversations`를 실행 간 완전히 격리한 뒤, 신규 세션 5회 성공→6번째 429 → 기존 세션에 2턴 추가로 총 3턴 → JSON 파일 존재·턴 수 확인 → `load_to_sqlite.py --date` 배치 실행 → SQLite 행 수 확인까지 전 구간을 스모크하고, 실패 지점마다 비 0 종료코드로 빠진다.

#### 변경 파일

- `tests/test_swap_e2e.py` (신규, +46)
- `scripts/smoke_local.sh` (신규, +90, 실행권한 부여)

#### 검증 결과

- `pass` — `.venv/bin/python -m pytest tests/test_swap_e2e.py -q` → 1 passed
- `pass` — `bash scripts/smoke_local.sh` → `OK: 로컬 통합 스모크 전 구간 통과` (연속 재실행 2회 모두 통과 — rate limit 윈도우 격리가 실제로 실행 간 간섭 없이 동작함을 확인)
- `pass` — `.venv/bin/python -m pytest -q` (전체 스위트) → 30 passed, 회귀 없음

#### 추가 발견사항

- `app/ratelimit.py`의 `RateLimiter.DATA_PATH`("data/ratelimit.json")와 `app/storage.py`의 `DEFAULT_CONVERSATIONS_DIR`("data/conversations")는 상대경로로 고정돼 있고 env로 주입할 방법이 없다. 설계 pseudocode 순서(3턴/JSON 확인을 먼저, 6세션 rate-limit 확인을 나중)대로 그대로 구현하면 두 확인이 같은 IP의 rate limit 윈도우를 공유하게 되어 "6번째 신규 세션이 429"라는 경계가 어긋난다(3턴 체크에 쓴 세션 1개가 이미 윈도우를 1칸 소모하기 때문). smoke_local.sh에서는 순서를 (1) 6세션 rate-limit 경계 확인 → (2) 이미 등록된 세션 1개를 재사용해 2턴을 더 채워 총 3턴/JSON/SQLite 확인으로 재배열해 이 카운팅 충돌을 피했다. 스크립트가 매 실행마다 새 임시 cwd에서 서버를 띄우므로 상태 파일 자체도 실행마다 격리된다(재실행 2회 연속 통과로 확인).
- CAP06(지식 스왑) 실증은 이미 Phase 1에서 `tests/test_knowledge.py::test_directory_swap`, `test_sample_knowledge_sets_have_min_five_docs`로 `knowledge.load_documents/search` 레벨까지는 검증돼 있었다. 이번 Phase 6 테스트는 그 위에서 `chat.handle_message`(검색+LLM 호출 전 구간)를 통해 "코드 무수정 + env 값만 교체"로 실제 응답 문구까지 바뀜을 증명한다는 점에서 레이어가 다르다.

#### 질문 / 결정 사항

없음.

#### Commit
- `1162dfb` test(swap-e2e): Phase 6 — 지식 스왑 e2e + 로컬 통합 스모크 (review pass, simplify 변경 0, 검증 재실행 pass)
