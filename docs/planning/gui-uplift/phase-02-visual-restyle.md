---
phase: 2
title: 비주얼 전면 리스타일 (딥틸 테마)
status: completed
depends_on: []
scope:
  - static/index.html
  - static/style.css
  - static/app.js
intervention_likely: false
intervention_reason: ""
executor: sonnet
load_bearing: "static/style.css 팔레트 교체 + static/app.js addMessage 타임스탬프 래퍼가 core — 나머지 마크업은 cosmetic"
e2e_refs: []
e2e_triggers: []
phase_context:
  baseline: "missing"
  adoption: "bootstrap"
  coverage: "standard"
  enforcement_during_run: "warn"
  materialize_at: "finalization"
---

# Phase 2: 비주얼 전면 리스타일 (딥틸 테마)

> **범위**: Frontend
> **난이도**: L
> **의존성**: 없음
> **영향 파일**: static/index.html, static/style.css, static/app.js

<!-- E2E 카탈로그(docs/e2e) 부재 — 카탈로그 갱신 전까지 E2E 비활성. Phase 5 로컬 브라우저 스모크가 대체. -->

## 배경

참조 이미지 docs/design/gui-reference.png 수준으로 GUI를 재스타일한다. 재활병원
의사 시연용 — 현행 베이지/그린 톤을 딥틸 테마로 전환하고 참조 이미지의 비주얼
요소 8종을 구현한다. 빌드 도구 없는 바닐라 3파일 구조 유지(파일 고치고 새로고침이
전부). 봇 말투·이모지는 _persona.md 소유 — GUI 크롬 텍스트만 다룬다.

## 심볼 인벤토리

- `addMessage` (메시지 li 생성 — 타임스탬프 래퍼 추가 지점)
  - 근거: static/app.js:26
- `showTyping` (타이핑 인디케이터 — 보존 대상)
  - 근거: static/app.js:40
- `renderIntake` (슬롯 패널 — 보존 대상)
  - 근거: static/app.js:82
- `.notice` (기존 고지 문구 — details 카드로 승격)
  - 근거: static/index.html:22
- `.message-user` / `.message-assistant` (비대칭 라운딩 기존 부분 구현)
  - 근거: static/style.css:147
- 개인정보 `<details>` 카드, 봇 아바타 SVG, 타임스탬프 렌더러, 원형 전송 아이콘, 하단 자물쇠 문구
  - [NEW]

## 설계

참조 이미지 8요소를 CSS 변수 교체 + 마크업 추가로 구현한다. 엔진·API 무접촉.

1. **딥틸 팔레트**: `:root` CSS 변수를 딥틸 계열(참조 이미지의 진한 청록 계열 헤더/
   유저 말풍선, 연한 민트 배경 톤)로 교체. 다크모드 `@media (prefers-color-scheme:
   dark)` 블록도 딥틸 기준으로 재정의 — 구 베이지 팔레트 값이 남지 않게.
2. **헤더 바**: 딥틸 배경 바에 제목 + 턴 카운터 배지. 기존 subtitle은 유지하거나
   카드 안으로 이동. 진행 바(#turn-progress)는 헤더 하단에 보존.
3. **봇 아바타**: 봇 메시지 왼쪽에 원형 아바타(inline SVG 로봇 — 외부 에셋 금지).
4. **말풍선 비대칭 라운딩**: 참조 이미지 수준으로 강화 — 봇은 왼쪽 위 모서리,
   유저는 오른쪽 아래 모서리 작은 라운딩.
5. **타임스탬프**: 각 메시지 아래 `toLocaleTimeString('ko-KR', {hour: 'numeric',
   minute: '2-digit'})` (예: "오전 10:30"). addMessage가 말풍선+타임스탬프를 감싸는
   래퍼를 만들되 `.message-user`/`.message-assistant` 클래스와 말풍선 본문
   textContent 규약은 유지 — fake 접미사 strip(app.js:136)·scrollIntoView·기존
   테스트와 충돌 방지.
6. **개인정보 접기 카드**: 기존 `.notice`를 `<details class="privacy-card">`로 승격.
   summary "응답 내용은 안전하게 보호됩니다" + 방패 아이콘(inline SVG), 본문에 기존
   고지 원문 "이 대화 내용은 서버에 저장됩니다." **보존**(문구 유실 금지 — 새 보안
   주장 문구를 지어내지 않는다).
7. **둥근 입력창 + 원형 전송 아이콘**: 전송 버튼을 원형 아이콘 버튼(inline SVG
   종이비행기)으로 — `aria-label="전송"` 유지(접근성).
8. **하단 자물쇠 문구**: 폼 아래 자물쇠 아이콘 + "응답 내용은 안전하게 보호됩니다"
   한 줄.

보존 대상(회귀 금지): 타이핑 인디케이터, 진행 바+턴 카운터, 슬롯 패널 스타일
(slot-filled/unfilled/next/redflag), status/error, disabled 상태, sr-only.

## 체크리스트

- [x] 딥틸 팔레트로 라이트 테마 CSS 변수 교체
- [x] 다크모드 @media 블록에 딥틸 팔레트 변수를 정의하고 구 팔레트 값이 남지 않는다
- [x] 상단 딥틸 헤더 바(제목 + 턴 카운터 배지) 구현
- [x] 봇 아바타(inline SVG)·말풍선 비대칭 라운딩·타임스탬프(ko-KR 오전/오후 h:mm) 구현
- [x] 기존 고지를 <details> 접기 카드로 승격 — "이 대화 내용은 서버에 저장됩니다" 원문 보존
- [x] 둥근 입력창 + 원형 전송 아이콘(aria-label 유지) + 하단 자물쇠 문구
- [x] 타이핑 인디케이터·진행 바·슬롯 패널·상태/에러·disabled 스타일이 개편 후에도 보존된다
- [x] .venv/bin/python -m pytest -q 통과

## 영향 범위

- static/ 3파일만 — 엔진·API·지식셋 무접촉.
- addMessage DOM 구조 변경이 유일한 동작 변경점 — .message 클래스·textContent 규약
  유지로 통제. 시각 최종 확인은 Phase 5 스크린샷.
- 롤백: git checkout static/ 으로 완전 복원.

## 검증

```bash
cd /path/to/chatbot_phaseskill
.venv/bin/python -m pytest -q
# edge: 개인정보 고지 문구 유실 차단 — 카드 승격 중 법적 고지가 사라지는 실패 경로 단언
grep -q "서버에 저장됩니다" static/index.html && echo "notice ok"
grep -q "<details" static/index.html && echo "details ok"
```

## 실행 결과

### 1회차 (2026-07-12 00:00 KST) — completed
**상태**: completed
**소요 시간**: 약 20분
**진행 모델**: Claude `sonnet`

#### 요약
static/ 3파일을 딥틸 테마로 전면 리스타일했다. CSS 변수 팔레트를 라이트/다크
모두 딥틸 계열로 교체하고, 헤더를 풀블리드 딥틸 바로 만들었으며, 봇 아바타·
비대칭 라운딩·타임스탬프·개인정보 접기 카드·원형 전송 버튼·하단 자물쇠 문구를
추가했다. addMessage는 avatar + bubble-col(말풍선+타임스탬프) 래퍼 구조로
바뀌었고, .message-user/.message-assistant 클래스와 textContent 규약은
그대로 유지해 기존 fake 접미사 strip·scrollIntoView 로직과 충돌하지 않는다.

#### 변경 파일
- `static/style.css` (modified, +165/-35 lines)
- `static/index.html` (modified, +29/-7 lines)
- `static/app.js` (modified, +42/-5 lines)

#### 검증 결과
- [x] .venv/bin/python -m pytest -q 통과: `81 passed, 1 warning in 1.79s`
- [x] 개인정보 고지 문구 유실 차단: `grep -q "서버에 저장됩니다" static/index.html` -> `notice ok`
- [x] details 카드 승격 확인: `grep -q "<details" static/index.html` -> `details ok`
- [x] app.js 문법 스모크: `node --check static/app.js` -> `app.js syntax ok`
- [x] style.css 중괄호 균형 스모크: 77쌍 일치 확인

#### 추가 발견사항
- static/index.html의 기존 하드코딩 인사말 `<li>`를 제거하고, 동일 문구를
  app.js `GREETING` 상수로 옮겨 `addMessage("assistant", GREETING)`로 초기
  렌더링하게 했다. 백엔드/`_persona.md`가 소유한 문구가 아니라(grep 결과
  app/knowledge 어디에도 없음) 순수 프런트엔드 정적 문구였고, 이렇게 하면
  addMessage 한 곳에서만 아바타+타임스탬프 마크업을 만들어 첫 인사말도
  일관된 비주얼을 갖는다. 동작 변경(첫 메시지가 JS 실행 후 렌더링)은 이
  앱이 애초에 JS 없이는 전혀 동작하지 않으므로 실질적 회귀는 없다고 판단.
- 정적 자산 캐시 버스팅 쿼리(`?v=`)를 기존 관행(과거 커밋에서 v=2 -> v=3로
  증가한 이력 확인)에 따라 v=3 -> v=4로 올렸다.
- Phase 5가 실제 브라우저 스크린샷으로 참조 이미지 대조를 최종 검증하므로
  Playwright 등 브라우저 렌더링 스모크는 이 phase에서 실행하지 않았다
  (환경에 playwright 미설치 확인, phase 설계상 Phase 5 소관).

#### 질문 / 결정 사항
none
