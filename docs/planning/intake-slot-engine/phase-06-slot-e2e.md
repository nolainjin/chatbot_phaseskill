---
phase: 6
title: fake e2e 4종 + 스왑 회귀
status: completed
depends_on: [2, 3, 4, 5]
scope:
  - tests/test_slot_e2e.py
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

# Phase 6: fake e2e 4종 + 스왑 회귀

> **범위**: 테스트 전용
> **난이도**: M
> **의존성**: Phase 2, 3, 4, 5
> **영향 파일**: `tests/test_slot_e2e.py` [NEW]

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 배경

task 성공 기준 그 자체 — fake 모드 e2e 시나리오 4종(정서/관계/위기 레드플래그 우선/혼합 발화 다중 슬롯) + knowledge-alt 스왑 폴백 회귀 + 전체 pytest. CAP 원장의 어드버서리얼 플래그가 요구하는 단언 수준을 지킨다: 위기 시나리오는 "레드플래그가 다른 슬롯보다 먼저 질문된다"는 순서 단언(CAP22 — 그냥 위기 트랙을 태우기만 하고 통과 처리하는 fake-satisfy 차단), 혼합 시나리오는 "2슬롯이 실제로 동시에 채워졌다"는 개수 단언(CAP23)이 있어야 한다.

E2E 카탈로그 부재 — e2e_refs 빈 값(사용자 승인 2026-07-12). 이 phase의 pytest e2e가 카탈로그 E2E를 대체한다.

## 심볼 인벤토리

- `handle_message`
  - 근거: app/chat.py:57
- `MAX_TURNS`
  - 근거: app/chat.py:13

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 설계

fake 모드(MODEL=fake, API 키 불필요)로 handle_message를 시나리오별 다턴 구동. 발화 문구는 Phase 2 스키마의 signals와 맞물리게 작성.

- ① 정서: 1턴 시스템 프롬프트에 opening_question 포함 단언(CAP12) → "우울해서 잠을 못 자요" → track=정서 채움 → 10턴 소진 후 요약 JSON의 track=정서 단언.
- ② 관계: 동일 구조로 track=관계 경로 검증.
- ③ 위기: 자해 신호 발화 → 다음 질문(fake reply의 "다음 질문:" 접미사)이 레드플래그 슬롯임을 단언 — 우선 질문 "순서"를 직접 검증.
- ④ 혼합: "남편과 갈등 때문에 잠을 못 자요" → track=관계 + 정서 증상 슬롯이 한 발화에서 동시 충족(2개) 단언.
- 스왑 회귀: knowledge-alt 구동 시 reply에 진행 접미사가 없고 기존 스텁 형식 그대로임을 단언 + 기존 test_swap_e2e 포함 전체 pytest.

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 체크리스트

- [x] tests/test_slot_e2e.py — 정서 시나리오: 1턴 opening_question 단언 + 요약 JSON track=정서 단언
- [x] tests/test_slot_e2e.py — 관계 시나리오: 요약 JSON track=관계 단언
- [x] tests/test_slot_e2e.py — 위기 시나리오: 레드플래그 슬롯 우선 질문 순서 단언 (CAP22)
- [x] tests/test_slot_e2e.py — 혼합 발화 시나리오: 2슬롯 동시 충족 단언 (CAP23)
- [x] tests/test_slot_e2e.py — knowledge-alt 스왑 회귀 단언: 진행 접미사 없음·기존 스텁 형식 유지 (CAP18)
- [x] 전체 pytest 통과 (CAP24)

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 영향 범위

신규 테스트 파일만 — 프로덕션 코드 무변경. 실패 시 원인은 Phase 2~5 산출물에 있으므로 이 phase는 회귀 검출기 역할. 롤백 = 파일 삭제(무해).

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 검증

```bash
pytest tests/test_slot_e2e.py -q  # edge: 위기 시나리오 — 레드플래그 미충족 상태에서 다음 질문이 레드플래그 슬롯임을 순서 단언
pytest -q
```

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 실행 결과

### 1회차 (2026-07-12 09:08 KST) — completed
**상태**: completed
**소요 시간**: 약 20분
**진행 모델**: Claude `sonnet`

#### 요약
handle_message/intake 심볼과 실제 `knowledge/_intake_schema.md` 슬롯 정의(signals, priority, when, red_flag)를 먼저 근거로 확인한 뒤 `tests/test_slot_e2e.py`를 신규 작성했다. 정서·관계 트랙은 10턴 소진 후 저장된 `intake_summary` JSON의 track 값을 단언하고, 위기 트랙은 "자해할 계획이 있어요" 한 발화로 track=위기 채움과 동시에 red_flag signal("계획")을 감지시켜 미충족 crisis_plan_means가 priority 1인 chief_complaint보다 먼저 "다음 질문:"에 노출되는 순서를 직접 단언했다(CAP22). 혼합 발화는 track+support 2슬롯이 한 발화에서 동시 충족됨을 개수·값으로 단언했고(CAP23), knowledge-alt 스왑은 진행 접미사 없이 기존 스텁 형식이 유지됨을 단언했다(CAP18).

#### 변경 파일
- `tests/test_slot_e2e.py` (new, +124/-0)

#### 검증 결과
- [x] `pytest tests/test_slot_e2e.py -q` -> pass (5 passed)
- [x] `pytest -q` -> pass (78 passed, 1 pre-existing warning: fastapi/starlette httpx deprecation, 본 phase와 무관)

#### 추가 발견사항
NOTES:
- `## 설계` 4번(혼합) 예시 발화 "남편과 갈등 때문에 잠을 못 자요"는 실제 코드 동작과 안 맞는다. `_match_signal`이 track.signals dict를 정서→관계→위기 선언 순으로 검사하므로 "잠"이 먼저 걸려 track=정서로 확정되고(관계가 아님), 게다가 애초에 "증상 슬롯"(symptom_context)은 `when: "track=정서"`라 track=관계로 확정된다 해도 절대 활성화될 수 없다 — 두 슬롯이 서로 배타적인 when 조건이라 설계문의 "track=관계 + 정서 증상 슬롯 동시 충족"은 코드상 성립 불가능한 조합이다. 체크리스트 항목 자체는 "2슬롯 동시 충족"(CAP23 원문)만 요구하므로, 실제로 동시 매칭되는 문장("남편과 가족 문제로 너무 힘들어요" → track=관계 + support=가족)으로 대체해 CAP23 요구사항은 그대로 충족시켰다. 이 파일(tests/test_slot_e2e.py) 범위 내 판단이라 SCOPE_CHANGE_REQUEST 대상은 아니며, 추후 spec-review 갱신 시 참고용으로만 남긴다.

#### 질문 / 결정 사항
없음

#### Commit
- `5620380` test(slot-engine): Phase 6 — fake e2e 4종 + knowledge-alt 스왑 회귀 테스트 추가
