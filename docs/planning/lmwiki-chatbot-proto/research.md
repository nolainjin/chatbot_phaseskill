---
task: lmwiki-chatbot-proto
created: 2026-07-11
research_status: complete
---

# LM Wiki 챗봇 프로토타입 — Research

## Research Need Gate

```yaml
research:
  required: true
  reason: "사용자가 직접 '실제 배포 환경에서 JSON 저장과 SQLite 적재가 가능한지 확인 필요'를 요구. 무료/저비용 호스팅의 영속 디스크 지원 여부는 date-sensitive 외부 사실이며, 잘못 판단하면 저장 구조 전체가 무효화됨. 보안(rate limit, API 비용 공격) 제약도 관여."
  source_policy: official_docs_first
  queries:
    - "free hosting persistent disk JSON SQLite 2026"
    - "Fly.io volumes pricing free allowance 2026"
    - "Render free tier persistent disk"
    - "Railway hobby plan pricing persistent volume"
    - "Cloudflare Workers filesystem SQLite D1"
    - "Hugging Face Spaces persistent storage pricing"
    - "cheap VPS Hetzner pricing 2026"
```

## Sources

리서치 수행: document-specialist agent, 2026-07-11. 핵심 검증 항목 = "무료/최저가 티어에서 영속(persistent) 쓰기 가능 디스크 + 일 1회 배치(cron) + 외부 LLM API 아웃바운드".

```yaml
sources:
  - url: "https://fly.io/docs/about/pricing/"
    type: official_docs
    checked_at: "2026-07-11"
    relevant_claim: "신규 가입 무료 티어 없음(2024-10 이후, 트라이얼만). Volumes $0.15/GB·월 + 초 단위 머신 과금 — 소형 상시/scale-to-zero 구성 월 $5~10. 스케줄 머신 또는 외부 cron으로 배치 가능."
    confidence: high
    verdict: viable_low_cost
  - url: "https://render.com/docs/disks"
    type: official_docs
    checked_at: "2026-07-11"
    relevant_claim: "무료 웹 서비스는 영속 디스크 부착 불가(ephemeral, 재시작마다 초기화) + 15분 유휴 시 spin-down + 크론 없음. 영속 디스크는 Starter $7/월 + $0.25/GB·월."
    confidence: high
    verdict: incompatible_without_redesign_on_free
  - url: "https://docs.railway.com/pricing/plans"
    type: official_docs
    checked_at: "2026-07-11"
    relevant_claim: "Hobby $5/월(고정) — 영속 Volume(~$0.15/GB·월) + 서비스 내장 Cron Schedule + 유휴 spin-down 없음. '월 $1 크레딧 Free 플랜'은 문서 간 상충(가입 화면 재확인 필요)."
    confidence: medium
    verdict: viable_low_cost
  - url: "https://www.koyeb.com/docs/reference/volumes"
    type: official_docs
    checked_at: "2026-07-11"
    relevant_claim: "free/eco 인스턴스는 볼륨 부착 불가 명시. 볼륨은 유료 인스턴스 + public preview 상태로 벤더 스스로 백업 권고(내구성 리스크)."
    confidence: high
    verdict: incompatible_without_redesign_on_free
  - url: "https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm"
    type: official_docs
    checked_at: "2026-07-11"
    relevant_claim: "진짜 $0 영구 무료: AMD Micro VM 2대(1GB RAM) 또는 Ampere A1(현재 2 OCPU/12GB — 2026-06경 무공지 반토막 전례) + 영속 블록 스토리지 200GB. 실제 VM이라 cron/systemd/SQLite 네이티브."
    confidence: high
    verdict: viable_free
  - url: "https://developers.cloudflare.com/workers/platform/storage-options/"
    type: official_docs
    checked_at: "2026-07-11"
    relevant_claim: "Workers는 파일시스템 자체가 없음. 저장은 D1/R2/KV로 대체해야 하므로 'JSON 파일 + 로컬 SQLite' 패턴은 데이터 레이어 전면 재설계 없이 이식 불가."
    confidence: high
    verdict: incompatible_without_redesign
  - url: "https://vercel.com/kb/guide/how-can-i-use-files-in-serverless-functions"
    type: official_docs
    checked_at: "2026-07-11"
    relevant_claim: "서버리스 함수 파일시스템은 /tmp(≤500MB) 외 읽기 전용이며 /tmp도 호출·배포 간 비영속. 영속 JSON/SQLite 파일 경로 없음."
    confidence: high
    verdict: incompatible_without_redesign
  - url: "https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/"
    type: official_docs
    checked_at: "2026-07-11"
    relevant_claim: "최저가 CX23(2 vCPU/4GB/40GB NVMe) €5.49/월(2026-06-15 인상 후, ~$6.49). 진짜 VPS — 디스크·SQLite·cron 전부 표준. 단 OS/보안 자가 관리. 가격은 유럽 리전 기준."
    confidence: high
    verdict: viable_low_cost
  - url: "https://huggingface.co/docs/hub/en/spaces-storage"
    type: official_docs
    checked_at: "2026-07-11"
    relevant_claim: "Space 기본 디스크는 ephemeral(재시작 시 유실). 영속 스토리지는 유료 $5/월(20GB)~. Docker SDK로 임의 서버는 가능하나 크론이 1급 기능이 아님(우회 필요)."
    confidence: medium
    verdict: viable_low_cost
  - url: "https://help.pythonanywhere.com/pages/FreeAccountsFeatures/"
    type: official_docs
    checked_at: "2026-07-11"
    relevant_claim: "무료 계정 512MB 영속 디스크는 있으나 2026-01부터 신규 계정은 스케줄 태스크(크론)가 유료 전환. 무료 티어 아웃바운드 화이트리스트 제한 여부 미확인 — LLM API 호출이 막힐 수 있음."
    confidence: medium
    verdict: incompatible_without_redesign_on_free
```

## Findings

- 핵심 결론: "무료 PaaS + 영속 파일 저장 + 크론" 3조건을 동시에 만족하는 곳은 사실상 없음. 사용자의 JSON→SQLite 저장 구조를 그대로 살리려면 (a) 월 $5 안팎의 저비용 PaaS 볼륨, (b) $0 Oracle Always Free VM, (c) 저가 VPS 중 선택.
- 순위 (리서치 agent 결론):
  1. Fly.io — Volumes + 소형 머신 월 $5~10, Dockerfile 하나로 10일 내 배포 가능
  2. Railway Hobby $5/월 — 영속 볼륨 + 내장 Cron Schedule로 설정이 가장 쉬움, 데드라인에 가장 안전
  3. Hetzner CX23 €5.49/월 — 플랫폼 제약 없음, 대신 서버 관리 부담
  - 번외(진짜 $0 필요 시) Oracle Always Free VM — 유일한 영구 무료+영속 디스크. 단 2026-06 스펙 무공지 축소 전례(정책 리스크)
- 서버리스 계열(Cloudflare Workers, Vercel)은 파일시스템 부재/비영속으로 이번 저장 구조와 구조적 불일치 — 채택 시 저장 레이어 전면 재설계 필요.
- Render·Koyeb·PythonAnywhere 무료 티어는 각각 디스크/볼륨/크론 제약으로 탈락.

## Rubric Registry Gaps

`decision_rubrics.py` (as-of 2026-07-11, rubric_count 8) 결과:

- `front_gate_block.blocked: true` — load-bearing 클래스 3건이 `canonical_status: missing`, `author_or_defer_state: none`:
  - `hosting_platform` (missing_rubric) — 본 리서치가 소스 제공 (D01)
  - `llm_provider_and_key_custody` (missing_rubric) — (D02)
  - `tech_stack` (missing_rubric) — (D03)
- 위 3건은 author-or-defer 해소 전까지 `/phase-init` handoff 금지 (D1 BLOCK). 해소 경로는 D04(사용자 결정)로 결정.
- non-LB 파생 클래스 `rate_limit_semantics`, `knowledge_retrieval_strategy` 는 gap-note로만 기록 (decisions.md에 올리지 않음):
  - `rate_limit_semantics`: "1시간 5회"의 단위(세션 vs 메시지)는 intake open question. 기본값: 대화 세션 5회/시간/IP.
  - `knowledge_retrieval_strategy`: 지식 데이터 규모 확인 전까지 단순 로딩+검색 기본. 규모가 크면 phase-init에서 재평가.
- 기존 8개 rubric은 전부 harness 메타 rubric으로 이번 요청과 미매칭 (`matched_rubrics: []`, `suppressed: []`).

## Remaining Uncertainty

- PythonAnywhere 무료 티어 아웃바운드 화이트리스트 제한 — 공식 문서 미확인 (후보 탈락이라 실질 영향 없음)
- Railway "월 $1 크레딧 Free 플랜" 존재 여부 문서 간 상충 — Railway 채택 시 가입 화면에서 재확인
- Hetzner 가격은 유럽 리전 기준, 미국 리전 상이 가능
- Koyeb 유료 볼륨은 public preview — 벤더 자체 백업 권고 (후보 탈락이라 실질 영향 없음)
- LM Wiki 지식 데이터 실물 미확보 — 규모에 따라 knowledge_retrieval_strategy 재평가 필요 (phase-init에서 확인)
