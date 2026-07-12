---
task: gui-uplift
phase_count: 6
created: 2026-07-12
---

# GUI 업리프트 — 참조 이미지 수준 재스타일 — 진행 체크리스트

> **AI development guide**: `/phase-run` reads this file to select the next phase.
> If progressing manually, keep the same table updated.

<!-- Parser-required structural heading: keep this exact heading text. -->
## 진행 상태 요약

| Phase | 파일 | 항목 | 완료 | 진행률 | 상태 | 커밋 |
|-------|------|------|------|--------|------|------|
| 1 | [phase-01-config-probe.md](./phase-01-config-probe.md) | 3 | 3 | 100% | completed | e92b2cf |
| 2 | [phase-02-visual-restyle.md](./phase-02-visual-restyle.md) | 8 | 8 | 100% | completed | 623714e |
| 3 | [phase-03-stepper.md](./phase-03-stepper.md) | 6 | 6 | 100% | completed | 32375d0 |
| 4 | [phase-04-quick-chips.md](./phase-04-quick-chips.md) | 6 | 6 | 100% | completed | b55d579 |
| 5 | [phase-05-browser-smoke.md](./phase-05-browser-smoke.md) | 5 | 5 | 100% | completed | - |
| 6 | [phase-06-intake-panel-hidden-fix.md](./phase-06-intake-panel-hidden-fix.md) | 3 | 3 | 100% | completed | b0f63e7 |
| **Total** | | **31** | **31** | **100%** | | |

<!-- Parser-required structural heading: keep this exact heading text. -->
## Phase 의존성

```
Phase 1 (config 프로브) ─┬─▶ Phase 3 (스테퍼) ─▶ Phase 4 (칩) ─┬─▶ Phase 5 (브라우저 스모크)
Phase 2 (비주얼 전면) ───┘                                     └─▶ Phase 6 (intake-panel hidden 수정) ─▶ Phase 5 재검증
```

Phase 1·2는 scope 서로소(app/main.py+tests vs static/) — 병렬 실행 가능.
Phase 3·4는 static/ 3파일 공유 — 직렬.
Phase 6은 Phase 5 스모크가 발견한 CSS 결함의 후속 수정 — depends_on [4]
(Phase 5가 needs_user로 이 수정을 기다리므로 [5] 지정 시 상호 대기 교착).

<!-- Parser-required structural heading: keep this exact heading text. -->
## 우선순위

| 등급 | Phase | 설명 | 단위/체크포인트 |
|------|-------|------|-----------|
| P0 | Phase 1 | 스키마 프로브 — 스테퍼·칩의 스왑 회귀 게이트 전제 | unit: additive 엔드포인트 |
| P0 | Phase 2 | 비주얼 전면 — 참조 이미지 8요소 | unit: static 3파일 리스타일 |
| P1 | Phase 3 | 3단계 스테퍼 — 파생 규칙 + fail-closed 게이트 | unit: 순수 함수 + 마크업 |
| P1 | Phase 4 | 퀵리플라이 칩 — 신호어 매칭 문장 | unit: 칩 행 + 수명주기 |
| P0 | Phase 5 | 브라우저 스모크 — 스왑 회귀·참조 대조 최종 게이트 | checkpoint: playwright 스모크 |
| P0 | Phase 6 | intake-panel hidden CSS 결함 수정 — 스왑 회귀 게이트 통과 전제 | unit: CSS 1줄 + 정적 단언 |

<!-- Parser-required structural heading: keep this exact heading text. -->
## 권장 실행 순서

1. Phase 1, Phase 2 (병렬 가능)
2. Phase 3 -> Phase 4
3. Phase 5 (스크린샷 사용자 확인 — intervention)
4. Phase 6 (CSS 결함 수정) -> Phase 5 재검증

<!-- Parser-required structural heading: keep this exact heading text. -->
## 검증 체크리스트

### 공통 검증
- [ ] .venv/bin/python -m pytest -q 전체 통과 (시스템 pytest 금지 — 의존성 없어 수집 에러)
- [ ] /api/chat 계약 {reply, turn, limit_reached} 무변경, intake 필드 additive 유지
- [ ] knowledge-alt 스왑 시 패널·스테퍼·칩 미노출
- [ ] _persona.md·봇 말투 무수정, 엔진 수정은 GET /api/config(사용자 승인)로 한정

<!-- Parser-required structural heading: keep this exact heading text. -->
## 관련 문서

- [README](./README.md)
- [spec-review](./spec-review.md)
- 참조 이미지: `docs/design/gui-reference.png`
