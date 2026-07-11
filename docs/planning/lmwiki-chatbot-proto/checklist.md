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
| 1 | [phase-01-knowledge-loader.md](./phase-01-knowledge-loader.md) | 6 | 6 | 100% | completed | 664167b |
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

## Cross-Phase 메모

- cross-phase (2026-07-11 리셋): Phase 1·2 1회차 실행 산출물(커밋 829fa33·9d9c0c4의 코드)은 사용자 요청으로 삭제 — 아래 답변 반영해 Phase 1부터 재실행. 1회차에서 starlette(1.3.1)+httpx(0.28.1) testclient deprecation 경고 있었음(테스트는 통과) — 재실행 시 참고
- cross-phase (2026-07-11 사용자 답변, intake open questions 전부 해소): 첫 도메인 = **상담 초기 면담 챗봇**. 지식 프론트매터 레퍼런스 = SecondBrain wiki (`type/aliases/author/date/tags[/cluster]`, 제목은 H1) — Phase 1 스펙에 스키마 호환 요건(title 폴백·meta 보존) 반영됨. 턴 = 사용자 발화 기준(Phase 2 구현대로). 상담 도메인 민감정보 가능성 → Phase 7 저장 데이터 점검 가중. 실배포용 상담 지식셋 작성은 Phase 8 전 별도 콘텐츠 작업 (Phase 6 스왑 검증은 기존 샘플 2벌로 충분)

<!-- Parser-required structural heading: keep this exact heading text. -->
## 관련 문서

- [README](./README.md)
- [spec-review](./spec-review.md)
- [intake](./intake.md) · [decisions](./decisions.md) · [research](./research.md) · [capabilities](./capabilities.md) · [origin](./origin.md)
