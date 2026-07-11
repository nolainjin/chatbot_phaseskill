---
task: lmwiki-chatbot-proto
spec_review_version: 2
created: 2026-07-11
final_verdict: pass
risk: low
appeal_used: false
fallback_used: false
fallback_reason: ""
contamination_risk: ""
fallback_user_approved: false
---

# LM Wiki 챗봇 프로토타입 — Spec Review

## Active Lenses

- architecture
- testing
- backend
- security
- frontend

리뷰 실행 모델: sub-agent 기반 (purpose reviewer 2회 → critic 2회 → judge 2회 → 결정론 triage 2회 → final purpose re-check 1회, 전부 read-only sub-agent). fallback 미사용.

## Evidence Ledger

```yaml
evidence_ledger:
  evidence_commit: "3076b54087ebd82c32f241c9ea92bfe2f24b47f0"
```

- E01 (Read): `docs/planning/lmwiki-chatbot-proto/intake.md` — goal/facts/assumptions/constraints/risks/open questions 전체
- E02 (Read): `docs/planning/lmwiki-chatbot-proto/research.md` — 무료/저비용 호스팅 영속 디스크 조사(공식 문서 10건, checked_at 2026-07-11). 결론: 무료 PaaS+영속디스크+크론 3박자 부재. viable 후보 Railway Hobby/Fly.io/Oracle Free VM/Hetzner. 서버리스(Cloudflare Workers/Vercel)는 파일시스템 부재/비영속으로 구조적 부적합
- E03 (Read): `docs/planning/lmwiki-chatbot-proto/decisions.md` — D01 hosting explicit defer(후보 4종), D02 Anthropic+서버 env 키, D03 Python+FastAPI+바닐라 HTML/JS, D04 rubric task-local, D05 rate limit=대화 세션 5회(리뷰 중 확정), D06 실배포 포함(리뷰 중 확정), D07 기본 모델 claude-haiku-4-5(리뷰 중 확정)
- E04 (Read): `docs/planning/lmwiki-chatbot-proto/capabilities.md` — CAP 19건(load-bearing 14), 적대적 플래그 9건(지식 스왑 실증·실배포 rate limit·일배치 실동작·배포환경 저장 검증 등)
- E05 (Bash): `tooling_readiness.py` — sem ready / engramx missing(Read/Grep 폴백) / code_files 0
- E06 (Bash): ls / git — 신규 빈 리포. 기존 코드·심볼 없음 → 스펙의 모든 심볼은 [NEW]
- E07 (Research): claude-api 번들 스킬 레퍼런스 (cached 2026-06-24, 로컬 문서) — Python SDK `anthropic.Anthropic()`가 ANTHROPIC_API_KEY env 자동 인식, `client.messages.create(model, max_tokens, system, messages)` 사용법, 모델 ID·가격표(claude-haiku-4-5 $1/$5). confidence: high
- E08 (Read): `PHASE-SKILLS.md` — guided-vibe-coder 프리셋 + ko 산출물

Tooling readiness: sem=ready, engramx=missing, graph=missing, large_files=0

## Memory Evidence

MemoryPacket entries from ProjectMemory or HarnessMemory are audit-only evidence. 이번 task에서 과거 메모리와 충돌하는 항목 없음. 현재 사용자 입력·리포 증거·research 소스가 우선한다.

## Purpose Review

1차 리뷰 verdict는 needs_user였고(S1: rate limit '5회' 단위 미확정, O1: 실배포 검증 범위), 사용자 확정(D05: 대화 세션 5회, D06: 실배포까지 이번 task 포함)으로 해소 후 재실행에서 pass. 아래는 최종(재실행) 결과.

```yaml
purpose_review:
  intended_outcomes:
    - "10턴 캡 텍스트 대화가 동작하고 11번째 발화가 거부됨 (Phase 2, test_chat.py) — SC1"
    - "KNOWLEDGE_DIR 교체만으로 다른 도메인 문서가 프롬프트 컨텍스트에 실림이 e2e로 실증됨 (Phase 1+6, test_swap_e2e.py) — SC2"
    - "대화가 JSON 저장되고 일배치가 SQLite에 멱등 적재됨 (Phase 3, test_storage_batch.py) — SC3"
    - "IP당 1시간 신규 대화 세션 5회(사용자 확정 세션 단위) 제한 + 일일 총량 캡이 집행됨 (Phase 4, test_ratelimit.py) — SC4"
    - "확정 플랫폼에 실배포 실행 후 공개 URL·JSON 저장·배치 수동 1회+SQLite·6번째 세션 차단이 실환경에서 검증됨 (Phase 8 intervention, 사용자 참여) — SC5"
    - "배포 전 AI 보안 검토 수행·기록 + high/critical 수정 + 시크릿 스캔 통과 (Phase 7) — SC6"
    - "Anthropic API를 서버측 env 키로 호출 (Phase 2, .env·.gitignore 구조화) — SC7"
  goal_alignment:
    verdict: pass
    rationale: "직전 두 needs_user 항목(rate-limit 단위·SC5 실배포 범위)이 D05/D06 사용자 확정으로 해소되어 plan(Phase 4/8·SC4/SC5·GM1/GM2)에 반영됐고, 원 요청 7개 SC가 모두 phase/게이트로 닫힘."
  missing_goals: []
  scope_truncations: []
  overclaimed_outcomes: []
```

## Phase Context

```yaml
phase_context:
  baseline: missing
  adoption: bootstrap
  coverage: standard
  enforcement_during_run: warn
  materialize_at: finalization
```

## Context Readiness

```yaml
context_readiness:
  selector: "phase-context-selector"
  status: missing
  selected_docs: []
  skipped_docs: []
  stale_docs: []
  sync_needed: false
  budget:
    max_docs: 0
    max_bytes: 0
  source:
    command: ""
    rationale: "신규 빈 리포로 tracked CONTEXT.md가 존재하지 않아 selector 실행을 생략. phase-init은 context 문서를 생성하지 않으며 materialize_at: finalization 정책만 기록."
```

## Source Blueprint

Omit for non-blueprint tasks.

For blueprint-origin tasks, treat the rendered block above as canonical handoff
data. Preserve parent-origin trace fields and repo-local `research_required`
closure here rather than replacing them with summary prose.

## Decision Surface

```yaml
decision_surface:
  status: present
  source_mode: registry_rerun
  source_artifact: "docs/planning/lmwiki-chatbot-proto/request.json"
  source_command: "python3 skills/phase-intake/scripts/decision_rubrics.py --request-file docs/planning/lmwiki-chatbot-proto/request.json --decisions-file docs/planning/lmwiki-chatbot-proto/decisions.md --rubric-dir /Users/jinduchan/.claude/skills/phase-intake/rubrics --as-of 2026-07-11 --pretty"
  freshness: fresh
  no_memory_promotion: true
  accepted_defaults: []
  user_choices:
    - decision_key: "llm_provider"
      answer: "Anthropic Claude 단일 + 운영자 키 서버측 env"
      source: "intake AskUserQuestion 2026-07-11 (D02)"
    - decision_key: "tech_stack"
      answer: "Python + FastAPI + 바닐라 HTML/JS 채팅 페이지"
      source: "intake AskUserQuestion 2026-07-11 (D03)"
    - decision_key: "rubric_gap_resolution"
      answer: "이번 task 한정 (explicit defer)"
      source: "intake AskUserQuestion 2026-07-11 (D04)"
    - decision_key: "rate_limit_unit"
      answer: "대화 세션 5회/시간/IP"
      source: "spec purpose review needs_user 해소 2026-07-11 (D05)"
    - decision_key: "sc5_scope"
      answer: "실배포 실행+실환경 검증까지 이번 task 포함 (Phase 8 intervention 사용자 참여)"
      source: "spec purpose review needs_user 해소 2026-07-11 (D06)"
    - decision_key: "default_model"
      answer: "claude-haiku-4-5 (MODEL env로 교체 가능)"
      source: "spec judge needs_user 해소 2026-07-11 (D07)"
    # --- phase-add 델타 (Phase 9, 2026-07-11) — 기존 항목 무수정, append만 ---
    - decision_key: "intake_persona_injection"
      answer: "knowledge/_persona.md — `_` 접두 파일 검색 제외 + 시스템 프롬프트 선두 결합, 부재 시 프리앰블 폴백"
      source: "phase-add AskUserQuestion 2026-07-11 (D08)"
    - decision_key: "intake_summary_storage"
      answer: "포함 — MAX_TURNS 도달 시 role=intake_summary 턴으로 구조화 요약 저장"
      source: "phase-add AskUserQuestion 2026-07-11 (D09)"
  deferrals:
    - decision_key: "hosting_platform"
      reason: "사용자 답변(2026-07-11): 배포 플랫폼은 이후 결정할 예정. 후보 4종(Railway Hobby/Fly.io/Oracle Free VM/Hetzner)으로 압축, Phase 8 진입 시 GM1 needs_user로 확정"
  unresolved_load_bearing_offers: []
  stale_or_missing_rubric_candidates:
    - decision_class: "hosting_platform"
      reason: "missing_rubric — 이번 task 한정 처리로 explicit defer (D04)"
      source_policy: "official_docs_first"
      canonical_status: missing
      author_or_defer_state: explicit_defer
      rubric_id: ""
    - decision_class: "llm_provider_and_key_custody"
      reason: "missing_rubric — 이번 task 한정 처리로 explicit defer (D04)"
      source_policy: "official_docs_first"
      canonical_status: missing
      author_or_defer_state: explicit_defer
      rubric_id: ""
    - decision_class: "tech_stack"
      reason: "missing_rubric — 이번 task 한정 처리로 explicit defer (D04)"
      source_policy: "official_docs_first"
      canonical_status: missing
      author_or_defer_state: explicit_defer
      rubric_id: ""
  provenance:
    decisions_file: "docs/planning/lmwiki-chatbot-proto/decisions.md"
    matched_rubric_ids: []
    suppressed_reasons: []
  finalization_audit: true
```

## Goal Decomposition

```yaml
goal_items:
  - id: G1
    source: "작동하는 텍스트 챗봇 프로토타입 (origin §1,2)"
    decomposed_to: [SC1, SC7]
  - id: G2
    source: "지식 데이터 교체 가능한 구조 (origin §3)"
    decomposed_to: [SC2]
  - id: G3
    source: "JSON→SQLite 경량 저장 구조 (origin §4)"
    decomposed_to: [SC3]
  - id: G4
    source: "사용량·공격 방지 + 보안 검토 (origin §6)"
    decomposed_to: [SC4, SC6]
  - id: G5
    source: "저비용/무료 호스팅 실배포 (origin §5)"
    decomposed_to: [SC5]
scope_deferrals: []
```

## Success Criteria Coverage

```yaml
success_criteria:
  - id: SC1
    criterion: "10턴 미만 텍스트 대화가 동작하고 11번째 발화가 거부된다"
    cap_refs: [CAP01, CAP03, CAP04]
    covered_by: [GM3, GM13]
  - id: SC2
    criterion: "로직 무수정으로 지식 디렉토리 교체 시 다른 도메인 챗봇으로 전환된다"
    cap_refs: [CAP02, CAP05, CAP06, CAP07]
    covered_by: [GM6]
  - id: SC3
    criterion: "대화가 JSON으로 저장되고 일 1회 배치가 SQLite에 멱등 적재한다"
    cap_refs: [CAP08, CAP09]
    covered_by: [GM9, GM10]
  - id: SC4
    criterion: "동일 IP 1시간 5회(대화 세션) 제한과 일일 총량 캡이 실제 집행된다"
    cap_refs: [CAP13]
    covered_by: [GM4, GM11]
  - id: SC5
    criterion: "확정된 저비용 플랫폼 실배포에서 공개 URL·저장·배치·rate limit이 검증된다"
    cap_refs: [CAP11, CAP12]
    covered_by: [GM1, GM2]
  - id: SC6
    criterion: "배포 전 AI 보안 검토가 수행·기록되고 high/critical이 수정된다"
    cap_refs: [CAP14]
    covered_by: [GM5, GM7]
  - id: SC7
    criterion: "Anthropic API를 서버측 env 키로 호출한다"
    cap_refs: [CAP10]
    covered_by: [GM13, GM8]
```

## Failure Path Seeds

```yaml
failure_paths:
  - id: FP1
    scenario: "배포 플랫폼의 ephemeral 파일시스템으로 JSON/SQLite 데이터 유실"
    impact: "저장 구조 전체 무효화, 대화 기록 소실"
    mapped_gates: [GM1, GM2]
  - id: FP2
    scenario: "10턴 캡이 상수 선언만 되고 실제 차단이 없음"
    impact: "핵심 제약 미충족, 비용 증가"
    mapped_gates: [GM3]
  - id: FP3
    scenario: "rate limit 미집행 또는 XFF 스푸핑/오구성으로 우회·붕괴"
    impact: "API 비용 공격 노출 또는 전역 self-DoS"
    mapped_gates: [GM4, GM5]
  - id: FP4
    scenario: "지식이 프롬프트에 하드코딩되어 디렉토리 교체가 무의미"
    impact: "교체 가능 구조라는 핵심 목적 실패 (fake-satisfy)"
    mapped_gates: [GM6]
  - id: FP5
    scenario: "API 키가 리포/클라이언트에 노출"
    impact: "키 도용·비용 사고"
    mapped_gates: [GM7, GM8]
  - id: FP6
    scenario: "배치가 코드로만 존재하고 배포 환경에서 스케줄되지 않아 실행 안 됨"
    impact: "SQLite 적재 미동작 (fake-satisfy)"
    mapped_gates: [GM9, GM10]
  - id: FP7
    scenario: "봇/공격자가 세션을 대량 생성해 LLM 비용 폭주"
    impact: "비용 사고"
    mapped_gates: [GM11]
  - id: FP8
    scenario: "대화 저장 사실을 이용자에게 미고지"
    impact: "개인정보 취급 리스크"
    mapped_gates: [GM12]
  - id: FP9
    scenario: "SDK 사용 오류·키 미설정·의존성 미설치로 LLM 호출/검증 자체가 실패"
    impact: "챗봇 핵심 기능 불능 또는 클린 환경 검증 실패"
    mapped_gates: [GM13]
```

## Failure Path Gate Mapping

```yaml
gate_mappings:
  - id: GM1
    failure_path: FP1
    target_type: needs_user
    target:
      decision_id: "D01"
      question: "실배포 플랫폼을 Railway Hobby / Fly.io / Oracle Free VM / Hetzner 중 무엇으로 확정할까요? (영속 볼륨·크론·TRUST_PROXY_HOPS 구성이 플랫폼마다 다름)"
    rationale: "D01 explicit defer — Phase 8 진입 시 사용자 확정 필요"
  - id: GM2
    failure_path: FP1
    target_type: phase_checklist
    target:
      phase: 8
      checklist_text: "확정 플랫폼에 실배포 실행(사용자 개입: 플랫폼 확정 GM1 + 계정·과금 승인) 후 deploy/checklist.md 검증 항목 전부 확인 — 공개 URL 응답·JSON 저장·배치 수동 1회+SQLite·6번째 세션 차단 (사용자 확정 2026-07-11: 실배포까지 이번 task 범위)"
    rationale: "실배포 환경에서 저장·배치·rate limit 실동작을 사용자와 함께 검증 완결 (CAP11/CAP12) — 사용자가 실배포 포함을 명시 선택 (D06)"
  - id: GM3
    failure_path: FP2
    target_type: test
    target:
      file: tests/test_chat.py
      status: planned
      phase: 2
      checklist_text: "tests/test_chat.py: LLM mock으로 대화 루프·11번째 발화 거부·입력 검증 테스트 통과"
    rationale: "10턴 캡 실집행을 회귀 가능하게 고정"
  - id: GM4
    failure_path: FP3
    target_type: test
    target:
      file: tests/test_ratelimit.py
      status: planned
      phase: 4
      checklist_text: "tests/test_ratelimit.py: 6번째 세션 차단·윈도우 경과 후 해제·일일 캡·TRUST_PROXY_HOPS별 XFF 스푸핑 차단 테스트 통과"
    rationale: "rate limit 실집행·우회 차단 검증"
  - id: GM5
    failure_path: FP3
    target_type: phase_checklist
    target:
      phase: 7
      checklist_text: "AI 보안 검토: 키 노출·입력 검증·프롬프트 인젝션(지식 문서/사용자 입력 경계)·rate limit 우회(XFF 스푸핑)·저장 데이터 취급 점검 → docs/security-review.md 기록"
    rationale: "우회 경로를 보안 검토에서 재점검"
  - id: GM6
    failure_path: FP4
    target_type: test
    target:
      file: tests/test_swap_e2e.py
      status: planned
      phase: 6
      checklist_text: "tests/test_swap_e2e.py: 로직 무수정 상태에서 KNOWLEDGE_DIR=knowledge-alt 구동 시 다른 도메인 문서가 프롬프트 컨텍스트에 실림을 검증 (LLM mock)"
    rationale: "지식 스왑 실증 — CAP06 적대적 플래그 대응"
  - id: GM7
    failure_path: FP5
    target_type: phase_checklist
    target:
      phase: 7
      checklist_text: "리포 시크릿 스캔 통과 (git 히스토리 포함)"
    rationale: "키 노출 점검"
  - id: GM8
    failure_path: FP5
    target_type: phase_checklist
    target:
      phase: 1
      checklist_text: ".env.example에 ANTHROPIC_API_KEY/KNOWLEDGE_DIR/MODEL/TRUST_PROXY_HOPS/DAILY_REQUEST_CAP 명시, .gitignore에 .env·data/·.venv/ 포함"
    rationale: "키가 처음부터 리포 밖(env)에 있도록 구조화"
  - id: GM9
    failure_path: FP6
    target_type: test
    target:
      file: tests/test_storage_batch.py
      status: planned
      phase: 3
      checklist_text: "tests/test_storage_batch.py: 저장→적재→조회 왕복 + 멱등성 테스트 통과"
    rationale: "저장·적재 로직의 회귀 고정"
  - id: GM10
    failure_path: FP6
    target_type: phase_checklist
    target:
      phase: 8
      checklist_text: "deploy/README.md: 후보 4개 플랫폼별 배포 절차(볼륨 마운트·env 설정·TRUST_PROXY_HOPS 권장값·크론/스케줄 등록) — research.md 소스 기반"
    rationale: "배포 환경에서 배치가 실제 스케줄되도록 절차 명시 (CAP09 실동작)"
  - id: GM11
    failure_path: FP7
    target_type: phase_checklist
    target:
      phase: 4
      checklist_text: "전역 일일 요청 상한 env DAILY_REQUEST_CAP(기본 500) — API 비용 방어"
    rationale: "IP 우회 공격에도 총량으로 비용 캡"
  - id: GM12
    failure_path: FP8
    target_type: phase_checklist
    target:
      phase: 5
      checklist_text: "대화 내용이 저장됩니다 고지 문구 표시"
    rationale: "저장 고지"
  - id: GM13
    failure_path: FP9
    target_type: verification
    target:
      phase: 2
      command: ".venv/bin/python -m pytest tests/test_chat.py -q"
    rationale: "SDK 연동 경로의 회귀 검증 (실키 호출은 Phase 8 env-gated 스모크와 GM2 배포 검증에서 확인)"
```

## Translation Baseline

```yaml
translation_baseline:
  status: not_required
  baseline_ref: ""
  files_subject_to_rewrite_or_translation: []
  semantic_review_categories:
    - must
    - must not
    - stop
    - escalate
    - needs_user
    - scope
    - guard
    - commit
    - fallback
    - structural-token invariance
  phase_10_input_source: ""
```

기존 프로토콜 텍스트의 in-place 언어 재작성·번역이 없는 신규 구현 task라 해당 없음.

## Claims

```yaml
claims:
  - id: P01-C1
    phase: 1
    kind: scope
    claim: "빈 신규 리포라 phase 1 scope의 모든 파일은 [NEW]이며 기존 코드와 충돌 없음. requirements.txt는 Phase 1에서 전체 의존성(fastapi/uvicorn/anthropic/pyyaml/pytest/httpx)을 선기재"
    evidence_refs: [E05, E06]
    confidence: verified
    load_bearing: false
  - id: P01-C2
    phase: 1
    kind: design
    claim: "마크다운+YAML 프론트매터 지식베이스, KNOWLEDGE_DIR env 교체 구조가 원 요청의 로직/콘텐츠 분리 제약을 충족"
    evidence_refs: [E01, E04]
    confidence: doc
    load_bearing: true
  - id: P02-C1
    phase: 2
    kind: design
    claim: "Anthropic Python SDK env 키 패턴으로 D02를 구현하며, 기본 모델은 D07 사용자 확정 claude-haiku-4-5 (MODEL env 교체 가능)"
    evidence_refs: [E07, E03]
    confidence: doc
    load_bearing: true
  - id: P02-C2
    phase: 2
    kind: verification
    claim: "10턴 캡·입력 검증은 .venv 환경의 LLM mock 테스트로 객관 판정 가능"
    evidence_refs: [E01]
    confidence: assumed
    load_bearing: true
  - id: P03-C1
    phase: 3
    kind: design
    claim: "JSON 파일 저장→일 1회 SQLite 적재는 실 파일시스템 전제이며, 유보된 배포 후보 4종 모두 이 전제를 충족"
    evidence_refs: [E02, E03]
    confidence: doc
    load_bearing: true
  - id: P04-C1
    phase: 4
    kind: design
    claim: "파일 영속(원자적 쓰기+락) 슬라이딩 윈도우 + TRUST_PROXY_HOPS env + 오구성 경고 + 일일 총량 캡으로 세션 5회/시간/IP 제한(D05)과 비용 공격 방어를 구현"
    evidence_refs: [E01, E03]
    confidence: assumed
    load_bearing: true
  - id: P05-C1
    phase: 5
    kind: scope
    claim: "static/ 마운트를 phase 2에서 미리 하므로 phase 5는 static 파일만 추가하며 phase 3/4와 scope 충돌 없음 (병렬 가능)"
    evidence_refs: [E06]
    confidence: assumed
    load_bearing: false
  - id: P06-C1
    phase: 6
    kind: verification
    claim: "KNOWLEDGE_DIR=knowledge-alt 교체 e2e와 MODEL=fake 전 구간 스모크로 지식 스왑 실증(CAP06)과 통합 동작(CAP03/08/09/13)을 로컬에서 판정"
    evidence_refs: [E04]
    confidence: assumed
    load_bearing: true
  - id: P07-C1
    phase: 7
    kind: risk
    claim: "보안 검토는 intake risks(키 노출·XFF 스푸핑·프롬프트 인젝션·저장 데이터)를 점검 대상으로 명시"
    evidence_refs: [E01]
    confidence: doc
    load_bearing: true
  - id: P08-C1
    phase: 8
    kind: risk
    claim: "실배포는 플랫폼 미정(D01 explicit defer)이므로 intervention_likely + needs_user 게이트가 필요하며, 자동 배포는 불가. 사용자는 실배포 참여를 명시 선택(D06)"
    evidence_refs: [E03]
    confidence: verified
    load_bearing: true
  - id: P08-C2
    phase: 8
    kind: e2e
    claim: "docs/e2e/ 카탈로그 부재로 e2e_refs는 전부 빈 값이며, 실패 경로는 로컬 테스트·스모크·needs_user·배포 체크리스트로 닫음"
    evidence_refs: [E06]
    confidence: verified
    load_bearing: false
```

## Critic Objections

2 라운드 수행. 1차 O1~O6 → 전부 revise/사용자 확정으로 해소, 2차에서 O1~O6 닫힘 확인 + 신규 O7 → revise 반영. 최종 미해결 objection 없음.

```yaml
objections:
  - id: O1
    claim_id: P02-C2
    lens: testing
    severity: warn
    confidence: 8
    basis: mechanical_fail
    objection: "검증 전 의존성 설치 단계 부재 — 클린 환경에서 pytest 검증 실패"
    proposed_action: revise
    resolution: "Phase 1에 .venv 생성+전체 의존성 설치 체크리스트 추가, 모든 검증 명령 .venv/bin/python 사용 (2차 크리틱 닫힘 확인)"
  - id: O2
    claim_id: P01-C1
    lens: architecture
    severity: warn
    confidence: 7
    basis: heuristic
    objection: "requirements.txt가 Phase 1 scope에만 있어 후속 phase 의존성 추가가 scope 밖 수정 강제"
    proposed_action: revise
    resolution: "Phase 1에서 전체 의존성 선기재 (2차 크리틱 닫힘 확인)"
  - id: O3
    claim_id: P04-C1
    lens: security
    severity: warn
    confidence: 7
    basis: heuristic
    objection: "XFF 1홉 고정 신뢰는 raw VM(0홉 직노출) 후보에서 스푸핑으로 rate limit 우회 가능"
    proposed_action: revise
    resolution: "TRUST_PROXY_HOPS env(기본 0) + 스푸핑 차단 테스트 + deploy/README 플랫폼별 권장값 (2차 크리틱 닫힘 확인)"
  - id: O4
    claim_id: P04-C1
    lens: backend
    severity: warn
    confidence: 6
    basis: heuristic
    objection: "ratelimit.json read-modify-write 경합 — 락/원자적 쓰기/워커 수 고정 부재"
    proposed_action: revise
    resolution: "원자적 쓰기(tmp+rename)+프로세스 내 락+Dockerfile 워커 1 고정 (2차 크리틱 닫힘 확인)"
  - id: O5
    claim_id: P02-C1
    lens: backend
    severity: warn
    confidence: 6
    basis: product_decision
    objection: "기본 MODEL=claude-opus-4-8은 최고가 티어로 저비용·비용공격방어 목표와 상충"
    proposed_action: needs_user
    resolution: "사용자 확정(D07): 기본 claude-haiku-4-5, MODEL env 교체 가능"
  - id: O6
    claim_id: P02-C1
    lens: testing
    severity: info
    confidence: 6
    basis: risk_acceptance
    objection: "실 Anthropic 호출이 배포 시점에 처음 실행 — SDK 통합 결함 늦은 발견 위험"
    proposed_action: accept_risk
    resolution: "Phase 8 로컬 컨테이너 스모크에 env-gated 실모델 1회 호출 추가로 리스크 수용 대신 조기 검증으로 전환"
  - id: O7
    claim_id: P04-C1
    lens: security
    severity: warn
    confidence: 6
    basis: failure_path_missing
    objection: "PaaS 후보에서 TRUST_PROXY_HOPS=0 방치 시 전 클라이언트가 프록시 IP로 합쳐져 전역 self-DoS가 비가시적으로 발생"
    proposed_action: revise
    resolution: "Phase 4 오구성 경고 로그(hops=0인데 XFF 관측 시) + deploy/checklist.md에 플랫폼 권장값 확인·두 독립 클라이언트 카운트 검증 추가"
supplements:
  - claim_id: P03-C1
    lens: backend
    note: "research.md가 4개 후보 전부 영속 디스크+크론 가능 확인 — 파일시스템 전제 지지"
  - claim_id: P08-C1
    lens: architecture
    note: "raw VM 후보는 self-managed cron/OS 보안 — 배포는 intervention+needs_user 유지가 타당"
```

## Judge

1차 judge verdict는 needs_user(O5 모델 티어)였고, D07 확정+O1~O7 revise 후 최종 판정은 아래.

```yaml
verdict: pass
risk: low
issues: 0
top_issue: "none"
required_action: "phase-init may create planning/spec files — all objections O1–O7 closed, purpose review pass, D01–D07 settled"
appeal_allowed: false
claim_rulings:
  - claim_id: P02-C2
    ruling: upheld
    objection_ids: [O1]
    reason: "Phase 1 venv+전체 의존성 선기재 및 모든 검증이 .venv/bin/python으로 전환되어 클린 환경 mechanical_fail 해소."
  - claim_id: P01-C1
    ruling: upheld
    objection_ids: [O2]
    reason: "requirements.txt에 전체 의존성 선기재로 Phase 2+ scope-외 수정 강제 제거."
  - claim_id: P04-C1
    ruling: upheld
    objection_ids: [O3, O4, O7]
    reason: "TRUST_PROXY_HOPS env(기본0)+오구성 경고 로그·원자적 쓰기+락+단일 워커·두 독립 클라이언트 검증으로 스푸핑/파손/무형 붕괴 경로 모두 닫힘."
  - claim_id: P02-C1
    ruling: upheld
    objection_ids: [O5, O6]
    reason: "기본 모델이 D07(claude-haiku-4-5)로 확정되어 저비용 목표와 정합, Phase 8 env-gated 실키 스모크로 SDK 통합 조기 검증 추가."
```

## Triage

`spec_review_triage.py` 2회 실행 (입력: /tmp/phase-spec-review-lmwiki-chatbot-proto.json). 1차 action=needs_user(judge verdict) → 사용자 확정(D07)+revise 후 2차(최종):

```yaml
action: pass
appeal_claims: []
reasons:
  - "no blocking review condition"
deterministic_basis:
  - "default pass"
```

## Appeal

미사용 (appeal_claims 빈 값, appeal_allowed: false).

## Final Purpose Re-check

```yaml
final_purpose_recheck:
  status: pass
  rationale: "리뷰 중 수정(venv·모델 기본값·TRUST_PROXY_HOPS·원자적 쓰기·실키 스모크)은 실행 가능성·보안·비용 하드닝으로 SC1~SC7 커버리지를 보존·개선하며 새 missing goal/scope truncation/overclaim 없음."
  compared_to: revised_plan_ir
```

## Final Disposition

pass — 8-phase 플랜 렌더 승인. 사용자 결정 D01~D07 전부 기록·반영, objection O1~O7 전부 해소, 실패 경로 FP1~FP9는 GM1~GM13(planned test 4건·phase checklist 7건·verification 1건·needs_user 1건)으로 닫힘. E2E 카탈로그 부재로 e2e_refs는 빈 값이며 로컬 게이트가 대체한다. Phase 8은 intervention_likely로 사용자 개입(플랫폼 확정 GM1·계정·실배포 실행)이 예정되어 있다.
