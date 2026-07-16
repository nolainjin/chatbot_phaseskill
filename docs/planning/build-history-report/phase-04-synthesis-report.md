---
phase: 4
title: 종합 보고서 — 빌드 히스토리·문제와 수정·기억 대조
status: pending
depends_on: [1, 2, 3]
scope:
  - docs/2026-07-16_빌드-히스토리-회고.md
intervention_likely: false
intervention_reason: ""
executor: opus
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

# Phase 4: 종합 보고서 — 빌드 히스토리·문제와 수정·기억 대조

> **범위**: Docs (evidence 3종 종합 + 신규 md 1개)
> **난이도**: M
> **의존성**: Phase 1, 2, 3
> **영향 파일**: docs/2026-07-16_빌드-히스토리-회고.md [NEW]

## 배경

사용자가 요청한 최종 산출물. Phase 1~3의 evidence 문서 3종
(evidence-repo.md·evidence-claude.md·evidence-gjc.md)을 종합해 lmwiki-chatbot이
언제·어떻게 만들어졌고, 무엇이 문제였고, 어떻게 고쳐졌는지를 하나의 보고서로 쓴다.
사용자 기억 M1~M5(README 정의)는 사실로 전제하지 않고 실측 근거로 판정한다.
E2E 카탈로그 부재 — 문서 태스크로 E2E 비활성.

## 심볼 인벤토리

(없음)

## 설계

**쓰기 대상은 `docs/2026-07-16_빌드-히스토리-회고.md` 하나뿐이다.**
입력은 docs/planning/build-history-report/의 evidence 3종. 첫 단계에서 repo 가드 2줄 먼저 실행.

필수 섹션 6종 (헤딩 문자열 고정 — 검증 게이트가 grep):

1. `## 전체 타임라인` — 07-11 phase-intake부터 07-15 마지막 커밋까지 일자별 서사 + 커밋 근거
2. `## phase-skills 사용 이력` — 태스크 3개가 언제 어떤 스킬(phase-intake/init/run/add/finalization)로
   돌았는지, 재계획(a6baf1c)·재시작이 언제 왜 있었는지, 세션 경계와의 관계
3. `## 챗봇 아키텍처` — as-built 노트 기반: 파이프라인, "판단은 코드·표현은 모델" 원칙,
   LLM 백엔드 3종(fake/claude-cli/codex-cli), JSON→SQLite 저장, app/ 모듈 구성
4. `## 문제와 수정 이력` — 문제·오류 항목마다 **증상→원인→수정** 구조 + 커밋/세션/로그 근거
   (fix 커밋 계열, gjc 수정 문제 목록, 리밋·재시작 사건 포함)
5. `## 사용자 기억 대조` — M1~M5를 표로: | 클레임 | 판정 | 근거 |. 판정 어휘는
   확인/부분확인/반박/미확인 4종만. **M 태그와 판정은 같은 행에 쓴다** (게이트가 행 단위 grep).
6. `## 미확인·한계` — 로그로 닫지 못한 것, degrade된 소스, 기존 tracked planning 2파일의
   사적 경로 잔존(범위 밖 — 후속 정리 권고 1줄) 등을 정직하게 나열

작성 규율:

- evidence 3종에 없는 수치·사실을 새로 만들지 않는다. 부족하면 '미확인'으로 쓴다.
- evidence 문서와 수치·사실이 모순되지 않게 상호 대조한다.
- **소스 표기·리댁션 규약(README 정본) 준수**. `knowledge*/_persona.md`·`_tone.md` 파생
  사적 내용 인용 금지 — overlap 게이트가 기계 검증한다.

## 체크리스트

- [ ] 필수 섹션 6종(전체 타임라인/phase-skills 사용 이력/챗봇 아키텍처/문제와 수정 이력/사용자 기억 대조/미확인·한계)을 작성한다
- [ ] 문제·오류 항목마다 증상→원인→수정 구조와 커밋/세션/로그 근거를 기재한다
- [ ] M1~M5 각각에 판정(확인|부분확인|반박|미확인)과 근거 인용을 기재한다
- [ ] 소스 표기 규약을 준수하고 knowledge*/_persona.md·_tone.md 파생 사적 내용을 인용하지 않는다
- [ ] evidence 문서 3종과 수치·사실 모순이 없도록 상호 대조한다
- [ ] 기존 tracked docs/planning 2파일의 사적 경로 잔존(범위 밖)을 '미확인·한계'에 후속 권고로 기록한다

## 영향 범위

신규 md 1개 생성뿐. 코드·기존 문서 무변경. 롤백 = 파일 삭제.

## 검증

```bash
[ "$(git rev-list --max-parents=0 HEAD)" = "3076b54087ebd82c32f241c9ea92bfe2f24b47f0" ] || { echo "WRONG REPO: lmwiki-chatbot 레포 루트에서 실행하세요"; exit 1; }
test -f PHASE-SKILLS.md || { echo "WRONG CWD"; exit 1; }
R="docs/2026-07-16_빌드-히스토리-회고.md"
test -f "$R" || { echo "missing $R"; exit 1; }
for h in "전체 타임라인" "phase-skills 사용 이력" "챗봇 아키텍처" "문제와 수정 이력" "사용자 기억 대조" "미확인·한계"; do
  LC_ALL=C grep -aq "## $h" "$R" || { echo "missing section: $h"; exit 1; }
done
# edge: M1~M5 판정 태그가 같은 행에 없으면 실패 — 기억 클레임의 무판정 통과 차단
for m in M1 M2 M3 M4 M5; do
  LC_ALL=C grep -aqE "$m.*(확인|반박)" "$R" || { echo "missing verdict: $m"; exit 1; }
done
# edge: 사적 경로·식별자 재유입 시 실패 — 산출물 4개 전체, grep exit 2 오류도 실패 처리
for f in "$R" docs/planning/build-history-report/evidence-repo.md docs/planning/build-history-report/evidence-claude.md docs/planning/build-history-report/evidence-gjc.md; do
  test -f "$f" || { echo "missing $f"; exit 1; }
  LC_ALL=C grep -a -nE '/Users/|/Volumes/|var[/-]folders|jind[u]chan|부[부]공용' "$f"; rc=$?
  [ "$rc" -eq 1 ] || { echo "PRIVACY GATE FAIL(rc=$rc): $f"; exit 1; }
done
# edge: 사적 페르소나/보이스 파일의 10자+ 라인이 보고서에 등장하면 실패 — 사적 내용 재유입 차단
python3 - <<'PY'
import pathlib, sys
report = pathlib.Path("docs/2026-07-16_빌드-히스토리-회고.md").read_text(encoding="utf-8")
fails = []
for d in ("knowledge", "knowledge-alt"):
    for name in ("_persona.md", "_tone.md"):
        p = pathlib.Path(d) / name
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if len(s) >= 10 and s in report:
                fails.append(f"{p}: {s[:40]}")
if fails:
    print("PERSONA OVERLAP FAIL:\n" + "\n".join(fails))
    sys.exit(1)
PY
echo "PHASE4 VERIFY OK"
```
