---
phase: 5
title: 구조화 JSON 요약 + Phase 9 테스트 정합
status: completed
depends_on: [4]
scope:
  - app/chat.py
  - app/intake.py
  - tests/test_intake.py
intervention_likely: false
intervention_reason: ""
executor: sonnet
load_bearing: "`app/chat.py` MAX_TURNS 분기에서 LLM 호출 요약 → 결정론 JSON 요약 전환이 핵심 — CAP07(미확인)·CAP08(구조화 JSON)이 여기서 결정"
e2e_refs: []
e2e_triggers: []
phase_context:
  baseline: "missing"
  adoption: "bootstrap"
  coverage: "standard"
  enforcement_during_run: "warn"
  materialize_at: "finalization"
---

# Phase 5: 구조화 JSON 요약 + Phase 9 테스트 정합

> **범위**: Backend
> **난이도**: S
> **의존성**: Phase 4
> **영향 파일**: `app/chat.py`, `tests/test_intake.py`

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 배경

면담 종료(MAX_TURNS 도달) 시 intake_summary를 산문이 아닌 "채워진 스키마의 구조화 JSON"으로 저장한다(origin §2). 채워진 슬롯은 이미 세션 상태에 있으므로 LLM을 부를 이유가 없다 — 결정론 생성이라 fake 모드에서도 동일하게 돈다. 못 채운 슬롯은 "미확인"으로 남긴다(CAP07). 기존 테스트와의 충돌 1건을 함께 정리한다: tests/test_intake.py:98-123의 test_summary_failure는 "요약 LLM 호출 실패 격리"를 knowledge/ 기준으로 검증하는데, 스키마 활성 시 요약이 LLM을 안 타므로 전제가 깨진다 → 스키마 없는 tmp 지식셋으로 옮겨 레거시 경로를 계속 검증한다.

accepted risk (스펙 리뷰 GM22): 위기 슬롯 민감정보(자해 계획·수단·시도 이력)가 구조화 JSON으로 평문 저장되어 기계판독 용이성이 올라간다. 구조화 저장 자체가 origin verbatim §2의 사용자 지시이고 intake.md Risks에 이미 표면화·수용된 항목이다. 저장 표면은 기존 append_turn 경로 재사용으로 확대하지 않는다.

E2E 카탈로그 부재 — e2e_refs 빈 값(사용자 승인 2026-07-12). 카탈로그 refresh 전까지 E2E 비활성.

## 심볼 인벤토리

- `_SUMMARY_INSTRUCTION`
  - 근거: app/chat.py:25
- `append_turn`
  - 근거: app/storage.py:25
- `test_summary_failure_does_not_break_conversation_storage`
  - 근거: tests/test_intake.py:98
- `build_summary_json`
  - [NEW]

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 설계

의사코드 수준 흐름 (MAX_TURNS 도달 분기):

```
schema 활성:
  summary = intake.build_summary_json(schema, session.slots)
    → {track, slots: {채워진 슬롯}, unfilled: [활성인데 못 채운 슬롯 → "미확인"],
       red_flags: [채워진 슬롯 중 red_flag=true인 id 파생]}
    → json.dumps(..., ensure_ascii=False) 문자열
  storage.append_turn(session_id, "intake_summary", summary)   # 기존 경로 그대로
schema 없음:
  기존 _SUMMARY_INSTRUCTION 산문 요약 경로 그대로 (llm.ask 경유, try/except 격리 유지)
```

- red_flags는 별도 감지 이력 상태 없이 채워진 red_flag 슬롯에서 파생한다. 신호가 감지됐지만 끝내 못 채운 레드플래그 슬롯은 unfilled의 미확인으로 표기된다 — 정보 손실 없음(스펙 리뷰 R-O5 반영).
- text 필드에 JSON "문자열"을 넣으므로 저장 스키마 {seq, role, text} 무변경 (CAP17).

tests/test_intake.py 정합:

- test_summary_failure_does_not_break_conversation_storage → 스키마 없는 tmp 지식셋(임시 디렉토리에 일반 문서만)으로 이동해 레거시 LLM 요약 실패 격리를 계속 검증.
- test_intake_summary_recorded_once_at_max_turns → knowledge/ 기준 그대로 유지(role 카운트 단언은 JSON 문자열 요약과 호환 — 스펙 리뷰 확인). 요약 JSON 파싱·미확인 필드 단언을 추가.

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 체크리스트

- [x] 스키마 활성 시 LLM 무호출 구조화 JSON 요약 구현 — unfilled 슬롯 미확인 포함, text 필드 문자열 직렬화
- [x] 스키마 부재 시 기존 _SUMMARY_INSTRUCTION 산문 요약 경로 보존
- [x] tests/test_intake.py — test_summary_failure를 스키마 없는 지식셋으로 이동해 레거시 요약 실패 격리 검증 유지
- [x] tests/test_intake.py — 요약 JSON 파싱 가능·미확인 필드 존재 단언 추가
- [x] 요약 저장은 기존 append_turn(role=intake_summary) 경로만 사용 — 신규 저장 표면 없음 확인
- [x] 전체 pytest 통과

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 영향 범위

MAX_TURNS 분기와 tests/test_intake.py만. 스키마 없는 지식셋의 요약 동작은 문자 그대로 무변경. 위기 슬롯 민감정보의 구조화 평문 저장은 위 accepted risk 참조 — 신규 저장 표면 없음이 체크리스트로 강제된다. 롤백 = 분기 revert (레거시 경로가 그대로 남아 있어 안전).

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 검증

```bash
pytest tests/test_intake.py -q  # edge: 10턴 내 미충족 슬롯이 요약 JSON unfilled에 '미확인'으로 존재 단언 포함
pytest -q
```

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 실행 결과

### 1회차 (2026-07-12 00:00 KST) — completed
**상태**: completed
**소요 시간**: 약 15분
**진행 모델**: Claude `sonnet`

#### 요약
MAX_TURNS 분기에 `intake.build_summary_json`을 추가해 스키마 활성 시 LLM 호출 없이 세션 슬롯 상태만으로 구조화 JSON 요약을 만들고, 기존 `append_turn(role=intake_summary)` 경로로 문자열 직렬화해 저장하도록 바꿨다. 스키마 없는 지식셋은 기존 `_SUMMARY_INSTRUCTION` 산문 요약 경로를 그대로 보존한다. tests/test_intake.py의 요약 실패 격리 테스트를 스키마 없는 tmp 지식셋으로 옮기고, 정상 요약 테스트에 JSON 파싱·미확인 필드 단언을 추가했다.

#### 변경 파일
- `app/intake.py` (modified, +19/-0)
- `app/chat.py` (modified, +19/-10)
- `tests/test_intake.py` (modified, +16/-1)

#### 검증 결과
- [x] pytest tests/test_intake.py -q: `.venv/bin/python -m pytest tests/test_intake.py -q` -> pass (5 passed)
- [x] pytest -q (전체): `.venv/bin/python -m pytest -q` -> pass (73 passed)

#### 추가 발견사항
없음

#### 질문 / 결정 사항
없음
