---
phase: 2
title: 상담 3-트랙 스키마 + 페르소나 소유권 정리
status: completed
depends_on: [1]
scope:
  - knowledge/_intake_schema.md
  - knowledge/_persona.md
intervention_likely: false
intervention_reason: ""
executor: sonnet
load_bearing: "`knowledge/_intake_schema.md` 신설이 핵심 — 3-트랙 슬롯 선언이 이후 모든 phase의 데이터 기반; _persona.md 정리는 소유권 정합용"
e2e_refs: []
e2e_triggers: []
phase_context:
  baseline: "missing"
  adoption: "bootstrap"
  coverage: "standard"
  enforcement_during_run: "warn"
  materialize_at: "finalization"
---

# Phase 2: 상담 3-트랙 스키마 + 페르소나 소유권 정리

> **범위**: 지식 데이터 (코드 무변경)
> **난이도**: S
> **의존성**: Phase 1
> **영향 파일**: `knowledge/_intake_schema.md` [NEW], `knowledge/_persona.md`

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 배경

엔진(Phase 1)이 읽을 실제 상담 접수면담 스키마를 기존 knowledge/ 셋에 얹는다. 트랙 3종(정서/관계/위기)과 슬롯 세부는 origin 지시대로 기존 지식 6종에서 도출한다. 동시에 `_persona.md`와의 소유권 충돌을 정리한다: 순서·항목은 스키마 소유, 태도·비밀보장·요약 형식은 페르소나 소유. critic 리뷰에서 확인된 함정 — 비밀보장 원칙·예외 안내가 현재 "면담 순서" 목록 1번 항목 안에만 있어(knowledge/_persona.md:8), 목록을 그냥 지우면 페르소나 소유 영역인 비밀보장 안내가 같이 사라진다. 별도 섹션으로 승격해 보존한다.

knowledge-alt/(커피)에는 아무것도 추가하지 않는다 — "스키마 없는 지식셋 = 기존 Q&A 폴백" 시연이 목적이므로.

E2E 카탈로그 부재 — e2e_refs 빈 값(사용자 승인 2026-07-12). 카탈로그 refresh 전까지 E2E 비활성.

## 심볼 인벤토리

- `load_documents`
  - 근거: app/knowledge.py:51
- `load_schema`
  - [NEW]

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 설계

스키마 내용 (기존 지식 6종 도출 근거 포함):

- 공통 슬롯:
  - `track` — enum(정서/관계/위기), 값별 signals (예: 정서=[우울, 불안, 잠], 관계=[남편, 부부, 가족, 갈등], 위기=[자해, 죽고 싶]). priority 최상위
  - `chief_complaint` — 호소 문제(방문 이유). opening_question은 접수-면접-질문지-구성.md:16 원문 "오늘 상담을 받으러 오신 이유가 무엇인가요?" 사용
  - `coping` — 대처 시도 / `support` — 지지체계 / `expectation` — 상담 기대 (접수-면접-질문지-구성.md 주요 영역 3~5)
- 조건부 슬롯 (`when: "track=값"`):
  - 정서 → 증상 시기·일상 영향 (접수-면접-질문지-구성.md "문제의 경과")
  - 관계 → 대상·기간
  - 위기 → 자해 계획·수단(`red_flag: true`)·시도 이력 (위기-상황-스크리닝.md 확인 항목 1·2)
- signals 키워드는 fake 결정론 추출과 Phase 6 e2e 4종 발화가 맞물리도록 선정 (예: "남편과 갈등 때문에 잠을 못 자요" → track=관계 + 정서 증상 슬롯 동시 매칭).

`_persona.md` 정리:

- 제거: "## 면담 순서" 1~5 목록 (순서·항목은 스키마·엔진 소유로 이관)
- 승격: 목록 1번에 있던 비밀보장 원칙·예외(즉각적 위해·학대 의심·법원 명령)를 `## 비밀보장 안내` 별도 섹션으로
- 유지: 제목 "접수 면담 봇 페르소나"(tests/test_intake.py:55 "접수 면담" 단언 보존), 역할 소개, `## 태도`, `## 접수 요약 형식`

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 체크리스트

- [x] knowledge/_intake_schema.md 작성 — 트랙 3종(정서/관계/위기)·공통 슬롯·조건부 슬롯·레드플래그·signals 선언, 기존 지식 6종과 정합
- [x] knowledge/_persona.md 소유권 정리 — 면담 순서 목록 제거, 태도·비밀보장·요약 형식 유지, '접수 면담' 문자열 보존
- [x] 비밀보장 원칙·예외 안내를 `## 비밀보장 안내` 별도 섹션으로 승격 유지 — 예외 열거(즉각적 위해·학대 의심·법원 명령) 보존
- [x] load_documents 검색 결과에 _intake_schema.md 미포함 확인
- [x] pytest 통과 (tests/test_intake.py 페르소나 단언 포함)

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 영향 범위

지식 데이터 2파일만 — 코드 무변경. `_` 예약 규칙(app/knowledge.py:59-61) 덕에 스키마 파일은 검색에 자연히 안 섞인다. 이 phase 커밋 후 Phase 3 배선 전까지는 페르소나의 면담 순서가 제거됐는데 슬롯 엔진은 미배선인 중간 상태 창이 존재 — 직렬 실행 전제로 수용(테스트는 전부 통과). 롤백 = _intake_schema.md 삭제 + _persona.md 복원.

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 검증

```bash
python3 -c "from app.intake import load_schema; s = load_schema('knowledge'); assert s is not None, '스키마 로드 실패'"
python3 -c "from app.knowledge import load_documents; names = [d.path.name for d in load_documents('knowledge')]; assert '_intake_schema.md' not in names"  # edge: 예약 파일이 Q&A 검색 대상에 섞이지 않음
grep -q '^## 비밀보장' knowledge/_persona.md && grep -q '예외' knowledge/_persona.md
pytest -q
```

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 실행 결과

### 1회차 (2026-07-12 08:27 KST) — completed
**상태**: completed
**소요 시간**: 약 15분
**진행 모델**: Claude `sonnet`

#### 요약
`knowledge/_intake_schema.md`를 신설해 트랙 3종(정서/관계/위기)·공통 슬롯 4종·트랙별 조건부 슬롯 4종(레드플래그 1종 포함)을 기존 지식 6종 근거와 함께 선언했다. `_persona.md`는 "## 면담 순서" 목록을 제거하고, 그 안에 있던 비밀보장 원칙·예외(즉각적 위해·학대 의심·법원 명령)를 "## 비밀보장 안내" 별도 섹션으로 승격해 소유권을 스키마(순서·항목)와 페르소나(태도·비밀보장·요약 형식)로 정리했다.

#### 변경 파일
- `knowledge/_intake_schema.md` (new, +68/-0 lines)
- `knowledge/_persona.md` (modified, +3/-9 lines)

#### 검증 결과
- [x] `load_schema('knowledge')` 스키마 로드 성공: `python3 -c "from app.intake import load_schema; s = load_schema('knowledge'); assert s is not None, '스키마 로드 실패'"` -> pass
- [x] `_intake_schema.md`가 `load_documents` 검색 대상에서 제외됨: `python3 -c "from app.knowledge import load_documents; names = [d.path.name for d in load_documents('knowledge')]; assert '_intake_schema.md' not in names"` -> pass
- [x] `_persona.md`에 비밀보장 섹션·예외 문구 존재: `grep -q '^## 비밀보장' knowledge/_persona.md && grep -q '예외' knowledge/_persona.md` -> pass
- [x] 전체 테스트 스위트 통과: `.venv/bin/python -m pytest -q` -> pass (52 passed)

#### 추가 발견사항
없음

#### 질문 / 결정 사항
없음
