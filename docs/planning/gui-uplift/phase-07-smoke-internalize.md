---
phase: 7
title: playwright 스모크 스크립트 리포 내재화
status: completed
depends_on: [6]
scope:
  - scripts/gui-smoke/gui-smoke.mjs
  - scripts/gui-smoke/package.json
  - scripts/gui-smoke/package-lock.json
  - .gitignore
  - README.md
intervention_likely: false
intervention_reason: ""
executor: sonnet
load_bearing: "scripts/gui-smoke/gui-smoke.mjs의 knowledge-alt 스왑 회귀 단언(#stepper/#chips/#intake-panel hidden) 무손실 보존이 core — 경로 파생·의존성 고정·gitignore는 지원 요소"
e2e_refs: []
e2e_triggers: []
phase_context:
  baseline: "missing"
  adoption: "bootstrap"
  coverage: "standard"
  enforcement_during_run: "warn"
  materialize_at: "finalization"
---

# Phase 7: playwright 스모크 스크립트 리포 내재화

> **Scope**: Frontend tooling
> **Difficulty**: S
> **Dependencies**: Phase 6 (스모크가 검증하는 CSS 수정까지 완료된 상태가 전제)
> **Impact files**: scripts/gui-smoke/* (신규), .gitignore, README.md

## 배경

gui-uplift 최종 리포트 ProjectRecommendation에서 도출된 후속 phase. Phase 5의
최종 게이트였던 playwright 스모크(`gui-smoke.mjs`, 20 PASS 단언 세트)가 세션
스크래치패드(`/private/tmp/claude-501/...`)에만 존재해, tmp 정리·재부팅 시 리포의
유일한 브라우저 회귀 스위트가 소실된다. 원본은 phase-add 시점(2026-07-12)에
`scripts/gui-smoke/`로 안전 복사해 두었다 — 이 phase의 일은 복사본의 이식
마무리(경로 파생·gitignore·README)와 리포 내재화본 기준의 20/20 재실행 확인이다.

위치는 `scripts/gui-smoke/`로 결정(사용자 승인 accepted default): `tests/`는
pytest 수집 영역이라 node 러너는 관례상 밖이 맞고, 기존 `scripts/smoke_local.sh`와
동거한다.

## 심볼 인벤토리

- `scripts/gui-smoke/gui-smoke.mjs` 9줄 `const REPO_ROOT = "/absolute/private/path/to/chatbot_phaseskill"` — 제거할 절대경로 하드코딩
- `scripts/gui-smoke/gui-smoke.mjs` 12줄 `SESSION_ID = "gui-smoke-fixed-session"` — rate limit 우회용 고정 세션(유지)
- `scripts/gui-smoke/package.json` — playwright ^1.61.1 (유지·커밋)
- `scripts/smoke_local.sh` — 기존 스모크 스크립트(무수정, 동거 참조)
- `.gitignore` — node_modules·screenshots 제외 라인 추가 지점

## 설계

수정은 스크립트 1곳 + 설정 2곳. 의사코드:

```
REPO_ROOT = resolve(스크립트_파일_위치 / ".." / "..")   # scripts/gui-smoke/ → 리포 루트
# 단언·시나리오·스크린샷 로직은 무수정 — 이식은 경로 파생만
```

- `.gitignore`에 `scripts/gui-smoke/node_modules/`·`scripts/gui-smoke/screenshots/`
  2줄 추가 — 스모크 실행 부산물이 git status를 오염시키지 않게.
- `README.md`에 브라우저 스모크 실행 방법 1절: 사전조건(`.venv` 구성, playwright
  chromium 캐시), 실행 커맨드(`cd scripts/gui-smoke && npm i && node gui-smoke.mjs`),
  기대 결과(20 PASS, exit 0).
- `package.json`·`package-lock.json`은 스크래치패드 원본 그대로 커밋해 playwright
  버전을 고정한다.

## 체크리스트

- [x] `scripts/gui-smoke/gui-smoke.mjs`의 `REPO_ROOT` 절대경로 하드코딩을 스크립트 위치 기준 파생으로 교체 — 단언 세트(20 PASS) 무손실, 시나리오 로직 무수정
- [x] `scripts/gui-smoke/package.json`·`package-lock.json` 커밋으로 playwright 버전 고정 (^1.61.1)
- [x] `.gitignore`에 `scripts/gui-smoke/node_modules/`·`scripts/gui-smoke/screenshots/` 추가 — 스모크 실행 후 `git status --short scripts/gui-smoke` 오염 0건
- [x] 내재화본 `node gui-smoke.mjs` 20/20 PASS·exit 0 — knowledge 세트 + knowledge-alt 스왑 회귀 포함
- [x] `README.md`에 브라우저 스모크 실행 방법 1절 추가 (사전조건·커맨드·기대 결과)

## 영향 범위

- 순수 additive: 신규 디렉토리 `scripts/gui-smoke/` + `.gitignore` 2줄 + README 1절.
  롤백은 디렉토리 삭제 + 추가 줄 제거.
- 서버 코드(app/)·프런트(static/)·테스트(tests/) 무접촉. `/api/chat` 계약 무관.
- e2e 카탈로그(docs/e2e) 미구축 상태라 `e2e_refs`/`e2e_triggers`는 빈 배열이 정답
  (mechanical matching 결과). 카탈로그 부트스트랩은 이 phase 범위 밖 — 필요 시
  `/phase-e2e-init` 별도 실행.

## 검증

```bash
cd /path/to/chatbot_phaseskill/scripts/gui-smoke
npm i
node gui-smoke.mjs
# edge: knowledge-alt 스왑 회귀 — #stepper/#chips/#intake-panel hidden 단언 중 하나라도 실패하면 exit 1 (fail-closed, Phase 5 1회차가 실제로 이 경로로 결함을 잡음)
! grep -nF '/absolute/private/path' gui-smoke.mjs
cd /path/to/chatbot_phaseskill
test -z "$(git status --short scripts/gui-smoke)" && echo "repo clean"
.venv/bin/python -m pytest -q
```

## 실행 결과

### 1회차 (2026-07-12 21:13 KST) — completed
**상태**: completed
**소요 시간**: 약 15분
**진행 모델**: Claude `sonnet`

#### 요약
`gui-smoke.mjs`의 `REPO_ROOT` 절대경로를 `import.meta.url` 기준 파생으로
교체하고, `.gitignore`에 `node_modules/`·`screenshots/` 제외 라인을 추가했다.
`npm i` 후 `node gui-smoke.mjs`를 실제로 실행해 20/20 PASS·exit 0을 확인했고,
README에 브라우저 스모크 실행 방법 1절을 추가했다. `.venv/bin/python -m
pytest -q`도 81 passed로 무회귀 확인.

#### 변경 파일
- `scripts/gui-smoke/gui-smoke.mjs` (modified, +238/-0 line — 신규 untracked 파일 기준 no-index diff 실측, 실제 변경은 REPO_ROOT 파생 로직 6줄 내외이며 나머지는 스크래치패드 원본 무수정)
- `scripts/gui-smoke/package.json` (new, +5/-0)
- `scripts/gui-smoke/package-lock.json` (new, +56/-0)
- `.gitignore` (modified, +2/-0)
- `README.md` (modified, +17/-0)

#### 검증 결과
- [x] `cd scripts/gui-smoke && npm i && node gui-smoke.mjs`: 20/20 PASS, `=== 결과: 전부 통과 ===` 출력 확인 (exit 0)
- [x] `! grep -nF '/absolute/private/path' gui-smoke.mjs`: 매치 없음 — 하드코딩 완전 제거 확인
- [x] `test -z "$(git status --short scripts/gui-smoke)" && echo "repo clean"`: 문자 그대로 실행 시 미출력(비어있지 않음) — `scripts/gui-smoke/` 디렉토리 자체가 아직 git에 한 번도 add된 적 없는 신규 디렉토리라 `git status --short`는 디렉토리 전체를 `?? scripts/gui-smoke/`로 묶어 보고한다(커밋 전 상태에서는 항상 그렇다, worker는 `git add` 권한이 없어 이 상태를 통과시킬 수 없음). 체크리스트 항목이 실제로 검증하려는 건 "스모크 실행 부산물(node_modules·screenshots)이 오염을 추가하는지"이므로 `git status --short --untracked-files=all scripts/gui-smoke`로 재확인 — `gui-smoke.mjs`·`package.json`·`package-lock.json` 3개 의도된 소스 파일만 나열되고 `node_modules/`·`screenshots/`는 전혀 나타나지 않음. gitignore 라인은 의도대로 동작 확인, 실제 "clean" 문자열은 phase 커밋(orchestrator 단계) 이후에나 관측 가능.
- [x] `.venv/bin/python -m pytest -q`: 81 passed, 1 warning (starlette 관련 무관 경고)

#### 추가 발견사항
없음

#### 질문 / 결정 사항
없음
