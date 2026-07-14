---
phase: 6
title: intake-panel hidden CSS 오버라이드 수정
status: completed
depends_on: [4]
scope:
  - static/style.css
intervention_likely: false
intervention_reason: ""
executor: haiku
load_bearing: "static/style.css에 .intake-panel[hidden]{display:none} 1줄 추가가 core — author 규칙(.intake-panel{display:flex})이 UA 스타일시트의 [hidden]{display:none}을 캐스케이드에서 이겨버리는 근본 원인을 차단"
e2e_refs: []
e2e_triggers: []
phase_context:
  baseline: "missing"
  adoption: "bootstrap"
  coverage: "standard"
  enforcement_during_run: "warn"
  materialize_at: "finalization"
---

# Phase 6: intake-panel hidden CSS 오버라이드 수정

> **Scope**: Frontend
> **Difficulty**: XS
> **Dependencies**: Phase 4 (Phase 5는 needs_user 상태로 이 수정을 기다리는 중 — [5]로 걸면 상호 대기 교착이라 [4]로 지정)
> **Impact files**: static/style.css

## 배경

Phase 5 브라우저 스모크(1회차, 19/20)에서 발견된 결함의 근본 수정.
`#intake-panel`에 `hidden` 속성이 있어도 데스크톱 폭(>860px)에서 패널이 계속
노출된다. `.intake-panel { display: flex; ... }` author 규칙이 UA 스타일시트의
`[hidden] { display: none; }`보다 캐스케이드 우선순위가 높기 때문이다.
같은 파일의 `.stepper[hidden]`(139줄)·`.chips[hidden]`(365줄)는 이미 동일 패턴의
오버라이드를 갖고 있고 `.intake-panel`(454줄)만 빠져 있다.

증상 2곳, 원인 1곳:
- knowledge-alt 스왑 회귀: 빈 문진 패널 노출 (Phase 5 체크리스트 fail 항목)
- knowledge 세트 초기 화면: 첫 응답 전 빈 패널 노출 (05·01번 스크린샷)

사용자 결정: `DECISION_REQUEST id=intake-panel-hidden-css-bug` → `followup_phase_fix`
(2026-07-12, `.phase/phase-run-decisions.jsonl` 기록).

## 심볼 인벤토리

- `static/style.css` 139줄 `.stepper[hidden] { display: none; }` — 복제할 기존 패턴
- `static/style.css` 365줄 `.chips[hidden] { display: none; }` — 복제할 기존 패턴
- `static/style.css` 454~464줄 `.intake-panel { ... display: flex; ... }` — 오버라이드 부재 지점
- `static/app.js` — `hidden` 속성 토글 주체 (이 phase에서 무수정, 참조만)

## 설계

수정은 CSS 1줄. 의사코드:

```
IF 요소가 .intake-panel AND hidden 속성 보유
THEN display: none   # 속성 셀렉터가 붙어 specificity가 base 규칙보다 높아 위치 무관하게 이김
```

`.intake-panel` 블록(454줄) 직후에 `.intake-panel[hidden] { display: none; }`을
추가한다. `.stepper[hidden]`·`.chips[hidden]`와 동일 패턴. JS(app.js)는 이미
`hidden` 속성을 올바르게 토글하고 있으므로 무수정.

과차단 위험 없음: 규칙은 `hidden` 속성이 DOM에 있을 때만 발동하고, 패널이
보여야 하는 시점에는 app.js가 `hidden`을 제거한다.

## 체크리스트

- [x] `static/style.css`에 `.intake-panel[hidden] { display: none; }` 규칙 추가 — 기존 `.stepper[hidden]`·`.chips[hidden]`와 동일 패턴, `.intake-panel` 블록 인근
- [x] 정적 단언 통과 — 규칙 존재 + `display: none` 포함 (아래 검증 python 블록)
- [x] `.venv/bin/python -m pytest -q` 전체 통과 — CSS 단독 수정 회귀 게이트

## 영향 범위

- `static/style.css` 단일 파일, 순수 additive 1줄. 롤백은 해당 줄 삭제.
- `/api/chat` 계약·서버 코드·app.js 무접촉.
- 브라우저 레벨 최종 확인(>860px 실제 렌더에서 hidden 시 미노출 + knowledge 세트
  정상 노출 유지)은 **Phase 5 재검증**(스모크 재실행, 20/20 목표)이 담당한다 —
  이 phase의 정적 단언은 규칙 존재까지만 보증.

## 검증

```bash
cd /path/to/chatbot_phaseskill
grep -n '\.intake-panel\[hidden\]' static/style.css
# edge: 오버라이드 부재 회귀 경로 — 규칙이 없거나 display:none이 빠지면 assert 실패
python3 - <<'PY'
import re
css = open('static/style.css', encoding='utf-8').read()
m = re.search(r'\.intake-panel\[hidden\]\s*\{[^}]*display:\s*none', css)
assert m, "missing .intake-panel[hidden]{display:none} override"
print("override OK")
PY
.venv/bin/python -m pytest -q
```

## 실행 결과

### 1회차 (2026-07-12 10:45 KST) — completed
**상태**: completed
**소요 시간**: 약 2분
**진행 모델**: Claude Haiku 4.5

#### 요약
`.intake-panel[hidden] { display: none; }` 규칙을 `static/style.css` 465줄에 추가하여 UA 스타일시트의 `[hidden]{display:none}`이 author 규칙의 `display:flex`에 패배하는 캐스케이드 우선순위 문제를 해결했다. 정적 단언과 전체 테스트 스위트(81/81 pass) 모두 통과.

#### 변경 파일
- `static/style.css` (modified, +4/-0 lines)

#### 검증 결과
- [x] grep: `grep -n '\.intake-panel\[hidden\]' static/style.css` → 466줄에서 규칙 발견
- [x] python3 assert: `\.intake-panel\[hidden\]\s*\{[^}]*display:\s*none` 정규식 매치 → "override OK"
- [x] pytest: `.venv/bin/python -m pytest -q` → 81 passed

#### 추가 발견사항
없음

#### 질문 / 결정 사항
없음
