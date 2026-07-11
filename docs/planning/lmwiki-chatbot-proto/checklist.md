---
task: lmwiki-chatbot-proto
phase_count: 8
created: 2026-07-11
---

# LM Wiki 챗봇 프로토타입 — 진행 체크리스트

> **AI development guide**: `/phase-run` reads this file to select the next phase.
> If progressing manually, keep the same table updated.

<!-- Parser-required structural heading: keep this exact heading text. -->
## 진행 상태 요약

| Phase | 파일 | 항목 | 완료 | 진행률 | 상태 | 커밋 |
|-------|------|------|------|--------|------|------|
| 1 | [phase-01-knowledge-loader.md](./phase-01-knowledge-loader.md) | 6 | 6 | 100% | completed | 829fa33 |
| 2 | [phase-02-chat-api.md](./phase-02-chat-api.md) | 5 | 0 | 0% | pending | - |
| 3 | [phase-03-storage-batch.md](./phase-03-storage-batch.md) | 5 | 0 | 0% | pending | - |
| 4 | [phase-04-ratelimit.md](./phase-04-ratelimit.md) | 6 | 0 | 0% | pending | - |
| 5 | [phase-05-chat-ui.md](./phase-05-chat-ui.md) | 5 | 0 | 0% | pending | - |
| 6 | [phase-06-swap-e2e-smoke.md](./phase-06-swap-e2e-smoke.md) | 3 | 0 | 0% | pending | - |
| 7 | [phase-07-security-review.md](./phase-07-security-review.md) | 4 | 0 | 0% | pending | - |
| 8 | [phase-08-deploy.md](./phase-08-deploy.md) | 5 | 0 | 0% | pending | - |
| **Total** | | **39** | **6** | **15%** | | |

<!-- Parser-required structural heading: keep this exact heading text. -->
## Phase 의존성

```
Phase 1 ──▶ Phase 2 ──▶ Phase 3 ─┐
                   ├──▶ Phase 4 ─┼──▶ Phase 6 ──▶ Phase 7 ──▶ Phase 8
                   └──▶ Phase 5 ─┘
(Phase 3/4/5는 scope 서로소 — 병렬 실행 가능)
```

<!-- Parser-required structural heading: keep this exact heading text. -->
## 우선순위

| 등급 | Phase | 설명 | 단위/체크포인트 |
|------|-------|------|-----------|
| P0 | Phase 1 | 지식 로더 — 교체 가능 구조의 기반 | unit: 지식/로직 분리 invariant |
| P0 | Phase 2 | 대화 루프 + 10턴 캡 — 챗봇 본체 | unit: API 계약 {reply,turn,limit_reached} |
| P1 | Phase 3 | JSON 저장 + SQLite 일배치 | unit: 저장 파이프라인 |
| P1 | Phase 4 | IP rate limit + 비용 캡 | unit: 세션 5회/시간 집행 |
| P1 | Phase 5 | 채팅 UI | unit: 정적 페이지 |
| P0 | Phase 6 | 지식 스왑 실증 + 통합 스모크 | checkpoint: 통합 검증 |
| P1 | Phase 7 | 보안 검토 + 하드닝 | checkpoint: 배포 전 게이트 |
| P0 | Phase 8 | 배포 + 실환경 검증 (사용자 개입) | checkpoint: 실배포 검증 |

<!-- Parser-required structural heading: keep this exact heading text. -->
## 권장 실행 순서

1. Phase 1 → 2
2. Phase 3, 4, 5 (병렬 가능)
3. Phase 6 → 7 → 8 (Phase 8은 intervention — 플랫폼 확정·실배포에 사용자 참여)

<!-- Parser-required structural heading: keep this exact heading text. -->
## 검증 체크리스트

### 공통 검증
- [ ] .venv/bin/python -m pytest -q 전체 통과
- [ ] bash scripts/smoke_local.sh 통과 (Phase 6 이후)
- [ ] 시크릿 스캔 통과 — 리포·히스토리에 API 키 없음 (Phase 7 이후)

<!-- Parser-required structural heading: keep this exact heading text. -->
## 관련 문서

- [README](./README.md)
- [spec-review](./spec-review.md)
- [intake](./intake.md) · [decisions](./decisions.md) · [research](./research.md) · [capabilities](./capabilities.md) · [origin](./origin.md)
