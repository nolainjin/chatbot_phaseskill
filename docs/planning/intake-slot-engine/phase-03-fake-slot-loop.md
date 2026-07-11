---
phase: 3
title: fake 슬롯 루프 통합
status: completed
depends_on: [1, 2]
scope:
  - app/chat.py
  - app/intake.py
  - tests/test_slot_flow.py
intervention_likely: false
intervention_reason: ""
executor: sonnet
load_bearing: "`app/chat.py` handle_message의 슬롯 상태·프롬프트 주입·fake 추출 배선이 핵심 — CAP02~06/12가 전부 이 배선에 걸림"
e2e_refs: []
e2e_triggers: []
phase_context:
  baseline: "missing"
  adoption: "bootstrap"
  coverage: "standard"
  enforcement_during_run: "warn"
  materialize_at: "finalization"
---

# Phase 3: fake 슬롯 루프 통합

> **범위**: Backend
> **난이도**: M
> **의존성**: Phase 1, 2
> **영향 파일**: `app/chat.py`, `app/intake.py`

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 배경

파서(Phase 1)와 스키마(Phase 2)를 대화 루프에 배선한다. 이 phase의 invariant는 하나 — "fake 모드에서 스키마 선언대로 문진이 돈다": 세션 슬롯 상태, 조건부 활성, 매 턴 채워진/미충족 슬롯 주입, 레드플래그 우선 정렬, 발화에서 다중 슬롯 결정론 추출, 개방형 첫 질문. 실모드 추출 프로토콜은 Phase 4로 분리했다(스펙 리뷰 O3 — invariant 2개를 한 phase에 담지 않기). 현재 fake 스텁은 문진을 전혀 흉내내지 못하므로(app/llm.py:22-25) 이 phase 없이는 "데모 완성" 요구가 fake-satisfy될 위험이 있다 — 어드버서리얼 플래그 CAP02/04/05/10의 몸통이 여기다.

E2E 카탈로그 부재 — e2e_refs 빈 값(사용자 승인 2026-07-12). 카탈로그 refresh 전까지 E2E 비활성.

## 심볼 인벤토리

- `handle_message`
  - 근거: app/chat.py:57
- `ChatSession`
  - 근거: app/chat.py:32
- `llm.ask`
  - 근거: app/chat.py:72
- `append_turn`
  - 근거: app/storage.py:25
- `load_schema`
  - [NEW]
- `extract_fake`
  - [NEW]

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 설계

의사코드 수준 흐름 (handle_message 확장):

```
schema = intake.load_schema(settings.knowledge_dir)
schema 없음(None) → 기존 경로 그대로 (폴백 — 분기 최소, knowledge-alt 무영향)

schema 활성:
  1. fake 모드면 llm 호출 전 extract_fake(message, schema, session.slots)
     - 스키마 signals 부분문자열 매칭, 한 발화에서 여러 슬롯 동시 충족
     - 이미 채워진 슬롯은 덮지 않음 (트랙 뒤집힘 방지)
  2. 발화가 red_flag 슬롯 signals에 걸리면 그 슬롯을 미충족 목록 최상단으로
  3. system 프롬프트에 슬롯 섹션 주입 (모드 공통):
     채워진 슬롯 / 미충족 슬롯(우선순위순) / 레드플래그 우선 질문 규칙 /
     턴 예산(잔여 턴, 우선순위 소비) / 1턴이면 opening_question 개방형 시작 지시
  4. fake 모드 reply = llm.ask 스텁 반환값 유지 + chat.py에서 진행 접미사 부착
     예: "[fake] 참고 문서: ... | 채움: 트랙=관계 | 다음 질문: 대상"
```

설계 제약:

- ChatSession에 `slots: dict[str, str]` 필드 추가 — 메모리 dict, 기존 세션 설계와 일관(재시작 소실은 프로토타입 수용 범위).
- app/llm.py는 무수정. 접미사는 chat.py에서 붙인다 — tests/test_swap_e2e.py:40-46과 tests/test_chat.py:27,33의 문서 제목 부분문자열 단언이 그대로 보존된다(스펙 리뷰에서 실파일 대조 확인).
- API 반환 {reply, turn, limit_reached}·storage.append_turn 호출 형태 무변경 (CAP16/17).
- 요약 경로는 이 phase에서 건드리지 않는다 (Phase 5 소유 — tests/test_intake.py 기존 단언이 이 phase 커밋 시점에 깨지지 않는 이유).

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 체크리스트

- [x] ChatSession 슬롯 상태 + 시스템 프롬프트 슬롯 섹션 주입 구현 (채워진/미충족 우선순위순·턴 예산)
- [x] tests/test_slot_flow.py — 1턴 시스템 프롬프트에 opening_question 포함 단언 (CAP12)
- [x] tests/test_slot_flow.py — 조건부 활성 배선 단언: 트랙=위기 채움 시 자해 계획·수단 슬롯 활성 (CAP02)
- [x] tests/test_slot_flow.py — fake 다중 추출 단언: 1발화에서 2슬롯 동시 충족 (CAP04)
- [x] tests/test_slot_flow.py — 레드플래그 신호 시 미충족 목록 최상단 정렬 단언 (CAP05)
- [x] tests/test_slot_flow.py — 기채움 슬롯 덮어쓰기 금지 단언: 후속 발화가 트랙 값을 못 뒤집음
- [x] knowledge-alt(스키마 없음) 경로 기존 동작 유지 단언
- [x] 전체 pytest 통과 (API 계약·스왑 회귀 포함)

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 영향 범위

app/chat.py(100줄)와 app/intake.py 확장. 스키마 없는 지식셋(knowledge-alt)은 `schema None → 기존 경로` 분기로 완전 격리 — 회귀 표면은 knowledge/(스키마 활성) 경로의 fake reply 접미사뿐이며 기존 단언은 부분문자열 검사라 안전. 이 phase 커밋 후 Phase 4 전까지 실모드는 슬롯 지시 없이 주입만 되는 중간 상태 창 존재 — 직렬 실행·fake 데모 전제로 수용(스펙 리뷰 기록). 롤백 = chat.py diff revert (intake.py 확장은 미배선 상태로 무해).

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 검증

```bash
pytest tests/test_slot_flow.py -q  # edge: 스키마 없는 지식셋(knowledge-alt)에서 슬롯 섹션·접미사 미개입 단언 포함
pytest -q
```

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 실행 결과

### 1회차 (2026-07-12 KST) — completed
**상태**: completed
**소요 시간**: 약 20분
**진행 모델**: Claude `sonnet`

#### 요약
`intake.py`에 `extract_fake`(signals 부분문자열 매칭, dict/list 두 형태 지원, 기채움 슬롯 보호)와 `detect_red_flags`(red_flag 슬롯 신호 감지)를 추가하고, `chat.py`의 `handle_message`에 스키마 활성 시 슬롯 섹션 주입 + fake 모드 다중 추출 + 레드플래그 우선 정렬 + 진행 접미사 부착 배선을 완성했다. `schema is None`이면 기존 경로 그대로 폴백해 knowledge-alt 무영향을 유지했다.

#### 변경 파일
- `app/intake.py` (modified, +50/-0)
- `app/chat.py` (modified, +59/-2)
- `tests/test_slot_flow.py` (new, +143/-0)

#### 검증 결과
- [x] pytest tests/test_slot_flow.py -q: `.venv/bin/python -m pytest tests/test_slot_flow.py -q` -> pass (6 passed)
- [x] pytest -q (전체): `.venv/bin/python -m pytest -q` -> pass (58 passed, 기존 test_chat.py/test_swap_e2e.py/test_intake.py 회귀 없음)

#### 추가 발견사항
없음

#### 질문 / 결정 사항
없음
