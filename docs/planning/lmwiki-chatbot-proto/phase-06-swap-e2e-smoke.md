---
phase: 6
title: 지식 스왑 e2e + 로컬 통합 스모크
status: pending
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

- [ ] tests/test_swap_e2e.py: 로직 무수정 상태에서 KNOWLEDGE_DIR=knowledge-alt 구동 시 다른 도메인 문서가 프롬프트 컨텍스트에 실림을 검증 (LLM mock)
- [ ] scripts/smoke_local.sh: MODEL=fake로 서버 기동→채팅→JSON 저장 확인→배치 실행→SQLite 조회→6번째 세션 429 확인 전 구간 스모크
- [ ] 스모크 실패 시 비 0 종료코드

## 영향 범위

앱 코드는 수정하지 않는다(테스트·스크립트만 추가). 스모크가 실패하면 Phase 2~5 구현의 회귀를 뜻하므로 해당 phase로 되돌아간다.

## 검증

```bash
.venv/bin/python -m pytest tests/test_swap_e2e.py -q && bash scripts/smoke_local.sh
```
