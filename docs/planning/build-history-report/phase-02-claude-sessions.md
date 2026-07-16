---
phase: 2
title: Claude 세션 로그 마이닝 — dev 세션 3개 + 런타임 CLI 호출 정량화
status: pending
depends_on: []
scope:
  - docs/planning/build-history-report/evidence-claude.md
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

# Phase 2: Claude 세션 로그 마이닝 — dev 세션 3개 + 런타임 CLI 호출 정량화

> **범위**: Docs (홈 디렉토리 로그 읽기 전용 조사 + 신규 md 1개)
> **난이도**: M
> **의존성**: 없음
> **영향 파일**: docs/planning/build-history-report/evidence-claude.md [NEW]

## 배경

Claude Code 쪽 개발 대화는 `~/.claude/projects/-Volumes------worknote-lmwiki-chatbot/`의
dev 세션 JSONL 3개(각 ~120KB)에 남아 있다. 별도로 챗봇 자체가 claude CLI를 LLM 백엔드로 호출한
런타임 흔적(`lmwiki-cli-*` 프로젝트 디렉토리, 실측 ~276개)이 있다 — 이는 5시간 리밋 소진(M2)의
유력 원인 후보다. 이 phase는 사용자 기억 M1~M5 판정의 Claude 측 근거를 수집한다.
E2E 카탈로그 부재 — 문서 태스크로 E2E 비활성.

## 심볼 인벤토리

(없음)

## 설계

**쓰기 대상은 `docs/planning/build-history-report/evidence-claude.md` 하나뿐이다.**

수집 절차 (첫 단계에서 repo 가드 2줄 먼저 실행 — Phase 1과 동일):

1. **dev 세션 3개 정독** (LLM 정독은 이 3개 한정): `~/.claude/projects/-Volumes------worknote-lmwiki-chatbot/*.jsonl`
   각각에 대해 — 시작/종료 시각, 사용자 지시 시퀀스(무엇을 시켰나), phase 스킬 호출 흔적
   (phase-intake/phase-init/phase-run/phase-add/phase-finalization), 에러·리밋·재시작·모델 관련 이벤트를
   시간순으로 기록한다. 세션은 `세션 <uuid 앞8자>` 표기, 라인 인용은 `세션 <uuid8>#L<n>`.
2. **교차 스캔(기계적)**: `~/.claude/projects` 전체에서 2026-07-10~16 기간에 lmwiki를 언급한 세션을
   bash로만 스캔한다(`grep -l`, gz는 zgrep; 목록·카운트만). LLM 정독으로 확장하지 않는다.
   신규 dev 세션이 4개 이상 발견되면 최신 3개만 추가 정독하고 나머지는 목록·크기만 기재 후 '미확인' 표기.
3. **런타임 CLI 호출 정량화**: `lmwiki-cli-*` 디렉토리 총수와 날짜 분포(디렉토리 mtime 기준)를 집계하고
   `runtime_cli_dirs: <n>` 라인과 측정시각을 기재한다. 개별 디렉토리는 `lmwiki-cli-<suffix>`로만 표기.
4. **리밋 이벤트**: 5시간 리밋·세션 한도·rate limit·모델 전환(Fable 등) 관련 이벤트를 세션 로그에서 찾아
   목록화한다. 정확한 횟수를 셀 수 없으면 "확인된 것만 N건, 전수 미확인"으로 정직하게 쓴다.
5. **M1~M5 근거 인용**: 각 기억 클레임을 지지/반박하는 대목을 `세션 <uuid8>#L<n>` 표기로 모은다.

**소스 표기·리댁션 규약(README 정본) 준수**: 절대경로·사용자명·볼륨명 금지. 로그 verbatim 인용 시
민감 스팬은 `<path>`/`<user>`/`<vol>` 치환.

## 체크리스트

- [ ] dev 세션 JSONL 3개를 정독해 세션별 시각·사용자 지시 시퀀스·phase 스킬 호출·에러/리밋/재시작 이벤트를 기록한다
- [ ] `$HOME/.claude/projects` 전체를 기계적 bash 스캔(grep -l 목록·카운트, gz 파일은 zgrep)으로 2026-07-10~16 기간 lmwiki 언급 세션을 교차 확인한다 — 신규 dev 세션 4개 이상 발견 시 최신 3개만 추가 정독하고 나머지는 목록·크기만 기재 후 '미확인' 표기
- [ ] lmwiki-cli-* 런타임 호출 디렉토리를 정량화해 `runtime_cli_dirs: <n>`·측정시각·날짜 분포를 기재한다
- [ ] 리밋·세션 한도 관련 이벤트(5시간 리밋, 세션 한도, 모델 전환)를 목록화한다
- [ ] M1~M5 대조용 근거를 `세션 <uuid 앞8자>` 표기로 인용한다
- [ ] 소스 표기·리댁션 규약을 준수한다

## 영향 범위

신규 md 1개 생성뿐. 홈 디렉토리 로그는 읽기 전용. 롤백 = 파일 삭제.

## 검증

```bash
[ "$(git rev-list --max-parents=0 HEAD)" = "3076b54087ebd82c32f241c9ea92bfe2f24b47f0" ] || { echo "WRONG REPO: lmwiki-chatbot 레포 루트에서 실행하세요"; exit 1; }
test -f PHASE-SKILLS.md || { echo "WRONG CWD"; exit 1; }
F=docs/planning/build-history-report/evidence-claude.md
test -f "$F" || { echo "missing $F"; exit 1; }
LC_ALL=C grep -aq 'runtime_cli_dirs: ' "$F" || { echo "runtime_cli_dirs 라인 누락"; exit 1; }
# edge: 문서에 인용된 세션 uuid가 실존하지 않으면 실패 — 없는 소스 인용 차단
for u in $(LC_ALL=C grep -a -oE '세션 [0-9a-f]{8}' "$F" | awk '{print $2}' | sort -u); do
  ls "$HOME/.claude/projects/-Volumes------worknote-lmwiki-chatbot/$u"*.jsonl >/dev/null 2>&1 || { echo "unknown session: $u"; exit 1; }
done
# edge: runtime_cli_dirs 단조-유계 대조(문서값>=200, 실측>=문서값, 증가폭<=300) — 저quote·날조 차단
doc_n=$(LC_ALL=C grep -a -oE 'runtime_cli_dirs: [0-9]+' "$F" | head -1 | LC_ALL=C grep -a -oE '[0-9]+')
live_n=$(ls -d "$HOME/.claude/projects/"*lmwiki-cli* 2>/dev/null | wc -l | tr -d ' ')
[ -n "$doc_n" ] && [ "$doc_n" -ge 200 ] && [ "$live_n" -ge "$doc_n" ] && [ $((live_n - doc_n)) -le 300 ] || { echo "runtime_cli_dirs out of bounds: doc=$doc_n live=$live_n"; exit 1; }
# edge: 사적 경로·식별자 재유입 시 실패 (grep exit 2 오류도 실패 처리)
LC_ALL=C grep -a -nE '/Users/|/Volumes/|var[/-]folders|jind[u]chan|부[부]공용' "$F"; rc=$?
[ "$rc" -eq 1 ] || { echo "PRIVACY GATE FAIL(rc=$rc)"; exit 1; }
echo "PHASE2 VERIFY OK"
```
