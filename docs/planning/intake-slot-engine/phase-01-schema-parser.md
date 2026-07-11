---
phase: 1
title: 스키마 파서 + 슬롯 모델
status: completed
depends_on: []
scope:
  - app/intake.py
  - tests/test_intake_schema.py
intervention_likely: false
intervention_reason: ""
executor: sonnet
load_bearing: "`app/intake.py` load_schema의 None 폴백 계약이 핵심 — 파서 강건성이 CAP09(스키마 부재·형식 오류 폴백) 전체를 결정"
e2e_refs: []
e2e_triggers: []
phase_context:
  baseline: "missing"
  adoption: "bootstrap"
  coverage: "standard"
  enforcement_during_run: "warn"
  materialize_at: "finalization"
---

# Phase 1: 스키마 파서 + 슬롯 모델

> **범위**: Backend
> **난이도**: S
> **의존성**: 없음
> **영향 파일**: `app/intake.py` [NEW]

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 배경

지금 봇은 `_persona.md` 산문 정책만으로 10턴 면담을 자유 진행해 필수 항목 누락을 막을 장치가 없다. 이 task는 "무엇을 수집할지"를 코드가 아닌 knowledge 데이터(`_intake_schema.md`)로 선언하는 도메인 무관 엔진을 추가한다. Phase 1은 그 첫 단추 — 스키마 선언을 읽어 슬롯 모델로 바꾸는 파서다. 형식은 사용자 결정 D01(마크다운 + 기계 파싱용 YAML 블록 1개, 파싱 실패 = 형식 오류 = 폴백)을 따른다. 파서가 어떤 입력에서도 예외를 새지 않고 None으로 수렴해야 스키마 오류 하나가 대화 전체를 죽이는 사고(FP1)를 막는다.

E2E 카탈로그 부재 — e2e_refs 빈 값(사용자 승인 2026-07-12). 카탈로그 refresh 전까지 카탈로그 기반 E2E는 비활성이며, 이 task의 e2e는 Phase 6 pytest로 강제한다.

## 심볼 인벤토리

- `yaml.safe_load`
  - 근거: app/knowledge.py:38
- `load_schema`
  - [NEW]
- `Schema`
  - [NEW]
- `Schema.active_slots`
  - [NEW]
- `Schema.unfilled_by_priority`
  - [NEW]

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 설계

의사코드 수준 흐름:

```
load_schema(knowledge_dir):
    파일 <knowledge_dir>/_intake_schema.md 없음        → None
    본문에서 첫 ```yaml fenced 블록 추출 실패          → None
    yaml.safe_load 예외                                → None
    최상위 intake_schema 키 또는 필수 키 누락          → None
        필수 키: version, opening_question, slots(리스트, 1개 이상)
    전부 통과                                          → Schema 객체
```

슬롯 선언 필드 (스키마 YAML 안):

- `id` — 슬롯 식별자 (필수)
- `label` — 사람이 읽는 이름 (필수)
- `required` — 필수/선택 (bool)
- `priority` — 낮을수록 먼저 소비 (int)
- `red_flag` — 레드플래그 표시 (bool, 기본 false)
- `when` — 조건부 활성 조건, `"slot_id=값"` 형식. 없으면 공통 슬롯
- `values` — enum 값 목록 (트랙 같은 선택형 슬롯용, 선택)
- `signals` — 발화 매칭 키워드. values 있는 슬롯은 값별 dict, 일반 슬롯은 list. fake 결정론 추출과 레드플래그 신호 감지가 이 필드를 쓴다
- `ask` — 질문 힌트 (모델 재량, 선택)

Schema 메서드:

- `active_slots(filled)` — 공통 슬롯 + `when` 조건이 filled 값으로 충족된 조건부 슬롯
- `unfilled_by_priority(filled, red_flag_first_ids)` — 활성이면서 미충족인 슬롯을 정렬: 레드플래그 신호 감지분 최상단, 나머지 priority 오름차순

원칙: 상담 등 도메인 문구는 엔진 코드에 일절 넣지 않는다 — 전부 스키마 데이터가 소유한다 (범용 엔진 invariant).

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 체크리스트

- [x] app/intake.py 스키마 파서·슬롯 모델 구현 (load_schema/active_slots/unfilled_by_priority)
- [x] tests/test_intake_schema.py — 부재·YAML 오류·필수 키 누락 → None 폴백 3케이스 테스트
- [x] tests/test_intake_schema.py — 조건부 활성(when)·우선순위 정렬·레드플래그 최상단 정렬 단위 테스트
- [x] pytest 통과 (기존 스위트 회귀 없음)

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 영향 범위

신규 모듈 + 신규 테스트만 — 기존 파일 무변경이라 회귀 표면이 없다. 이 phase 시점에는 아무도 load_schema를 호출하지 않는다(배선은 Phase 3). 롤백 = 두 파일 삭제.

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 검증

```bash
pytest tests/test_intake_schema.py -q  # edge: 부재·malformed YAML·필수 키 누락 → None 폴백 3케이스 포함
pytest -q
```

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 실행 결과

### 1회차 (2026-07-12 08:16 KST) — completed
**상태**: completed
**소요 시간**: 약 15분
**진행 모델**: Claude `sonnet`

#### 요약
`app/intake.py`에 스키마 파서(`load_schema`)와 슬롯 모델(`Slot`, `Schema`)을 신규 구현했다. 파일 부재·YAML fence 추출 실패·`yaml.safe_load` 예외·필수 키(version/opening_question/slots) 누락·슬롯별 필수 키(id/label) 누락까지 모든 실패 경로가 예외 없이 `None`으로 수렴한다. `Schema.active_slots`(when 조건부 활성)와 `Schema.unfilled_by_priority`(레드플래그 감지분 최상단 → priority 오름차순)도 설계대로 구현했다.

#### 변경 파일
- `app/intake.py` (new, +116/-0 lines)
- `tests/test_intake_schema.py` (new, +158/-0 lines)

#### 검증 결과
- [x] app/intake.py 스키마 파서·슬롯 모델 구현: 코드 리뷰 + 아래 테스트로 확인 -> pass
- [x] None 폴백 3+1케이스(부재·malformed YAML·필수 키 누락·yaml fence 없음): `pytest tests/test_intake_schema.py -q` -> pass (10 passed)
- [x] 조건부 활성(when)·우선순위 정렬·레드플래그 최상단 정렬 단위 테스트: 동일 명령 포함 -> pass
- [x] pytest 통과(기존 스위트 회귀 없음): `pytest -q` -> pass (52 passed, 1 warning — httpx2 deprecation, 기존부터 존재하던 무관한 경고)

#### 추가 발견사항
없음

#### 질문 / 결정 사항
없음
