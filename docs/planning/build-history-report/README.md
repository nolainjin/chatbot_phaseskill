# build-history-report — lmwiki-chatbot 빌드 히스토리·오류·수정 조사 보고서

## 배경

lmwiki-chatbot은 2026-07-11 phase-intake로 시작해 2026-07-15까지 66커밋으로 만들어졌다.
그 과정에서 phase-skills 태스크 3개(lmwiki-chatbot-proto → intake-slot-engine → gui-uplift)가 돌았고,
마지막 구간(07-13 밤~07-15)은 가재코드(gjc)가 이어받아 영문 커밋 13개를 남겼다.

이 태스크는 그 전 과정을 실측으로 재구성한다:

1. 초기부터 어떤 작업을 했는지 (git·planning 아티팩트)
2. phase-skills를 언제 어떻게 썼는지 (dev 세션 로그)
3. 챗봇이 어떤 방식으로 만들어졌는지 (as-built: README·app/ 실측)
4. 문제·오류와 그 수정 방법 (Claude 세션 + gjc/codex 로그 발굴)

최종 산출물은 단일 보고서 `docs/2026-07-16_빌드-히스토리-회고.md`.

## 사용자 기억 클레임 (판정 대상 — 사실로 전제하지 않는다)

- **M1**: phase-init부터 finalization까지 한 세션에서 연속 진행했다 (스킬 단위 세션 재시작 없이).
- **M2**: Fable 모델로 작업하다 5시간 리밋을 약 10회 소진했다.
- **M3**: 재진행 때 phase-add로 추가 요청을 넣었으나 문제가 있어 스킬을 처음부터 하나씩 다시 시작했다.
- **M4**: 결과물이 원하는 것이 아니어서 추가 세팅을 넣다가 Claude 세션 한도를 모두 썼다.
- **M5**: 이후 코덱스 가재코드(gjc)로 수정을 마무리했다.

각 클레임은 보고서에서 판정(확인|부분확인|반박|미확인) + 근거와 함께 다룬다.

## 실행 방법

**반드시 lmwiki-chatbot 레포 루트에서 실행한다.** 모든 phase의 검증 블록이
root-commit 고정 가드로 레포 정체성을 확인하며, 다른 저장소에서 돌리면 즉시 실패한다.

```bash
/phase-run build-history-report
```

Phase 1·2·3은 스코프가 서로소라 병렬 가능, Phase 4가 셋을 종합한다.

## 소스 표기·리댁션 규약 (정본)

산출물 4개(md) 전부에 적용된다. 검증 게이트가 기계적으로 강제한다.

1. **절대경로 금지** — 홈 디렉토리·볼륨·임시 디렉토리 절대경로, 사용자명 리터럴, 볼륨명 리터럴을 쓰지 않는다.
2. **표기법**:
   - Claude dev 세션 → `세션 <uuid 앞8자>` (예: `세션 eb364437`), 라인 인용은 `세션 <uuid8>#L<n>`
   - 챗봇 런타임 CLI 호출 디렉토리 → `lmwiki-cli-<suffix>`
   - gjc 로그 → 실제 파일명 그대로 (예: `gjc.2026-07-14.log.gz`)
   - codex rollout → `codex 07/<일>/<파일명>`
   - 위치 설명이 필요하면 `~/.claude/projects/…`, `~/.gjc/logs/…` 일반형만 허용
3. **리댁션** — 로그·에러 메시지를 verbatim 인용할 때 민감 스팬은 플레이스홀더로 치환:
   경로 → `<path>`, 사용자명 → `<user>`, 볼륨명 → `<vol>`. 커밋 해시·메시지 본문·판정에 필요한
   내용은 마스킹 후 그대로 인용 가능하다.
4. **사적 페르소나 금지** — `knowledge*/_persona.md`·`knowledge*/_tone.md`에서 파생된 사적 내용을
   보고서에 인용하지 않는다 (10자 이상 라인 overlap 게이트로 강제).

근거: HEAD 커밋 1929f4e("Remove private local paths from docs")가 세운 레포 위생 규율 유지.

## E2E

`docs/e2e/` 카탈로그 부재 + 문서 조사 태스크라 E2E 무관. 전 phase `e2e_refs`/`e2e_triggers` 빈 값.
카탈로그가 생기면 `/phase-e2e-init` 후 재매칭 가능하나 이 태스크에는 불필요.

## 알려진 한계 (태스크 범위 밖)

- 기존 tracked 파일 2곳(docs/planning/lmwiki-chatbot-proto/intake.md, spec-review.md)에
  사적 경로가 이미 잔존한다. 이 태스크는 신규 산출물만 게이트하며, 기존 파일 정리는
  보고서 '미확인·한계' 섹션에 후속 권고로 기록한다.

## 관련 문서

- [checklist](./checklist.md) · [spec-review](./spec-review.md)
