# 세션 스토어 분리 (다중 워커·재시작 내성) — 설계 문서 인덱스

목표: 세션 상태를 프로세스 메모리에서 분리해 다중 워커(`uvicorn --workers N`)와 서버 재시작을
견디게 만든다. 최종 배포 형태는 Docker 웹서비스다. 이 문서 세트의 산출물은 **설계 문서**뿐이며,
구현과 테스트 작성은 별도 task 로 미룬다([capabilities.md](../../planning/session-store-multiworker/capabilities.md)
CAP04·CAP08·CAP09).

## 대상 리포지토리

이 문서 세트 전체가 대상으로 삼는 리포지토리는 다음 하나뿐이다(CAP46).

```
/Volumes/LEARNING/빅션/90_작업중/chatbot_phaseskill  (lmwiki-chatbot, git HEAD c5adc0c 시점 기준)
```

`/Volumes/LEARNING/E&C/05_프로그램운영/chatbot_phaseskill` 같은 사본은 정본이 아니다.

## 읽는 순서

| # | 문서 | 내용 |
|---|------|------|
| 1 | [01-current-state.md](./01-current-state.md) | 현황 분석 — 블로커 4건, `_sessions` 직접 접근 37곳/13파일, `ChatSession` 필드 7개, 401 분기 추적, `append_turn`↔`history.append` 비대칭 5건, 209 회귀 기준선 |
| 2 | [02-policy-decisions.md](./02-policy-decisions.md) | 정책 결정 — D01(스토어)·D03(TTL)·D04(레이트리밋 배치)·D05(대화 쓰기 동시성) 확정 근거 |
| 3 | [03-history-restore.md](./03-history-restore.md) | 개인정보 경계(D02)와 `history` 복원 설계 — 안전 경계 보존, 날짜 경계 병합, 복원 알고리즘 |
| 4 | [04-interface.md](./04-interface.md) | `SessionStore` 인터페이스 — 연산 11개, 오류 코드, 스키마, 생성/10턴 캡/대화 쓰기 경합 해소 |
| 5 | [05-invariants.md](./05-invariants.md) | 목표 달성 논증 — 불변식 I1~I6, 다섯 전제(T1~T5), 종합 판정 |
| 6 | [06-migration-plan.md](./06-migration-plan.md) | 이행 계획(스펙만, 미실행) — S1~S8 여덟 단계, 37+9곳 전건 배정, 중단 기준·롤백 |
| 7 | [07-compatibility-review.md](./07-compatibility-review.md) | 크로스플랫폼 위험 검토, 범위 밖 3항목(인증·관리자 화면·LLM 백엔드) 충돌 검토 |
| 8 | [08-cap-coverage.md](./08-cap-coverage.md) | CAP01~CAP49 전건 커버리지 대조, 원장 무결성 검증 |

## 권고안 요약

| 결정 | 확정 답 | 근거 문서 |
|------|---------|-----------|
| 세션 스토어 | **SQLite**(표준 라이브러리 `sqlite3`, WAL), 기존 `/app/data` 볼륨, 로컬·Docker 동일 백엔드. 신규 런타임 의존성 0 | [02 D01](./02-policy-decisions.md) |
| 개인정보 경계 | `ChatSession` 최소 상태만 스토어에 저장(`session_token`/`turns`/`slots`/`last_question_slot_id`/`participant_id`). `history`(대화 원문)는 **미저장** — `data/conversations/{day}/{sid}.json` 에서 복원 | [02 D02](./02-policy-decisions.md), [03](./03-history-restore.md) |
| 세션 TTL | 마지막 활동 기준 **24시간** + 요청 경로 lazy sweep(별도 크론 없음) | [02 D03](./02-policy-decisions.md) |
| 레이트리밋 배치 | 세션과 **같은 DB, 별도 테이블**, 하나의 트랜잭션 경계로 세션 쓰기와 직렬화 | [02 D04](./02-policy-decisions.md) |
| 인터페이스 방침 | 기존 4개 함수(`has_session`/`owns_session`/`session_token`/`_get_session`) **전면 재설계** — `open_session`/`verify_owner`/`consume_turn`/`append_conversation_turn` 등 11개 연산으로 대체. R1(전체 덮어쓰기 API 금지)·R2(판정을 `WHERE` 절로) 두 규칙을 따른다 | [04](./04-interface.md) |

## 상태

Phase 1~11 은 완료됐고 CAP01~CAP49 커버리지 대조([08](./08-cap-coverage.md))에서 **49건 전건 충족**으로
확인됐다. CAP37(회귀 기준선 209 유지 규율)은 이행 계획의 알려진 결함(K1) 때문에 한동안 조건부
판정이었다 — 06 §4.5 「알려진 결함 K1」이 S2~S5-h 구간에서 209 재확인 규율이 성립하지 않는다고
기록했었다(영향을 받는 개별 단계는 S2·S3·S4·S5-a~S5-g). 사용자가 이 결함을 `fix_defect` 로
답했고(2026-07-28), Phase 9 가 06 §4.4.2 「읽기 전용」 규정에 `history` 지연 프로퍼티를 본문
규정으로 승격해 그 개정을 착지시킴으로써 K1 을 해소했다 — S2 의 중단 기준이 209 로 복귀했다.
Phase 11(이 문서)이 그 해소를 실물 대조해 CAP37 행을 충족으로 갱신했다. 상세는
[08-cap-coverage.md §3](./08-cap-coverage.md)을 참고한다.

## 관련 문서

- [capabilities.md — CAP 원장](../../planning/session-store-multiworker/capabilities.md)
- [origin.md — 원 의도(verbatim, frozen)](../../planning/session-store-multiworker/origin.md)
- [decisions.md — D01~D07 사용자 확정 답](../../planning/session-store-multiworker/decisions.md)
