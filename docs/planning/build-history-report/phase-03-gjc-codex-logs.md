---
phase: 3
title: 가재코드·Codex 로그 마이닝 — 영문 커밋 13개 구간 복원
status: pending
depends_on: []
scope:
  - docs/planning/build-history-report/evidence-gjc.md
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

# Phase 3: 가재코드·Codex 로그 마이닝 — 영문 커밋 13개 구간 복원

> **범위**: Docs (홈 디렉토리 로그 읽기 전용 조사 + 신규 md 1개)
> **난이도**: M
> **의존성**: 없음
> **영향 파일**: docs/planning/build-history-report/evidence-gjc.md [NEW]

## 배경

레포 마지막 구간(9d660a9~1929f4e, 07-13 22:32~07-15 00:45)은 영문 비컨벤셔널 커밋 13개로,
사용자 기억 M5("Claude 세션 한도 소진 후 코덱스 가재코드로 수정 마무리")에 대응하는 후보 구간이다.
가재코드(gjc) 활동 기록은 `~/.gjc/logs/`의 일자 로그(07-12~15는 .log.gz, 07-16만 평문 .log),
`~/.gjc/agent/`의 history.db·agent.db(WAL 모드, -wal/-shm 사이드카 실재), 그리고
`~/.codex/sessions/2026/07/`의 rollout에 남아 있다. E2E 카탈로그 부재 — 문서 태스크로 E2E 비활성.

## 심볼 인벤토리

(없음)

## 설계

**쓰기 대상은 `docs/planning/build-history-report/evidence-gjc.md` 하나뿐이다.**

수집 절차 (첫 단계에서 repo 가드 2줄 먼저 실행 — Phase 1과 동일):

1. **gjc 일자 로그**: `~/.gjc/logs/gjc.2026-07-{12,13,14,15}.log.gz`와 `gjc.2026-07-16.log`에서
   lmwiki 관련 활동을 추출한다. **gz 파일은 반드시 zgrep/zcat으로 처리한다** (plain grep은 gzip에서
   조용히 0건 — 금지). 선별 패턴은 부분문자열 `zgrep -ia 'lmwiki'` (lmwiki-chatbot·경로형 모두 매치).
   문서에 `gjc_log_files:` 목록을 실제 파일명 그대로(.log.gz 포함) 기재한다.
2. **agent DB (사본 조회)**: `~/.gjc/agent/`의 history.db·agent.db를 **-wal·-shm 사이드카와 함께**
   스크래치 디렉토리로 복사한 뒤 사본에서 읽기 전용 sqlite 조회로 lmwiki 관련 세션·프롬프트를 추출한다
   (메인 .db만 복사하면 WAL 미반영 stale 스냅샷 — 금지). 복사·조회가 실패하면 로그-only로 degrade하되
   **그 사실을 문서에 명시한다(침묵 금지)**.
3. **codex rollout**: `~/.codex/sessions/2026/07/{11..16}`에서 기계적 선별(grep, gz 혼재 대비 zgrep 병용)로
   lmwiki 언급 rollout 파일을 식별하고, 해당 파일만 정독한다.
4. **커밋×활동 매칭 표**: 영문 커밋 13개 각각을 gjc/codex 활동 시간대와 매칭한다 — 어떤 커밋이
   가재코드 산출인지, 커밋 직전 로그에 어떤 지시·수정이 있었는지.
5. **수정 문제 목록**: 가재코드가 고친 문제들(무엇을·왜·어떻게)을 커밋·로그 대응으로 정리한다.

**소스 표기·리댁션 규약(README 정본) 준수**: gjc 로그는 파일명만(`gjc.2026-07-14.log.gz`),
codex는 `codex 07/<일>/<파일명>` 표기. verbatim 인용 시 민감 스팬 `<path>`/`<user>`/`<vol>` 치환.

## 체크리스트

- [ ] gjc 일자 로그(07-12~16, gz는 zgrep/zcat)에서 lmwiki 활동을 추출하고 `gjc_log_files:` 목록을 실제 파일명 그대로 기재한다
- [ ] `$HOME/.gjc/agent/`의 history.db·agent.db를 wal·shm 사이드카와 함께 스크래치로 복사한 뒤 사본에서 읽기 전용 sqlite 조회한다 — 복사·조회 실패 시 로그-only degrade를 문서에 명시한다(침묵 금지)
- [ ] `$HOME/.codex/sessions/2026/07/11~16`에서 기계적 선별(zgrep 병용)로 lmwiki 언급 rollout을 식별하고 해당 파일만 정독한다
- [ ] 영문 커밋 13개(9d660a9~1929f4e)와 gjc/codex 활동 시간 매칭 표를 작성한다
- [ ] 가재코드가 수정한 문제 목록(무엇을·왜·어떻게)을 커밋·로그 대응으로 정리한다
- [ ] 소스 표기·리댁션 규약을 준수한다

## 영향 범위

신규 md 1개 생성뿐. gjc/codex 로그·DB는 읽기 전용(DB는 사본 조회). 롤백 = 파일 삭제.

## 검증

```bash
[ "$(git rev-list --max-parents=0 HEAD)" = "3076b54087ebd82c32f241c9ea92bfe2f24b47f0" ] || { echo "WRONG REPO: lmwiki-chatbot 레포 루트에서 실행하세요"; exit 1; }
test -f PHASE-SKILLS.md || { echo "WRONG CWD"; exit 1; }
F=docs/planning/build-history-report/evidence-gjc.md
test -f "$F" || { echo "missing $F"; exit 1; }
LC_ALL=C grep -aq 'gjc_log_files:' "$F" || { echo "gjc_log_files 목록 누락"; exit 1; }
# edge: 문서에 나열된 gjc 로그 파일명(.log.gz 실명)이 실존하지 않으면 실패 — 없는 로그 인용 차단
found=0
for f in $(LC_ALL=C grep -a -oE 'gjc\.2026-[0-9]{2}-[0-9]{2}\.log(\.gz)?' "$F" | sort -u); do
  test -f "$HOME/.gjc/logs/$f" || { echo "missing log: $f"; exit 1; }
  found=1
done
[ "$found" -eq 1 ] || { echo "로그 파일명 0건 인용"; exit 1; }
# edge: 사적 경로·식별자 재유입 시 실패 (grep exit 2 오류도 실패 처리)
LC_ALL=C grep -a -nE '/Users/|/Volumes/|var[/-]folders|jind[u]chan|부[부]공용' "$F"; rc=$?
[ "$rc" -eq 1 ] || { echo "PRIVACY GATE FAIL(rc=$rc)"; exit 1; }
echo "PHASE3 VERIFY OK"
```
