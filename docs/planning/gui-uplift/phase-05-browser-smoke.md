---
phase: 5
title: 브라우저 스모크 + 스왑 회귀 + 참조 대조
status: completed
depends_on: [4]
scope:
  - docs/planning/gui-uplift/phase-05-browser-smoke.md
intervention_likely: true
intervention_reason: "스크린샷과 참조 이미지(gui-reference.png) 육안 대조는 사용자 확인이 최종 판정"
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

# Phase 5: 브라우저 스모크 + 스왑 회귀 + 참조 대조

> **범위**: Frontend (검증 전용 — 리포 코드 무수정)
> **난이도**: M
> **의존성**: Phase 4 (전체 GUI 완성 후)
> **영향 파일**: 없음 (스모크 스크립트는 워커 스크래치패드에 생성)

<!-- E2E 카탈로그(docs/e2e) 부재 — 카탈로그 갱신 전까지 E2E 비활성. 이 phase의 playwright 스모크가 스왑 회귀·브라우저 검증을 대체. -->

## 배경

Phase 2~4는 브라우저 전용 증상(레이아웃·타임스탬프 렌더·스테퍼 전환·칩 동작)을
갖는다 — pytest로는 닫히지 않아 실브라우저 스모크가 필요하다. playwright는
~/.claude 캐시의 chromium-1228 + 스크래치패드 npm i playwright로 구동(직전 세션
검증된 방법). rate limit(IP당 신규 세션 5개/시간, 디스크 영속) 때문에 sessionStorage
lmwiki_session_id를 고정값으로 재사용한다.

## 심볼 인벤토리

- `window.lmwikiDeriveStep` (Phase 3 산출 — 합성 단언 대상)
  - [NEW]
- `#stepper` / `#chips` (Phase 3·4 산출 — 노출 상태 단언 대상)
  - [NEW]
- `gui-smoke.mjs` (이 phase에서 스크래치패드에 작성하는 스모크 스크립트)
  - [NEW]

## 설계

스크래치패드 작업 디렉토리에서 `npm i playwright`(chromium-1228 캐시 재사용) 후
`gui-smoke.mjs` 하나로 아래 시나리오를 순차 실행한다. 단언 실패 시 exit≠0.

1. **knowledge 세트** — `MODEL=fake KNOWLEDGE_DIR=knowledge .venv/bin/python -m
   uvicorn app.main:app` 기동. `page.addInitScript`로 sessionStorage
   lmwiki_session_id 고정값 주입.
   - 초기 화면: 칩 4종·스테퍼(① 활성)·개인정보 카드·자물쇠 문구 visible 단언 →
     데스크톱(1280px)·모바일(390px) 스크린샷.
   - 칩(예: 수면) 클릭: 유저 말풍선+타임스탬프 렌더, 봇 응답 수신, 칩 행 제거,
     스테퍼 ② 활성, 사이드 패널 갱신 단언 → 스크린샷.
   - 2~3턴 추가 진행(예: "가족과 갈등이 있어요") 후 패널·타임스탬프·아바타 렌더
     확인 → 스크린샷.
2. **스테퍼 3상태 합성 단언** — `page.evaluate`로 `window.lmwikiDeriveStep` 호출:
   `['track','chief_complaint']→1`, `['chief_complaint','expectation']→2`,
   `['expectation']→3`, `[]→3`. (fake 추출기는 signals 없는 chief_complaint를
   못 채워 라이브 ③ 도달 불가 — 합성 단언이 ③을 결정적으로 커버.)
3. **knowledge-alt 스왑 회귀** — `KNOWLEDGE_DIR=knowledge-alt`로 재기동:
   `#stepper`/`#chips`/`#intake-panel` 전부 visible=false 단언 + 스크린샷.
4. 스크린샷 전부를 사용자에게 전달(SendUserFile) — 참조 이미지
   docs/design/gui-reference.png와 육안 대조는 사용자 최종 확인.

리포 코드는 건드리지 않는다. 발견된 결함은 수정하지 말고 checklist에 실패 기록 후
needs_user 또는 해당 phase 재작업으로 에스컬레이션.

## 체크리스트

- [x] knowledge 데스크톱/모바일 스크린샷 세트 산출(초기·칩 클릭 후·진행 중)
- [x] 스테퍼 파생 3상태 합성 단언 통과(라이브 ①→② 전환 단언 포함)
- [x] knowledge-alt에서 #stepper/#chips/#intake-panel 미노출 단언 통과
- [x] sessionStorage lmwiki_session_id를 고정값으로 주입해 전 시나리오에서 재사용한다(rate limit 회피)
- [x] 스크린샷 사용자 전달 — 참조 이미지 대조 확인 요청

## 영향 범위

- 리포 무수정 — 스모크 스크립트·node_modules는 스크래치패드에만 생성.
- 서버는 로컬 2회 기동(knowledge/knowledge-alt) — 포트 충돌 시 대체 포트 사용.
- 실패 시 영향: 해당 GUI phase 재작업 신호일 뿐 코드 롤백 불필요.

## 검증

```bash
# 작업은 워커 스크래치패드에서 수행(리포 오염 금지). chromium-1228은 ~/.claude 캐시 재사용.
# cd <스크래치패드 작업 디렉토리>
npm i playwright
node gui-smoke.mjs
# edge: knowledge-alt 스왑 회귀 구간 — #stepper/#chips/#intake-panel visible=false 단언 실패 시 exit 1
```

## 실행 결과

### 1회차 (2026-07-12 18:08 KST) — needs_user
**상태**: needs_user
**소요 시간**: 약 25분
**진행 모델**: Claude `sonnet`

#### 요약
스크래치패드(`/private/tmp/.../scratchpad/gui-smoke`)에 `npm i playwright`(chromium-1228
캐시 재사용, 재다운로드 없음)로 `gui-smoke.mjs`를 작성해 실행했다. knowledge 세트 시나리오(초기
화면 4요소·데스크톱/모바일 스크린샷·칩 클릭 라이브 ①→②전환·2~3턴 진행)와 스테퍼 파생 4종 합성
단언은 전부 통과했다. 그러나 knowledge-alt 스왑 회귀 구간에서 `#intake-panel`이 `hidden` 속성이
있는데도 데스크톱 폭(1280px)에서 계속 노출되는 **진짜 결함**을 발견했다 — 리포는 무수정 원칙대로
건드리지 않고 체크리스트에 실패로 기록했다. 스크린샷 5장은 SendUserFile로 전달 완료, 참조 이미지
대조 확인과 결함 처리 방향 결정을 요청한다.

**결함 상세**: `static/style.css`의 `.stepper[hidden]{display:none}`(139줄)·`.chips[hidden]{display:none}`
(365줄)와 달리 `.intake-panel`(454줄)에는 `[hidden]` 오버라이드가 없다. `.intake-panel{display:flex}`
같은 일반 author 규칙이 UA 스타일시트의 `[hidden]{display:none}`보다 캐스케이드 우선순위가 높아,
`hidden` 속성이 DOM에 있어도 860px 초과 폭에서는 무시된다(860px 이하는 `@media`에서 별도로
`.intake-panel{display:none}`을 강제하므로 모바일 스크린샷(02번)에는 증상이 없었다). 이 결함은
knowledge-alt 스왑 회귀뿐 아니라 knowledge 세트 초기 화면(01번 스크린샷)에서도 첫 응답 전에 빈
패널이 노출되는 형태로 이미 나타나 있다(체크리스트 항목엔 없어 실패로 카운트하지 않았으나 육안
대조 시 참고 바람).

#### 변경 파일
- 없음 — 리포 코드 무수정(검증 전용 phase). 스모크 스크립트·screenshots는 워커 스크래치패드에만 존재
  (PHASE_FILE 자체의 상태/체크리스트/실행 결과 기록은 통상적인 phase-worker 자기기록이라 별도
  라인 수 실측 대상에서 제외).

#### 검증 결과
- [x] npm i playwright: 캐시 재사용(chromium-1228), 재다운로드 없이 2초 내 완료 -> pass
- [x] node gui-smoke.mjs — knowledge 세트 초기 화면 4요소(칩4종·스테퍼①·개인정보카드·자물쇠문구) visible -> pass
- [x] node gui-smoke.mjs — 데스크톱/모바일 스크린샷 2장 산출 -> pass
- [x] node gui-smoke.mjs — 칩 클릭: 유저 말풍선+타임스탬프, 봇 응답, 칩 제거, 스테퍼①→② 전환, 패널 갱신 -> pass
- [x] node gui-smoke.mjs — 2~3턴 추가 진행: 타임스탬프 7/7, 아바타 4개 렌더 -> pass
- [x] node gui-smoke.mjs — 스테퍼 파생 4종 합성 단언(`lmwikiDeriveStep`) -> pass (4/4)
- [ ] node gui-smoke.mjs — knowledge-alt 스왑: `#stepper`/`#chips` hidden -> pass, `#intake-panel` hidden -> **fail**
- 종합: `node gui-smoke.mjs` exit code 1 (19 PASS / 1 FAIL) — 스크립트 자체는 결함을 정확히
  검출한 정상 동작이며, 실패 원인은 앱 코드(static/style.css) 결함.

#### 추가 발견사항
- `#intake-panel` CSS 결함(위 요약 참조) — `static/style.css` 454~464줄에 `.intake-panel[hidden] { display: none; }`
  오버라이드 규칙 부재. `.stepper[hidden]`/`.chips[hidden]`와 동일 패턴으로 1줄 추가하면 해결될
  것으로 보이나, 이 phase는 리포 무수정이 전제라 직접 고치지 않았다.

#### 질문 / 결정 사항

1. **참조 이미지 육안 대조 (최종 승인)** — SendUserFile로 전달한 스크린샷 5장
   (01-initial-desktop, 02-initial-mobile, 03-after-chip-desktop, 04-after-turns-desktop,
   05-knowledge-alt-desktop)을 `docs/design/gui-reference.png`와 대조해 GUI 업리프트를
   최종 승인할지 확인 바란다. 참고로 참조 이미지는 모바일 프레임 단일 뷰(2열 큰 아이콘 칩 +
   "상담 시작하기" 버튼)이고, 현재 구현은 데스크톱 2단(채팅+사이드 패널) 레이아웃에 1행 4개
   pill형 칩으로 구성 — 레이아웃 구조 차이는 Phase 2~4에서 이미 결정된 사항이라 재론하지 않고,
   최종 톤·색상·컴포넌트 형태 일치 여부만 판단해 주시면 된다.

```yaml
DECISION_REQUEST:
  id: intake-panel-hidden-css-bug
  phase: 5
  blocking: true
  question: "#intake-panel이 hidden 속성에도 불구하고 데스크톱 폭(>860px)에서 CSS 캐스케이드로
    계속 노출되는 결함을 어떻게 처리할까요?"
  recommended: followup_phase_fix
  options:
    - followup_phase_fix
    - fix_now_scope_expand
    - accept_known_issue
  needs_research: false
  evidence:
    - "static/style.css 139줄 .stepper[hidden]{display:none}, 365줄 .chips[hidden]{display:none}는
      있으나 454~464줄 .intake-panel에는 [hidden] 오버라이드가 없음."
    - "05-knowledge-alt-desktop.png: knowledge-alt 스왑에서도 빈 문진 패널이 노출됨(hidden 속성은
      DOM에 존재하나 렌더링에서 무시)."
    - "01-initial-desktop.png: knowledge 세트 초기 화면에서도 첫 응답 전 빈 패널이 노출됨(동일 근본
      원인, 체크리스트 비대상)."
  note: "followup_phase_fix = phase-add로 static/style.css에 1줄 추가하는 후속 phase 생성 후
    Phase 5 재검증. fix_now_scope_expand = 지금 이 phase의 scope를 static/style.css까지
    넓혀 즉시 1줄 수정(리포 무수정 원칙과 상충하므로 비권장). accept_known_issue = 결함을
    현 상태로 수용하고 다음 라운드로 미룸."
```

### 2회차 (2026-07-12 19:06 KST) — completed

**상태**: completed
**소요 시간**: 약 10분
**진행 모델**: Claude `sonnet`

#### 요약

1회차에서 실패했던 `#intake-panel` hidden 단언은 Phase 6(커밋 `b0f63e7`,
`static/style.css` 466줄 `.intake-panel[hidden]{display:none}` 추가)에서 근본 원인이
수정됐다. 이번 회차는 리포 코드를 건드리지 않고 1회차와 동일한 스크래치패드 환경
(`/private/tmp/.../scratchpad/gui-smoke/`, chromium-1228 캐시 재사용)에서
`node gui-smoke.mjs`를 그대로 재실행해 재검증만 수행했다. 결과 20/20 PASS, exit 0으로
전 항목 통과. knowledge 세트 초기 화면(01-initial-desktop.png)도 재캡처해 확인한 결과
첫 응답 전 빈 문진 패널이 더는 노출되지 않는다 — 체크리스트 비대상 항목이었지만
1회차에서 지적한 동일 근본 원인이 함께 해소됐음을 확인했다. 참조 이미지 육안 대조는
1회차에서 이미 사용자 승인(decision id=visual-reference-approval)을 받았으므로
재요청하지 않는다.

#### 변경 파일

- 없음 — 리포 코드 무수정(검증 전용 phase). PHASE_FILE 자체의 상태/체크리스트/실행
  결과 기록만 갱신(통상적인 phase-worker 자기기록이라 라인 수 실측 대상에서 제외).

#### 검증 결과

- [x] npm i playwright: 스크래치패드 환경 재사용, 재설치 불필요(1회차 산출물 그대로) -> pass
- [x] node gui-smoke.mjs — knowledge 세트 초기 화면 4요소 visible -> pass
- [x] node gui-smoke.mjs — 데스크톱/모바일 스크린샷 2장 산출 -> pass
- [x] node gui-smoke.mjs — 칩 클릭: 유저 말풍선+타임스탬프, 봇 응답, 칩 제거, 스테퍼①→②
  전환, 패널 갱신 -> pass
- [x] node gui-smoke.mjs — 2~3턴 추가 진행: 타임스탬프 7/7, 아바타 4개 렌더 -> pass
- [x] node gui-smoke.mjs — 스테퍼 파생 4종 합성 단언(`lmwikiDeriveStep`) -> pass (4/4)
- [x] node gui-smoke.mjs — knowledge-alt 스왑: `#stepper`/`#chips`/`#intake-panel` 전부
  hidden -> pass
- 종합: `node gui-smoke.mjs` exit code 0 (20 PASS / 0 FAIL) — 1회차에서 발견한 진짜
  결함(Phase 6 커밋 b0f63e7)이 해소됐음을 확인.

#### 추가 발견사항

없음 — 1회차에서 보고한 `#intake-panel` CSS 결함은 Phase 6에서 이미 해결됨.

#### 질문 / 결정 사항

없음 — 참조 이미지 육안 대조는 1회차에서 이미 사용자 승인 완료
(decision id=visual-reference-approval, `.phase/phase-run-decisions.jsonl` 기록),
재요청하지 않는다.
