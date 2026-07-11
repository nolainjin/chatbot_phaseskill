---
phase: 8
title: 배포 구성 + 실배포 검증
status: pending
depends_on: [7]
scope:
  - Dockerfile
  - .dockerignore
  - deploy/README.md
  - deploy/checklist.md
intervention_likely: true
intervention_reason: "배포 플랫폼 확정(D01 유보: Railway/Fly.io/Oracle/Hetzner) + 계정·과금 승인 + 실배포 실행에 사용자 결정·참여 필요 (D06: 실배포까지 이번 task 범위)"
executor: sonnet
load_bearing: ""
e2e_refs: []
e2e_triggers: []
phase_context:
  baseline: "missing"
  adoption: "bootstrap"
  coverage: "standard"
  enforcement_during_run: "warn"
  materialize_at: "finalization"
---

# Phase 8: 배포 구성 + 실배포 검증

> **범위**: Both
> **난이도**: M
> **의존성**: Phase 7
> **영향 파일**: `Dockerfile` (신규), `deploy/README.md` (신규)

## 배경

origin §5: 저비용/무료 호스팅에서 실행, "실제 배포 환경에서 JSON 저장과 SQLite 적재가 가능한지 확인 필요." 사용자가 실배포까지 이번 task에 포함하기로 확정했다(D06). 플랫폼은 아직 유보(D01) — research.md가 공식 문서로 검증한 후보 4종(Railway Hobby $5/월, Fly.io $5~10/월, Oracle Always Free VM $0, Hetzner €5.49/월) 중에서 이 phase 진입 시 사용자가 확정한다(GM1 needs_user). CAP11(공개 URL 실배포)과 CAP12(실환경 저장·적재 검증)는 localhost 데모로 갈음할 수 없다는 적대적 플래그가 붙어 있다.

## 심볼 인벤토리

(없음)

## 설계

```
Dockerfile:
    python slim 베이스 → requirements 설치 → 앱 복사
    CMD uvicorn 워커 1 고정   # rate limit 파일 카운터 전제 (Phase 4)
    data/ 는 볼륨 마운트 지점으로 문서화

deploy/README.md (research.md 소스 기반, 플랫폼별):
    Railway: 볼륨 attach + Cron Schedule 기능으로 배치 등록, TRUST_PROXY_HOPS=1
    Fly.io: fly volumes + 스케줄 머신/외부 크론, TRUST_PROXY_HOPS=1
    Oracle Free VM / Hetzner: docker run -v + 시스템 crontab, TRUST_PROXY_HOPS=0

deploy/checklist.md (실배포 후 사용자와 함께 확인):
    공개 URL 응답 → 실대화 → JSON 저장 확인 → 배치 수동 1회+SQLite 조회
    → 6번째 세션 차단 → TRUST_PROXY_HOPS 권장값 확인
    → 서로 다른 두 클라이언트(PC/폰 LTE)가 독립 카운트되는지 확인
```

이 phase는 두 단계 성격이다: (a) 배포 준비물 생성(자동), (b) 실배포 실행+검증(사용자 개입 — 플랫폼 확정, 계정/과금, 함께 체크리스트 수행). (b)에서 orchestrator는 needs_user로 멈추고 사용자 확인 후 진행한다.

## 체크리스트

- [ ] Dockerfile: 앱 실행 이미지(uvicorn 워커 1 고정 — rate limit 파일 카운터 전제), data/ 영속 볼륨 경로 명시, 배치 실행 진입점 포함
- [ ] deploy/README.md: 후보 4개 플랫폼별 배포 절차(볼륨 마운트·env 설정·TRUST_PROXY_HOPS 권장값·크론/스케줄 등록) — research.md 소스 기반
- [ ] 로컬 컨테이너 스모크: docker 가용 시 build+기동 확인(불가 시 사유 기록), ANTHROPIC_API_KEY 제공 시 실모델 1회 호출 스모크로 SDK 통합 사전 확인
- [ ] deploy/checklist.md: 실배포 후 검증 항목(공개 URL 응답·대화 후 JSON 저장 확인·배치 1회 수동 실행+SQLite 확인·6번째 세션 차단 확인·TRUST_PROXY_HOPS 플랫폼 권장값 설정 확인·서로 다른 두 클라이언트(예: PC/폰 LTE)가 각자 독립 카운트되는지 확인)
- [ ] 확정 플랫폼에 실배포 실행(사용자 개입: 플랫폼 확정 GM1 + 계정·과금 승인) 후 deploy/checklist.md 검증 항목 전부 확인 — 공개 URL 응답·JSON 저장·배치 수동 1회+SQLite·6번째 세션 차단 (사용자 확정 2026-07-11: 실배포까지 이번 task 범위)

## 영향 범위

앱 코드 무수정(배포 산출물만 추가). 실배포 후 문제 발견 시 해당 구현 phase로 회귀. 비용 발생 지점(플랫폼 과금·실모델 호출)은 전부 사용자 승인 뒤에만 실행.

## 검증

```bash
docker build -t lmwiki-chatbot . || echo "docker 부재 — deploy/README.md 문서 검증으로 대체(사유 기록)"
```
