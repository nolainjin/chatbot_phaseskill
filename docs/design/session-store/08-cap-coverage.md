# 세션 스토어 분리 — Phase 8: CAP 커버리지 대조와 문서 인덱스

> 이 문서는 **감사**다. `capabilities.md`(CAP 원장) 49건이 Phase 1~7 문서 7건에 실제로
> 담겼는지 전건 대조하며, 대조 자체가 축소 협상은 아니다. 미충족·부분충족 CAP 은 기본적으로
> 소유 페이즈의 결함이며, 이 문서가 그 결함을 발견해도 스스로 판단을 좁히지 않는다 —
> `capabilities.md` 는 이 문서가 직접 쓰지 않는다(원장 갱신 경로는 `/phase-intake` 추출과
> `/phase-init` CCL 체크포인트뿐).
>
> 입력 문서: [01](./01-current-state.md)·[02](./02-policy-decisions.md)·[03](./03-history-restore.md)·
> [04](./04-interface.md)·[05](./05-invariants.md)·[06](./06-migration-plan.md)·
> [07](./07-compatibility-review.md), [capabilities.md](../../planning/session-store-multiworker/capabilities.md).

---

## 1. CAP01–CAP49 전건 커버리지 표

"이름만 묶여 있고 실제 산출물이 없는" 경우를 부분충족으로 표시한다.

| CAP | 담당 문서 | 해당 절 | 충족 여부 |
|-----|-----------|---------|-----------|
| CAP01 | 04-interface.md, 05-invariants.md | 04 전체(연산 집합·`data/sessions.db` 단일 매체), 05 §2(I1 — 읽기/쓰기 경로 양쪽 논증) | 충족 |
| CAP02 | 05-invariants.md | §4(I3) — §4.1 에서 반례 v1~v3 로 I1 과 독립임을 먼저 증명 | 충족 |
| CAP03 | 07-compatibility-review.md | §4(Docker 배포 형상 적합성 — 볼륨·cwd·컨테이너 수명주기) | 충족 |
| CAP04 | 01~07 각 문서 서두, 06-migration-plan.md | 각 문서 "코드는 한 줄도 바뀌지 않는다" 명시 + 06 §16(만들지 않은 것 목록) | 충족 (검증: CODE-UNCHANGED-OK) |
| CAP05 | 01-current-state.md | 전체 | 충족 |
| CAP06 | 02-policy-decisions.md | 전체 — D01~D05 확정 답(옵션 나열 아님) | 충족 |
| CAP07 | 04-interface.md | 전체 — 연산 집합·스키마·오류 코드 | 충족 |
| CAP08 | 06-migration-plan.md | 서두 "아무것도 실행하지 않는다" + §16 | 충족 |
| CAP09 | 01~07 각 문서 + 검증 게이트 | 검증 `CODE-UNCHANGED-OK` / `TASK-LEVEL-CODE-UNCHANGED-OK`(§3) | 충족 |
| CAP10 | 04-interface.md, 06-migration-plan.md | 04 §1~§2(SessionStore 연산·스키마), 06 S1~S5(이행 절차) | 충족 |
| CAP11 | 04-interface.md | §2.2(6개 값 필드 저장 배치표 — `history`·`last_question_slot_id` 포함) | 충족 |
| CAP12 | 05-invariants.md | §3(I2 — 401 분기 도달불가) | 충족 |
| CAP13 | 05-invariants.md | §3.3, §4(I3 — 재시작 케이스 별도 논증) | 충족 |
| CAP14 | 05-invariants.md | §6.4~§6.6(I5-B — 10턴 캡 워커 횡단 정확성) | 충족 |
| CAP15 | 05-invariants.md | §6.1~§6.3(I5-A — 성질 P1, 승자 토큰) | 충족 |
| CAP16 | 02-policy-decisions.md, 04-interface.md | 02 D04, 04 §7.3(`rate_*` 테이블) | 충족 |
| CAP17 | 02-policy-decisions.md | D04 근거 — 트랜잭션 경계에 의한 "정확한 시행" 논증(대략 시행 대체 금지 명시) | 충족 |
| CAP18 | 02-policy-decisions.md | D04 근거 — 동일 논증이 전역 일일 캡에도 적용됨을 명시 | 충족 |
| CAP19 | 06-migration-plan.md | §10.2 (2)·(3) — `Dockerfile`·`ratelimit.py` 주석 갱신을 S8 필수 작업으로 명시 | 충족 |
| CAP20 | 04-interface.md, 05-invariants.md | 04 §6(대화 쓰기 임계 구역), 05 §5(I4 — "스토어 이전만으로는 해결 안 됨"부터 논증) | 충족 |
| CAP21 | 06-migration-plan.md | §10.1(S8 해제 조건 — 블로커 3건 전부 해소 + `grep` 판정 기준) | 충족 |
| CAP22 | 01-current-state.md | §1(블로커 4건 표, "재조사 대상이 아니다(CAP22)" 명시) | 충족 |
| CAP23 | 02-policy-decisions.md | D01 후보 비교표(①~④, 4항목 판단 기준) | 충족 |
| CAP24 | 02-policy-decisions.md | D01 확정 답(①, 단일 권고) | 충족 |
| CAP25 | 02-policy-decisions.md | D01 질문 — "비개발자가 클론 후 바로 실행" 판단 기준 명시 | 충족 |
| CAP26 | 02-policy-decisions.md | D01 근거 — 신규 런타임 의존성 0, `run.py` 무영향 | 충족 |
| CAP27 | 02-policy-decisions.md | D01 기각된 후보 ③(이중 백엔드) — 기각 사유 명시 | 충족 |
| CAP28 | 02-policy-decisions.md, 03-history-restore.md | 02 D02(요약), 03 §1(전담) | 충족 |
| CAP29 | 03-history-restore.md | §1 대안 2종(①②③) 비교표 — 최소 상태 대안 명시 평가 | 충족 |
| CAP30 | 03-history-restore.md | §6.1(스토어 측 해당 없음 — 전건 거짓 논리 명시) | 충족 |
| CAP31 | 03-history-restore.md | §6.1(동일 — 암호화 의무도 "전건이 거짓" 논리로 해당 없음) | 충족 |
| CAP32 | 03-history-restore.md | §6.1 + §6.2(`data/conversations` FOLLOW-UP (a)~(e) 표로 재확인) | 충족 |
| CAP33 | 02-policy-decisions.md | D03 확정 답 — 24시간(TBD 아님, 근거 포함) | 충족 |
| CAP34 | 02-policy-decisions.md, 04-interface.md | 02 D03(lazy sweep), 04 §1.5 #10(`sweep_expired`) | 충족 |
| CAP35 | 02-policy-decisions.md | D04 확정 답 — 같은 스토어·별도 테이블·단일 트랜잭션 | 충족 |
| CAP36 | 04-interface.md | §3(기존 4개 공개 함수 폐기 2 / 대체 2 표 — 4개 전부 실측 호출부와 함께 처리) | 충족 |
| CAP37 | 01-current-state.md, 06-migration-plan.md | 01 §6(209 확정), 06 §12.1(단계별 재확인 규율) — **06 §4.5 「알려진 결함 K1」이 S2~S5-h 구간에서 209 규율을 깨고 S2·S3·S4·S5-a~S5-g 의 209 확인을 무효화한다고 문서 스스로 기록. 사용자 결정(`fix_defect`, 2026-07-28)에 따라 해소 예정 결함으로 확정, 06 §4.4.2 는 아직 미개정** | **부분충족 — 해소 예정 (후속 페이즈 이관)** (§3 참고) |
| CAP38 | 07-compatibility-review.md | §1(위험 항목 4개 표 — 위험 실체 + 안전 이유) | 충족 |
| CAP39 | 07-compatibility-review.md | §2.1(가드 지목) + §2.2(한계 — 동시성 미검증 명시) | 충족 |
| CAP40 | 07-compatibility-review.md | §4.4(4개 문서 grep 결과 음성 언급 0건) | 충족 |
| CAP41 | 04-interface.md, 07-compatibility-review.md | 04 §7.6(UTF-8 고정 계약 표), 07 §1 UTF-8 절 | 충족 |
| CAP42 | 07-compatibility-review.md | §4.4(범위 밖 3항목 미설계 grep 확인) | 충족 |
| CAP43 | 07-compatibility-review.md | §5.1(인증·권한 체계 — 독립 절) | 충족 |
| CAP44 | 07-compatibility-review.md | §5.2(관리자 화면 도메인 중립화 — 독립 절) | 충족 |
| CAP45 | 07-compatibility-review.md | §5.3(LLM 백엔드 API 전환 — 독립 절) | 충족 |
| CAP46 | README.md(신규) | "대상 리포지토리" 절 | 충족 |
| CAP47 | origin.md(원문 미변경), 본 문서 §2 | §2 원장 무결성 검증(원문이 수정됐다면 해시가 어긋나 검증이 실패한다) | 충족 |
| CAP48 | 본 문서 §3 | "미충족 처리" 절 — CAP37 부분충족을 침묵 축소하지 않고 결정 요청으로 승격 | 충족 |
| CAP49 | 본 문서 §2 | `capability_ledger.py validate` 출력(origin_checked: true) | 충족 |

**행 수 검산**: 위 표는 CAP01부터 CAP49까지 49행이며 각 CAP id 가 정확히 한 번씩 등장한다
(검증 `CAP-49-ROWS-OK`).

---

## 2. 원장 무결성 검증

산문이 아니라 명령 출력을 근거로 남긴다. 저장소 루트에서 다음을 실행했다.

```bash
python3 "$HOME/.claude/skills/phase-intake/scripts/capability_ledger.py" validate \
  --capabilities "$ROOT/docs/planning/session-store-multiworker/capabilities.md" \
  --origin "$ROOT/docs/planning/session-store-multiworker/origin.md"
```

출력:

```json
{"ok": true, "capabilities": 49, "reductions": 0, "origin_checked": true, "errors": []}
```

`ok: true`·`origin_checked: true`·`errors: []` — origin.md 의 verbatim 블록 sha256 재해시가
`capabilities.md` 의 `origin_manifest.sha256`(CAP49)과 일치하고, `reductions: 0` 은 지금까지
어떤 CAP 도 축소·연기로 기록되지 않았음을 뜻한다(CAP47·CAP48 의 직접 증거).

### 태스크 레벨 무수정 게이트 (고정 기준선 `c5adc0c` 대조)

```bash
git diff --quiet c5adc0c -- ':/' ':(top,exclude)docs/design/session-store' \
  ':(top,exclude)docs/planning' ':(top,exclude)docs/e2e'
# → TASK-LEVEL-CODE-UNCHANGED-OK
git diff --quiet HEAD -- ':/' ':(top,exclude)docs/design/session-store' \
  ':(top,exclude)docs/planning' ':(top,exclude)docs/e2e'
# → CODE-UNCHANGED-OK
```

두 명령 모두 통과했다 — Phase 1~7 이 커밋한 7건의 문서 페이즈 어디에서도 `docs/design/
session-store`·`docs/planning`·`docs/e2e` 바깥의 파일(저장소 코드)이 바뀌지 않았다
(CAP04·CAP09 의 태스크 전체 증거).

---

## 3. 미충족 처리 — CAP37 부분충족 (알려진 결함 K1)

### 3.1 무엇이 부분충족인가

CAP37 은 "회귀 기준선 `pytest 209 passed` 가 이행 후에도 유지되어야 할 숫자로 설계에
기록된다"는 것이다. 숫자 자체는 [01 §6](./01-current-state.md)·[06 §12.1](./06-migration-plan.md)에
정확히 기록돼 있다. 부분충족인 지점은 그 기록을 **운용하는 메커니즘**이다 — 06 문서 §0 은
"각 단계는 그 단계만으로 209 를 통과해야 하며, 통과하지 못한 단계는 그 자리에서 되돌린다"는
규율을 세우는데, 문서 자신이 [06-migration-plan.md §4.5 「알려진 결함 K1」](./06-migration-plan.md)의
소제목에서 그 규율이 **S2~S5-h 구간에서 성립하지 않는다**고 기록했다.

이 `S2~S5-h` 표기와, 아래에서 인용하는 `S2·S3·S4·S5-a~S5-g`(209 확인이 무효화되는 개별
단계 목록)는 서로 다른 개념이며 둘 다 06 §4.5 원문 그대로다 — `S2~S5-h` 는 결함이 살아 있는
**전체 창**(수정이 착지하는 S5-h 포함)을 가리키고, `S2·S3·S4·S5-a~S5-g` 는 그 창 안에서
**자기 자신의 209 확인이 무효가 되는** 단계만 추린 목록이다(S5-h 는 그 줄을 직접 이행하는
단계라 자신의 209 확인은 유효하다). 두 표기가 다르다고 문서 간 불일치가 아니다.

**결함의 실체**: `tests/test_security.py:49` 가 `chat._sessions["sec-output-bound"].history` 를
첨자로 읽는 저장소 유일의 지점인데, S2 가 도입하는 과도기 프록시의 `__getitem__` 반환값은
`SessionView`([04 §1.4](./04-interface.md))이고 `history` 는 미저장 필드라 `SessionView` 에
없다. 그 결과 S2 직후 이 테스트가 `AttributeError` 로 깨지고, 그 상태가 이 줄을 이행하는
S5-h 까지 지속된다 — 06 문서 스스로 "K1 이 살아 있는 동안 S2·S3·S4·S5-a~S5-g 의 209 확인이
함께 무효가 된다"고 적었다.

06 문서는 이미 해소 방향(프록시에 `history` 지연 프로퍼티를 추가해 `restore_history` 로 위임)을
적어 두었지만, 이는 **권고**일 뿐 이 문서 자신의 설계로 채택되지는 않았다 — §4.4.2 의 「읽기
전용」 규정이 아직 그 방향으로 갱신되지 않았다.

### 3.2 이 문서의 판단

이 부분충족은 축소가 아니라 Phase 6 소유의 결함이다. 사용자가 결정 `cap37-k1-resolution-path`
에 2026-07-28 **`fix_defect`** 로 답했다([decisions.md](../../planning/session-store-multiworker/decisions.md)
참고) — 부분충족을 의도적 축소로 기록하고 넘어가는 경로(`reduce_via_intake`)는 채택되지
않았다.

이 답변에도 불구하고 CAP37 은 **이 문서 기준으로는 여전히 부분충족**이다. 실제 해소(06
§4.4.2 「읽기 전용」 규정에 `history` 지연 프로퍼티를 반영하는 것)가 아직 착지하지 않았기
때문이다 — 이 결정 이후에도 `06-migration-plan.md` §4.4.2 는 변경되지 않았다. 따라서 위 §1
표의 CAP37 행을 충족으로 올리지 않는다.

바뀐 것은 **처분(disposition)** 이다: CAP37 은 더 이상 "축소할지 결함을 고칠지" 열린 질문이
아니라 **해소 예정 결함(후속 페이즈 이관)** 으로 확정됐다. 이는 의도적 축소가 아니므로
`capabilities.md` 에는 `reduction` 항목도 `user_ack` 도 기록되지 않으며, 원장은
`reductions: 0` 을 유지한다(§2 참고) — 이것은 누락이 아니라 `fix_defect` 선택의 정확한
귀결이다: 원장에 `reduction`+`user_ack` 가 쌓이는 경로는 `reduce_via_intake` 뿐이고, 이번
답변은 그 경로를 타지 않았다.

후속 조치는 `decisions.md` 말미의 `/phase-add` 후보 `k1-proxy-history-property` 로
정규화돼 있다. 이 후보는 `06-migration-plan.md` §4.4.2 를 개정해 프록시의
`__getitem__`/`get` 반환값에 `history` 지연 프로퍼티(값을 캐시하지 않고 `restore_history` 로
위임)를 규정하며, **이행 task 가 S2 에 착수하기 전에 반드시 착지해야 한다** — K1 이 살아
있는 채로 S2 를 시작하면 `tests/test_security.py:49` 가 즉시 `AttributeError` 로 깨진다.
Phase 8 은 감사 페이즈로서 `06-migration-plan.md` 에 쓸 권한이 없어 이 후보를 스스로
실행하지 않는다.

**결합 관계**: `k1-proxy-history-property` 가 착지해 §4.4.2 가 `history` 지연 프로퍼티를
포함하도록 개정되고 06 §4.5 의 K1 블록이 해소 반영 상태로 갱신되면, **같은 변경 안에서**
위 §1 표의 CAP37 행도 부분충족에서 충족으로 함께 갱신해야 한다. 두 문서가 서로를 인용하는
구조이므로 한쪽만 갱신하면 다른 쪽이 낡은 인용을 갖게 된다.

---

## 4. 관련 문서

- [README.md](./README.md) — 문서 세트 인덱스, 권고안 요약, 대상 리포지토리(CAP46)
- [01 현황 분석](./01-current-state.md) · [02 정책 결정](./02-policy-decisions.md) ·
  [03 개인정보 경계와 history 복원](./03-history-restore.md) ·
  [04 SessionStore 인터페이스](./04-interface.md) · [05 목표 달성 논증](./05-invariants.md) ·
  [06 이행 계획](./06-migration-plan.md) · [07 크로스플랫폼·범위 밖 충돌 검토](./07-compatibility-review.md)
- [capabilities.md — CAP 원장](../../planning/session-store-multiworker/capabilities.md)
- [phase-08-cap-coverage.md — 이 문서의 소스 페이즈](../../planning/session-store-multiworker/phase-08-cap-coverage.md)
