---
phase: 3
title: 대화 JSON 저장 + SQLite 일배치
status: pending
depends_on: [2]
scope:
  - app/storage.py
  - app/chat.py
  - scripts/load_to_sqlite.py
  - tests/test_storage_batch.py
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

# Phase 3: 대화 JSON 저장 + SQLite 일배치

> **범위**: Backend
> **난이도**: S
> **의존성**: Phase 2
> **영향 파일**: `app/storage.py` (신규), `scripts/load_to_sqlite.py` (신규)

## 배경

origin §4의 저장 구조 그대로: 대화 내역을 우선 JSON 파일로 저장하고, 하루 1회 배치가 SQLite에 적재한다. 복잡한 서버 DB는 금지. capabilities.md 적대적 플래그(CAP09)가 "적재 함수만 만들고 실제 스케줄은 안 걸리는" fake-satisfy를 경고하므로, 크론 등록 절차 문서화(이 phase)와 실배포 스케줄 검증(Phase 8)이 짝으로 붙는다.

## 심볼 인벤토리

- `app.storage.append_turn`
  - [NEW]
- `scripts.load_to_sqlite.main`
  - [NEW]

## 설계

```
append_turn(session_id, role, text):
    data/conversations/YYYY-MM-DD/{session_id}.json 에 턴 추가
    (표준 json 모듈, 파일 단위 재작성 — 세션당 최대 20턴이라 작음)

load_to_sqlite.py [--date YYYY-MM-DD]:   # 기본 = 어제
    해당 일자 JSON 전부 → data/chatlog.db 의 conversations/turns 테이블 UPSERT
    (표준 sqlite3, 세션+턴번호 PK → 재실행해도 중복 없음 = 멱등)
```

- chat.py의 대화 처리 경로에 저장 훅 한 줄을 연결한다 (사용자 발화·봇 응답 각각).
- 크론 예시(`0 3 * * * .venv/bin/python scripts/load_to_sqlite.py`)를 스크립트 헤더와 README에 문서화. 실제 등록은 Phase 8 배포에서.

## 체크리스트

- [ ] app/storage.py: 대화 턴을 data/conversations/YYYY-MM-DD/{session_id}.json 에 저장 (표준 json 모듈)
- [ ] app/chat.py 대화 처리 경로에 저장 훅 연결
- [ ] scripts/load_to_sqlite.py: 전일자(또는 --date 지정) JSON을 data/chatlog.db에 적재, 재실행 멱등 (표준 sqlite3 모듈)
- [ ] 크론 등록 방법 주석+README 문서화 (실등록은 Phase 8)
- [ ] tests/test_storage_batch.py: 저장→적재→조회 왕복 + 멱등성 테스트 통과

## 영향 범위

chat.py 한 줄 수정(저장 훅). Phase 6 스모크와 Phase 8 배포 검증이 이 저장 경로를 사용. data/ 디렉토리는 .gitignore 대상(Phase 1). 롤백 = 훅 제거 + 파일 삭제.

## 검증

```bash
.venv/bin/python -m pytest tests/test_storage_batch.py -q
```
