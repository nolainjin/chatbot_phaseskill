---
phase: 1
title: 레포 증거 수집 — git 타임라인·planning 아티팩트·as-built 아키텍처
status: pending
depends_on: []
scope:
  - docs/planning/build-history-report/evidence-repo.md
intervention_likely: false
intervention_reason: ""
executor: sonnet
load_bearing: ""
e2e_refs: []
e2e_triggers: []
phase_context:
  baseline: "missing"
  adoption: "defer"
  coverage: "minimal"
  enforcement_during_run: "warn"
  materialize_at: "never"
---

# Phase 1: 레포 증거 수집 — git 타임라인·planning 아티팩트·as-built 아키텍처

> **범위**: Docs (읽기 전용 조사 + 신규 md 1개)
> **난이도**: M
> **의존성**: 없음
> **영향 파일**: docs/planning/build-history-report/evidence-repo.md [NEW]

## 배경

lmwiki-chatbot 레포 안에 이미 남아 있는 1차 증거(git 히스토리 66커밋, phase-skills planning 태스크 3개,
.phase/final-reports 3건, receipts/)를 구조화된 타임라인 노트로 정리한다. 이 노트는 Phase 4 종합 보고서의
"전체 타임라인"·"phase-skills 사용 이력"·"챗봇 아키텍처" 섹션의 근거가 된다.
E2E 카탈로그 부재 — 문서 태스크로 E2E 비활성.

## 심볼 인벤토리

(없음)

## 설계

**쓰기 대상은 `docs/planning/build-history-report/evidence-repo.md` 하나뿐이다.** 나머지는 전부 읽기 전용.

수집 절차 (증거 수집 첫 단계에서 아래 repo 가드 2줄을 먼저 실행한다):

```
[ "$(git rev-list --max-parents=0 HEAD)" = "3076b54087ebd82c32f241c9ea92bfe2f24b47f0" ] || exit 1
test -f PHASE-SKILLS.md || exit 1
```

1. `git log --format='%h|%ad|%s' --date=format:'%m-%d %H:%M'` 전량으로 일자별 타임라인 표를 만든다.
   문서 상단에 `total_commits: <n>` 라인을 기재한다 — n은 `git rev-list --count 1929f4ec4abeb4dd9d9362bb3cea4156c230bca6` 실측값.
2. `docs/planning/{lmwiki-chatbot-proto,intake-slot-engine,gui-uplift}/`의 checklist.md·spec-review.md·
   decisions.md·purpose-gate.md(있으면 intake.md·origin.md)를 읽고 태스크별로: phase 구성(개수·제목),
   완료 상태, 주요 결정, 재검토 이력을 요약한다.
3. 재계획 사건(a6baf1c: intake open questions 답변 반영 + Phase 1-2 실행 산출물 리셋)과
   fix 커밋 계열(e2047df·b0f63e7·dbab06d·7078549·3f76eb2·4c9da8c, feat이지만 결함 수정 포함인 6d62432)을
   커밋 메시지 + `git show --stat`으로 정리한다 — 각각 무엇이 문제였고 무엇을 바꿨는지.
4. `.phase/final-reports/` 3건과 `receipts/`(collect_usage.py, phase-00 receipt)를 요약한다.
5. 영문 커밋 구간(9d660a9~1929f4e, 13커밋, 07-13 22:32~07-15 00:45)을 별도 구간으로 표시한다
   — 이 구간은 Phase 3(gjc 로그)와의 대조 지점이다.
6. as-built 아키텍처 노트: README.md의 처리 파이프라인·설계 원칙("판단은 코드, 표현은 모델")·
   LLM 백엔드 3종(fake/claude-cli/codex-cli)·JSON→SQLite 저장 구조를 `app/` 실제 모듈 목록
   (`ls app/*.py`)과 대조해 "## as-built 아키텍처" 헤딩 아래 기재한다. `docs/design/`도 참조.

**소스 표기·리댁션 규약(README 정본)을 준수한다**: 절대경로·사용자명·볼륨명 리터럴 금지.
기존 planning 파일을 인용할 때 사적 경로가 포함돼 있으면 `<path>`/`<user>`/`<vol>`로 치환한다.

## 체크리스트

- [ ] git 전체 타임라인 표(해시·일시·제목)를 작성하고 `total_commits: <실측수>` 라인을 기재한다
- [ ] docs/planning 3개 태스크(lmwiki-chatbot-proto·intake-slot-engine·gui-uplift)의 phase 구성·완료 상태·주요 결정을 태스크별로 요약한다
- [ ] 재계획 사건(a6baf1c)과 fix 커밋 계열(e2047df·b0f63e7·dbab06d·7078549·3f76eb2·4c9da8c·6d62432)의 문제·수정 내용을 정리한다
- [ ] .phase/final-reports 3건과 receipts/ 수집물을 요약한다
- [ ] 영문 커밋 13개 구간(9d660a9~1929f4e)을 별도 구간으로 표기한다
- [ ] as-built 아키텍처 노트를 README.md 파이프라인·설계원칙과 app/ 모듈 실측 대조로 작성한다
- [ ] 소스 표기·리댁션 규약을 준수한다 — 절대경로·사용자명·볼륨명 미기재

## 영향 범위

신규 md 1개 생성뿐. 코드·기존 문서 무변경. 롤백 = 파일 삭제.

## 검증

```bash
[ "$(git rev-list --max-parents=0 HEAD)" = "3076b54087ebd82c32f241c9ea92bfe2f24b47f0" ] || { echo "WRONG REPO: lmwiki-chatbot 레포 루트에서 실행하세요"; exit 1; }
test -f PHASE-SKILLS.md || { echo "WRONG CWD"; exit 1; }
F=docs/planning/build-history-report/evidence-repo.md
test -f "$F" || { echo "missing $F"; exit 1; }
LC_ALL=C grep -aq "a6baf1c" "$F" || { echo "재계획 커밋 미기재"; exit 1; }
LC_ALL=C grep -aq "as-built" "$F" || { echo "as-built 아키텍처 노트 누락"; exit 1; }
# edge: 문서 기재 total_commits와 고정 커밋(1929f4e) 기준 실측 불일치 시 실패 — 수치 날조 차단
doc_n=$(LC_ALL=C grep -a -oE 'total_commits: [0-9]+' "$F" | head -1 | LC_ALL=C grep -a -oE '[0-9]+')
real_n=$(git rev-list --count 1929f4ec4abeb4dd9d9362bb3cea4156c230bca6)
[ -n "$doc_n" ] && [ "$doc_n" -eq "$real_n" ] || { echo "total_commits mismatch: doc=$doc_n real=$real_n"; exit 1; }
# edge: 사적 경로·식별자 재유입 시 실패 (grep exit 2 오류도 실패 처리)
LC_ALL=C grep -a -nE '/Users/|/Volumes/|var[/-]folders|jind[u]chan|부[부]공용' "$F"; rc=$?
[ "$rc" -eq 1 ] || { echo "PRIVACY GATE FAIL(rc=$rc)"; exit 1; }
echo "PHASE1 VERIFY OK"
```
