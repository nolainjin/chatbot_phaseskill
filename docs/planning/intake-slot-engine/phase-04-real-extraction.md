---
phase: 4
title: 실모드 단일 호출 추출 + 신뢰 경계 검증
status: completed
depends_on: [3]
scope:
  - app/chat.py
  - app/intake.py
  - tests/test_slot_extract.py
intervention_likely: false
intervention_reason: ""
executor: sonnet
load_bearing: "`app/intake.py` extract_real의 신뢰 경계 검증(화이트리스트·str 강제·길이 상한·덮어쓰기 금지)이 핵심 — LLM 출력이 세션 상태·저장으로 증폭되는 경로의 유일한 관문"
e2e_refs: []
e2e_triggers: []
phase_context:
  baseline: "missing"
  adoption: "bootstrap"
  coverage: "standard"
  enforcement_during_run: "warn"
  materialize_at: "finalization"
---

# Phase 4: 실모드 단일 호출 추출 + 신뢰 경계 검증

> **범위**: Backend
> **난이도**: S
> **의존성**: Phase 3
> **영향 파일**: `app/intake.py`, `app/chat.py`

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 배경

실모드(실제 Claude 호출)에서 매 턴 슬롯을 추출한다. 방식은 사용자 결정 D02 — 단일 호출 통합: 응답 생성 호출에 추출 지시를 포함하고 모델 출력에서 응답 텍스트/슬롯 JSON을 분리한다(턴당 호출 1회 유지 = 비용 무증가, 파싱 실패 턴은 추출 스킵하고 다음 턴에 만회). 스펙 리뷰 보안 렌즈 지적(O2)을 반영해 신뢰 경계 검증을 함께 넣는다: LLM 출력은 신뢰 경계 밖이므로 파싱에 성공해도 스키마가 선언한 슬롯만, 문자열만, 상한 길이 안에서만 세션에 병합한다 — 비정상 출력이 session.slots → 다음 턴 프롬프트 → 요약 JSON 저장으로 증폭되는 경로(FP19)를 여기서 끊는다.

E2E 카탈로그 부재 — e2e_refs 빈 값(사용자 승인 2026-07-12). 카탈로그 refresh 전까지 E2E 비활성.

## 심볼 인벤토리

- `handle_message`
  - 근거: app/chat.py:57
- `llm.ask`
  - 근거: app/chat.py:72
- `extract_real`
  - [NEW]

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 설계

의사코드 수준 흐름:

```
실모드 + schema 활성:
  system 프롬프트에 추출 지시 추가:
    "응답 마지막에 ```slots fenced JSON으로 이번 발화에서 확인된 슬롯을 출력하라"
  reply_raw = llm.ask(...)
  clean_reply, accepted = intake.extract_real(reply_raw, schema, session.slots)

extract_real(reply, schema, filled):
  fenced ```slots 블록 분리 실패 / JSON 파싱 실패 → (원문 그대로, 빈 dict)  # 추출 스킵
  파싱 성공 시 각 항목에 신뢰 경계 필터:
    (a) 스키마 활성 슬롯 id 화이트리스트에 없는 키 → 폐기
    (b) str 강제 변환 불가 값 → 폐기
    (c) 길이 200자 초과 값 → 폐기
    (d) 이미 채워진 슬롯 → 폐기 (덮어쓰기 금지)
  통과분만 반환 → session.slots 병합
```

사용자에게 보이는 reply와 history·storage에는 슬롯 JSON 제거본(clean_reply)을 저장한다 — llm.ask 반환 직후 storage.append_turn 사이에 끼우면 기존 흐름과 충돌 없음(스펙 리뷰에서 chat.py:72-82 실측 확인). app/llm.py는 계속 무수정 — 추출 지시는 chat.py가 조립하는 system 문자열의 일부다.

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 체크리스트

- [x] 실모드 추출 지시 주입 + extract_real 구현 (단일 호출 통합, D02)
- [x] tests/test_slot_extract.py — 실모드 슬롯 JSON 분리·파싱 실패 시 추출 스킵·응답 원문 유지 단언
- [x] tests/test_slot_extract.py — 비정상 슬롯 id·비문자열 값·과길이 값·기채움 덮어쓰기 폐기 단언 (신뢰 경계)
- [x] history·reply에 슬롯 JSON 제거본 저장 단언
- [x] 전체 pytest 통과

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 영향 범위

실모드 경로에만 추가 — fake 모드·스키마 없는 지식셋은 무영향. 테스트는 llm.ask를 monkeypatch한 가짜 출력으로 결정론 검증(실 API 불필요). 파싱 실패의 최악 결과는 "그 턴 추출 스킵"으로 상한이 잡혀 있다. 롤백 = extract_real 배선 제거 (Phase 3 상태로 복귀).

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 검증

```bash
pytest tests/test_slot_extract.py -q  # edge: 깨진 JSON·화이트리스트 밖 슬롯 id·과길이 값 → 폐기·응답 원문 유지 단언 포함
pytest -q
```

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 실행 결과

### 1회차 (2026-07-12 08:48 KST) — completed
**상태**: completed
**소요 시간**: 약 20분
**진행 모델**: Claude `sonnet`

#### 요약
`app/intake.py`에 `extract_real`을 추가해 실모드 LLM 응답에서 ```` ```slots ```` fenced JSON을 분리하고, 스키마 활성 슬롯 화이트리스트·문자열 강제·200자 상한·기채움 보호 4중 필터로 신뢰 경계를 검증했다. `app/chat.py`는 실모드+스키마 조합일 때만 시스템 프롬프트에 추출 지시를 추가하고(D02 단일 호출 통합), `llm.ask` 응답을 `extract_real`에 통과시켜 clean_reply를 history·storage에 저장하도록 배선했다. fake 모드·스키마 없는 지식셋 경로는 무수정.

#### 변경 파일
- `app/intake.py` (modified, +43/-0 lines)
- `app/chat.py` (modified, +20/-1 lines)
- `tests/test_slot_extract.py` (new, +266 lines)

#### 검증 결과
- [x] `pytest tests/test_slot_extract.py -q`: `.venv/bin/python -m pytest tests/test_slot_extract.py -q` → pass (15 passed)
- [x] `pytest -q`: `.venv/bin/python -m pytest -q` → pass (73 passed, 1 warning — 기존 httpx deprecation 경고, 본 phase와 무관)

#### 추가 발견사항
없음

#### 질문 / 결정 사항
없음

#### Commit
- `8d82ff5` feat(intake): Phase 4 — 실모드 단일 호출 슬롯 추출 + 신뢰 경계 검증
