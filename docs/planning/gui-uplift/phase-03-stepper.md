---
phase: 3
title: 3단계 스테퍼 (intake 파생)
status: completed
depends_on: [1, 2]
scope:
  - static/index.html
  - static/style.css
  - static/app.js
intervention_likely: false
intervention_reason: ""
executor: sonnet
load_bearing: "static/app.js의 intakeSchemaActive 게이트 + window.lmwikiDeriveStep 순수 함수가 core — 스테퍼 CSS는 cosmetic"
e2e_refs: []
e2e_triggers: []
phase_context:
  baseline: "missing"
  adoption: "bootstrap"
  coverage: "standard"
  enforcement_during_run: "warn"
  materialize_at: "finalization"
---

# Phase 3: 3단계 스테퍼 (intake 파생)

> **범위**: Frontend
> **난이도**: M
> **의존성**: Phase 1(config 프로브), Phase 2(헤더·레이아웃 기반)
> **영향 파일**: static/index.html, static/app.js

<!-- E2E 카탈로그(docs/e2e) 부재 — 카탈로그 갱신 전까지 E2E 비활성. Phase 5 로컬 브라우저 스모크가 대체. -->

## 배경

참조 이미지의 3단계 스테퍼(①도움 필요 영역 ②상황 파악 ③상담 준비)를 intake 필드
{filled, unfilled}에서 파생해 표시한다. knowledge-alt(스키마 없는 지식셋)에서는
미노출 — Phase 1의 GET /api/config가 게이트. 데스크톱은 기존 사이드 패널 유지,
모바일은 스테퍼가 패널을 대체한다.

## 심볼 인벤토리

- `renderIntake` (intake 수신 지점 — 스테퍼 갱신 훅)
  - 근거: static/app.js:82
- `#intake-panel` (모바일에서 숨길 사이드 패널)
  - 근거: static/index.html:42
- `@media (max-width: 860px)` (모바일 분기 기존 지점)
  - 근거: static/style.css:345
- `_intake_state` unfilled[]={id,label,red_flag} (파생 입력 계약)
  - 근거: app/chat.py:121
- `#stepper` 마크업, `intakeSchemaActive` 플래그, `window.lmwikiDeriveStep`, config fetch
  - [NEW]

## 설계

1. **마크업**: index.html에 `id="stepper"` 요소를 `hidden` 기본값으로 추가 — 3단계
   (①도움 필요 영역 ②상황 파악 ③상담 준비), 원형 번호 + 라벨 + 연결선(참조 이미지).
2. **게이트**: app.js에 공유 플래그 `intakeSchemaActive`(기본 **false**). 로드 시
   `fetch("/api/config")`가 성공적으로 `{intake_schema: true}`를 반환할 때만 true로
   승격하고 스테퍼 unhide. 기본값이 false이므로 fetch 실패/비정상 응답은 본질적으로
   fail-closed(knowledge-alt와 동일 상태·undefined 접근 없음) — `console.warn` 기록,
   채팅 기능 무영향. 이 플래그는 Phase 4 칩도 같이 쓴다.
3. **파생 규칙** — DOM 무접근 순수 함수로 분리하고 window에 노출(결정적 검증 훅):

   ```
   window.lmwikiDeriveStep(unfilledIds):   # unfilledIds: intake.unfilled의 id 배열
       'track' ∈ U           → 1           # 도움 필요 영역 (track 채움 전)
       U − {'expectation'} ≠ ∅ → 2          # 상황 파악 (공통·조건부 슬롯 진행 중)
       그 외                  → 3           # 상담 준비 (expectation만 남음 또는 완료)
   ```

   최초(응답 수신 전)는 step 1 활성. renderIntake마다 재계산해 활성 단계 갱신.
   주의: fake 추출기는 signals 없는 슬롯(chief_complaint)을 채우지 않아 **fake
   라이브 플로우에서 ③ 도달 불가** — ③ 검증은 Phase 5에서 이 순수 함수에 대한
   합성 입력 단언으로 수행한다(실모드는 스키마 계약상 도달 가능).
4. **반응형**: 데스크톱 — 스테퍼 + 기존 사이드 패널 공존. 모바일(≤860px) —
   `#intake-panel` 숨김, 스테퍼가 진행 표시를 대체.

## 체크리스트

- [x] index.html에 id="stepper" 마크업 추가 — hidden 기본값(스왑 회귀 기본 미노출)
- [x] intakeSchemaActive 기본 false — config fetch 실패/비정상 응답 시 스테퍼 미노출 유지(fail-closed)하고 console.warn을 남기며 채팅 동작은 무영향이다
- [x] 파생 규칙을 window.lmwikiDeriveStep 순수 함수(DOM 무접근)로 노출 — 3분기 구현
- [x] renderIntake마다 활성 단계 갱신, 초기 상태는 step 1
- [x] 모바일(≤860px)에서 #intake-panel 숨김·스테퍼 표시, 데스크톱은 패널 유지
- [x] .venv/bin/python -m pytest -q 통과

## 영향 범위

- static/ 3파일만. Phase 1 엔드포인트를 소비(계약: {"intake_schema": bool}).
- 스테퍼는 표시 전용 — 대화 흐름·API 호출 무영향. fail-closed라 최악의 실패도
  "스테퍼 안 보임"으로 수렴.
- 롤백: git checkout static/ 으로 복원.

## 검증

```bash
cd /path/to/chatbot_phaseskill
.venv/bin/python -m pytest -q
# edge: 스테퍼 기본 미노출(스왑 회귀 정적 단언) — hidden 속성 없이 렌더되는 실패 경로 차단
grep -Eq '<[a-z]+[^>]*id="stepper"[^>]*hidden' static/index.html && echo "stepper hidden ok"
# edge: 결정적 검증 훅 존재 — Phase 5 합성 단언의 전제
grep -q "lmwikiDeriveStep" static/app.js && echo "hook ok"
```

## 실행 결과

### 1회차 (2026-07-12 17:40 KST) — completed
**상태**: completed
**소요 시간**: 약 20분
**진행 모델**: Claude `sonnet`

#### 요약
스테퍼 마크업·게이트·파생 함수·반응형 분기를 static 3파일에 구현했다. `#stepper`는
`hidden` 기본값으로 추가했고, `intakeSchemaActive` 플래그(기본 false)가
`/api/config` 성공 응답({"intake_schema": true})에서만 승격되어 스테퍼를
드러낸다. `window.lmwikiDeriveStep` 순수 함수가 track/expectation 아이디 기준
3분기를 처리하고, `renderIntake`마다 재계산해 활성 단계를 갱신한다. 모바일
(≤860px)에서는 `#intake-panel`을 완전히 숨기고 스테퍼가 진행 표시를 대체한다.

#### 변경 파일
- `static/index.html` (modified, +18/-2 lines)
- `static/style.css` (modified, +57/-11 lines)
- `static/app.js` (modified, +48/-0 lines)

#### 검증 결과
- [x] .venv/bin/python -m pytest -q 통과: `.venv/bin/python -m pytest -q` -> pass (81 passed)
- [x] 스테퍼 기본 미노출(스왑 회귀 정적 단언): `grep -Eq '<[a-z]+[^>]*id="stepper"[^>]*hidden' static/index.html` -> "stepper hidden ok"
- [x] 결정적 검증 훅 존재: `grep -q "lmwikiDeriveStep" static/app.js` -> "hook ok"
- [x] (추가 자체 점검) `window.lmwikiDeriveStep` 런타임 스모크: DOM 스텁 위에서 app.js를 그대로 로드해 6개 케이스(track 포함/공존, chief_complaint만, coping+expectation, expectation만, 빈 배열)를 단언 — 전부 설계된 3분기 규칙대로 통과

#### 추가 발견사항
- NOTES: `static/style.css`의 기존 `.intake-panel { display: flex; ... }` (Phase 2 도입, 369번째 줄 부근)는 `hidden` 속성에 대한 `[hidden]` 오버라이드 규칙이 없어, CSS 캐스케이드 규칙상(author 일반 선언이 UA 일반 선언을 항상 이긴다) HTML `hidden` 속성이 display 계산에서 무력화될 수 있는 잠재 이슈로 보인다. 이번 Phase 스코프(스테퍼 신설 + 모바일 미디어쿼리)에는 영향이 없어 손대지 않았고, 신규 `#stepper`에는 `.stepper[hidden] { display: none; }`을 명시적으로 추가해 동일 함정을 피했다. Phase 2 영역 후속 점검 시 참고.
- `static/style.css`의 `@media (max-width: 520px)` 블록에 남아있는 `.intake-panel { border-radius: 0; box-shadow: none; }`은 이제 상위 860px 분기에서 `display: none`으로 항상 가려지므로 도달 불가능한 죽은 CSS다. 기능상 무해하고 이번 체크리스트 범위 밖이라 제거하지 않았다.
- 참조 이미지의 정확한 배치 좌표 지정이 없어, 스테퍼는 헤더 바로 아래·턴 진행바 위에 배치했다(데스크톱 상단 진행 표시로 자연스러운 위치). Phase 5 브라우저 스모크에서 시각 확인 권장.

#### 질문 / 결정 사항
없음
