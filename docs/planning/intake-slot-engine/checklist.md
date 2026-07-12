---
task: intake-slot-engine
phase_count: 7
created: 2026-07-12
---

# 슬롯 스키마 문진 엔진 + 상담 접수면담 데모 — 진행 체크리스트

> **AI development guide**: `/phase-run` reads this file to select the next phase.
> If progressing manually, keep the same table updated.

<!-- Parser-required structural heading: keep this exact heading text. -->
## 진행 상태 요약

| Phase | 파일 | 항목 | 완료 | 진행률 | 상태 | 커밋 |
|-------|------|------|------|--------|------|------|
| 1 | [phase-01-schema-parser.md](./phase-01-schema-parser.md) | 4 | 4 | 100% | completed | 2be747a |
| 2 | [phase-02-counseling-schema.md](./phase-02-counseling-schema.md) | 5 | 5 | 100% | completed | e4596a3 |
| 3 | [phase-03-fake-slot-loop.md](./phase-03-fake-slot-loop.md) | 8 | 8 | 100% | completed | b6db56f |
| 4 | [phase-04-real-extraction.md](./phase-04-real-extraction.md) | 5 | 5 | 100% | completed | 8d82ff5 |
| 5 | [phase-05-structured-summary.md](./phase-05-structured-summary.md) | 6 | 6 | 100% | completed | e52a915 |
| 6 | [phase-06-slot-e2e.md](./phase-06-slot-e2e.md) | 6 | 0 | 0% | pending | - |
| 7 | [phase-07-demo-docs.md](./phase-07-demo-docs.md) | 4 | 0 | 0% | pending | - |
| **Total** | | **38** | **28** | **74%** | | |

<!-- Parser-required structural heading: keep this exact heading text. -->
## Phase 의존성

```
Phase 1 (스키마 파서) ──▶ Phase 2 (상담 스키마+페르소나) ──▶ Phase 3 (fake 슬롯 루프)
    ──▶ Phase 4 (실모드 추출) ──▶ Phase 5 (구조화 요약) ──▶ Phase 6 (e2e 4종) ──▶ Phase 7 (데모 문서)
```

전 구간 직렬 — Phase 3~5가 같은 파일(app/chat.py, app/intake.py)을 순차 확장하고, e2e(6)는 2~5 산출물 전부에, 문서(7)는 동작하는 데모에 의존한다.

<!-- Parser-required structural heading: keep this exact heading text. -->
## 우선순위

| 등급 | Phase | 설명 | 단위/체크포인트 |
|------|-------|------|-----------|
| P0 | Phase 1 | 스키마 파서 — None 폴백 계약이 엔진 전체의 안전선 (CAP01/09) | unit: 파서+폴백 |
| P0 | Phase 3 | fake 슬롯 루프 — 주입·조건부 활성·다중 추출·레드플래그 (CAP02~06/12) | unit: 대화 루프 배선 |
| P0 | Phase 6 | fake e2e 4종 + 스왑 회귀 — 성공 기준 그 자체 (CAP18/20~24) | checkpoint: 통합 검증 |
| P1 | Phase 2 | 상담 3-트랙 스키마 + 페르소나 소유권 (CAP11/13/14) | unit: 지식 데이터 |
| P1 | Phase 4 | 실모드 D02 추출 + 신뢰 경계 (D02) | unit: 추출 프로토콜 |
| P1 | Phase 5 | 구조화 JSON 요약 + 기존 테스트 정합 (CAP07/08) | unit: 요약 경로 |
| P2 | Phase 7 | 데모 시나리오 문서 + supersede 메모 (CAP15/19/25) | unit: docs |

<!-- Parser-required structural heading: keep this exact heading text. -->
## 권장 실행 순서

1. Phase 1 → 2 → 3 → 4 → 5 → 6 → 7 (전 구간 직렬 — 병렬 여지 없음)

<!-- Parser-required structural heading: keep this exact heading text. -->
## 검증 체크리스트

### 공통 검증
- [ ] `pytest -q` 전체 통과 (매 phase 커밋 전)
- [ ] knowledge-alt 스왑 시 기존 Q&A 폴백 회귀 없음 (tests/test_swap_e2e.py)
- [ ] API 계약 {reply, turn, limit_reached} 무변경
- [ ] 저장 스키마 {seq, role, text}·rate limit·SQLite 배치 무변경

<!-- Parser-required structural heading: keep this exact heading text. -->
## 관련 문서

- [README](./README.md)
- [spec-review](./spec-review.md)
- [intake](./intake.md) · [decisions](./decisions.md) · [research](./research.md) · [capabilities](./capabilities.md) · [origin](./origin.md)
