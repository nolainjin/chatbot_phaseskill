---
phase: 3
title: 대화 JSON 저장 + SQLite 일배치
status: completed
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

- [x] app/storage.py: 대화 턴을 data/conversations/YYYY-MM-DD/{session_id}.json 에 저장 (표준 json 모듈)
- [x] app/chat.py 대화 처리 경로에 저장 훅 연결
- [x] scripts/load_to_sqlite.py: 전일자(또는 --date 지정) JSON을 data/chatlog.db에 적재, 재실행 멱등 (표준 sqlite3 모듈)
- [x] 크론 등록 방법 주석+README 문서화 (실등록은 Phase 8)
- [x] tests/test_storage_batch.py: 저장→적재→조회 왕복 + 멱등성 테스트 통과

## 영향 범위

chat.py 한 줄 수정(저장 훅). Phase 6 스모크와 Phase 8 배포 검증이 이 저장 경로를 사용. data/ 디렉토리는 .gitignore 대상(Phase 1). 롤백 = 훅 제거 + 파일 삭제.

## 검증

```bash
.venv/bin/python -m pytest tests/test_storage_batch.py -q
```

## 실행 결과

### 1회차 (2026-07-11 13:55 KST) — completed

**상태**: completed
**소요 시간**: 약 20분
**진행 모델**: Claude sonnet

#### 요약

app/storage.py에 append_turn 함수를 신규 작성해 세션 대화 턴을 data/conversations/YYYY-MM-DD/{session_id}.json에 저장하게 했다. chat.py의 handle_message 안, LLM 응답을 받은 직후에 사용자 발화·봇 응답 각각을 append_turn으로 기록하는 훅 두 줄을 연결했다. scripts/load_to_sqlite.py를 신규 작성해 지정 날짜(기본값 어제)의 세션 JSON을 전부 읽어 data/chatlog.db의 conversations/turns 테이블에 UPSERT하도록 했다 — PK가 (session_id, seq)라 재실행해도 중복 적재되지 않는다. 크론 등록 예시는 스크립트 docstring과 README 두 곳에 문서화했다(실제 등록은 Phase 8).

#### 변경 파일

- `app/storage.py` (신규, +29)
- `scripts/load_to_sqlite.py` (신규, +85)
- `tests/test_storage_batch.py` (신규, +68)
- `app/chat.py` (+4/-1) — storage import + append_turn 훅 2줄
- `[ripple] README.md` (+13) — 저장/배치 적재 섹션 + 크론 예시 문서화 (frontmatter scope 밖이지만 체크리스트 4번 항목이 명시적으로 요구해 추가함, 15줄 이하·기계적 추가)

#### 검증 결과

`.venv/bin/python -m pytest tests/test_storage_batch.py -q` → 4 passed (저장 JSON 형식, 저장→적재 왕복, 멱등성, 존재하지 않는 날짜 처리).
`.venv/bin/python -m pytest -q` (전체) → 19 passed, 1 warning(기존 starlette/httpx deprecation 경고, Phase 3 무관) — 저장 훅이 기존 test_chat.py 흐름에서도 정상 동작해 data/conversations/에 실제 JSON을 남기는 것을 확인했고, 확인 후 테스트 산출물은 삭제했다(data/는 .gitignore 대상).

#### 추가 발견사항

없음.

#### 질문 / 결정 사항

없음.

### 2회차 (2026-07-11 17:25 KST) — completed

**상태**: completed
**소요 시간**: 약 5분
**진행 모델**: Claude fable (orchestrator 직접 수정 — worker 세션 한도로 재dispatch 불가)

#### 요약
리뷰 fix_required 대응: 공개 /api/chat의 session_id가 파일명으로 그대로 쓰여 `../` 경로 조작이 가능하던 문제를 storage.append_turn 입구에서 화이트리스트(`[A-Za-z0-9._-]{1,128}`) 검증으로 차단했다. 모든 호출자가 이 함수를 거치므로 공유 지점 1곳 수정으로 해결.

#### 변경 파일
- `app/storage.py` (modified, +7/-0)
- `tests/test_storage_batch.py` (modified, +10/-0)

#### 검증 결과
- [x] 경로 조작 거부: `.venv/bin/python -m pytest tests/test_storage_batch.py -q` -> pass (5 passed, 신규 traversal 테스트 포함)
- [x] 전체 회귀: `.venv/bin/python -m pytest -q` -> pass (29 passed)

#### 추가 발견사항
없음.

#### 질문 / 결정 사항
없음.

#### Commit
- `cd6cf72` feat(storage): Phase 3 — 대화 JSON 저장 + SQLite 일배치 적재 (review fix_required → session_id 검증 반영 후 pass, README ripple 인정, 검증 재실행 pass)
