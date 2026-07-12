# gui-uplift 결정 원장 (runtime decision ledger)

run `run-1783846772-92855` (2026-07-12)의 runtime decision packet을 태스크 문서에 연결한다.
원본 packet: `.phase/phase-run-decisions.jsonl` (runtime output — repo 커밋 대상 아님).

## 1. intake-panel-hidden-css-bug — followup_phase_fix (user)

- Phase 5 스모크 1회차(19/20)가 발견한 결함: `#intake-panel`이 `hidden` 속성에도
  데스크톱 폭(>860px)에서 CSS 캐스케이드로 계속 노출.
- 사용자 결정: `followup_phase_fix` — phase-add로 후속 phase 생성.
- 이행: Phase 6 커밋 `b0f63e7` (`static/style.css:466` `.intake-panel[hidden]{display:none}`),
  Phase 5 재검증 2회차 20/20 PASS (커밋 `9ab1ba8`).

## 2. visual-reference-approval — approved (user)

- 스크린샷 5장 vs `docs/design/gui-reference.png` 육안 대조.
- 레이아웃 구조 차이(모바일 단일 뷰 vs 데스크톱 2단)는 Phase 2~4 기결정 사항으로 재론 제외,
  톤·색상·컴포넌트 형태 일치를 사용자가 승인.

## 3. scope-violation-false-positive — no_revert (orchestrator)

- 증상: `phase_run_guard.py`가 Phase 5(1회차)·Phase 6·Phase 5(2회차) 가드 실행마다
  타 태스크의 사전 dirty 플래닝 파일 4건을 `scope_violation`으로 플래그 —
  `docs/planning/intake-slot-engine/checklist.md`,
  `docs/planning/lmwiki-chatbot-proto/checklist.md`,
  `docs/planning/lmwiki-chatbot-proto/decisions.md`,
  `docs/planning/lmwiki-chatbot-proto/spec-review.md`.
- 오탐 근거 (오케스트레이터 검증):
  - 4건 전부 mtime이 run 시작(17:59:32 KST) 이전 (09:21 / 09:16 당일, 22:56 전일).
  - `git diff 5e233ff8`(baseline_capture 스냅샷) 대비 내용 동일 — 이번 run의 어떤 워커도 미접촉.
  - edits ledger(`.phase/runs/<run-id>/phase-run-edits.log`)가 hook 미설치로 부재 →
    가드가 attribution 불가 시 보수적으로 플래그한 것.
- 처분: `no_revert` — 자동 revert 시 타 태스크의 미커밋 작업이 파괴되므로 미실행.
  worker 위반 아님으로 기록만 남김. 2·3차 가드 실행에서도 동일 처분 적용.
- 부수 기록: 같은 원인 계열로 task_schedule 게이트도 자기 run 마커(slug=RUN_ID)를
  타 run으로 오인해 block 반환 — 사용자 승인된 run임을 확인하고 `--override` 기록 후 진행.
  하네스 개선 후보는 최종 보고서 HarnessRecommendation 참조.
