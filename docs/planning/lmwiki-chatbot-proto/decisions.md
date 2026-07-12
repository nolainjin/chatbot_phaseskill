---
task: lmwiki-chatbot-proto
created: 2026-07-11
decision_count: 10
---

# LM Wiki 챗봇 프로토타입 — Decisions

## Decisions

```yaml
decisions:
  - id: D01
    kind: DECISION_OFFER
    rubric_id: ""
    decision_class: "hosting_platform"
    decision_key: "hosting_platform"
    question: "저비용/무료 조건에서 JSON 저장 + SQLite + 일 1회 배치가 실제로 도는 배포 플랫폼을 무엇으로 할까?"
    options:
      - label: "Railway Hobby ($5/월 고정) (권장)"
        recommended: true
        tradeoff: "영속 볼륨 + 내장 Cron Schedule + spin-down 없음. 설정이 가장 쉬워 10일 데드라인에 가장 안전. 무료는 아님."
      - label: "Fly.io (월 $5~10)"
        tradeoff: "Volumes $0.15/GB·월 + 머신 초 단위 과금. Dockerfile 배포. 크론은 스케줄 머신/외부 트리거로 우회 — Railway보다 설정 손이 감."
      - label: "Oracle Always Free VM ($0)"
        tradeoff: "유일한 영구 무료 + 영속 디스크 200GB. 실제 VM이라 제약 없음. 대신 서버 세팅·보안 자가 관리 + 2026-06 스펙 무공지 축소 전례(정책 리스크)."
      - label: "Hetzner CX23 VPS (€5.49/월)"
        tradeoff: "플랫폼 제약 제로(표준 리눅스). OS·보안 패치 직접 부담. 유럽 리전 기준 가격."
    default: "Railway Hobby ($5/월 고정)"
    provenance:
      source_type: research
      source_refs:
        - "docs/planning/lmwiki-chatbot-proto/research.md"
        - "https://docs.railway.com/pricing/plans"
        - "https://fly.io/docs/about/pricing/"
        - "https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm"
        - "https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/"
      last_reviewed: "2026-07-11"
      volatility: high
      refresh_required: false
    needs_research: false
    blocks_phase_init: false
    status: deferred
    accepted_default: ""
    answer: ""
    author_or_defer_state: explicit_defer
    reason: "사용자 답변(2026-07-11): 배포 플랫폼은 이후 결정할 예정. 후보는 research.md 4종(Railway/Fly.io/Oracle Free VM/Hetzner)으로 압축됐고 배포 phase 전 확정. 그때까지 구현은 플랫폼 비종속(파일시스템+크론 전제)으로 진행"

  - id: D02
    kind: DECISION_OFFER
    rubric_id: ""
    decision_class: "llm_provider_and_key_custody"
    decision_key: "llm_provider"
    question: "외부 AI 모델은 어느 제공사로 시작하고, API 키는 어떻게 관리할까?"
    options:
      - label: "Anthropic Claude 단일 + 운영자 키 서버측 env (권장)"
        recommended: true
        tradeoff: "가장 단순. 키는 서버 환경변수로만 보관해 노출 위험 최소. 모델·키를 env로 빼두면 나중에 교체 여지도 남음."
      - label: "OpenAI 단일 + 운영자 키 서버측 env"
        tradeoff: "동일 구조. 제공사 선호 차이일 뿐 구현 난이도 동일."
      - label: "멀티 프로바이더 추상화 레이어"
        tradeoff: "지식 교체 철학과 어울리지만 프로토타입 10일 일정에 불필요한 복잡도. 추후 과제로 미루는 것을 권장."
    default: "Anthropic Claude 단일 + 운영자 키 서버측 env"
    provenance:
      source_type: missing_rubric
      source_refs: ["docs/planning/lmwiki-chatbot-proto/origin.md §4"]
      last_reviewed: "2026-07-11"
      volatility: medium
      refresh_required: false
    needs_research: false
    blocks_phase_init: true
    status: answered
    accepted_default: ""
    answer: "Anthropic Claude 단일 + 운영자 키 서버측 env"
    author_or_defer_state: explicit_defer
    reason: "사용자 D04 선택(2026-07-11): 이번 task 한정 처리, 재사용 rubric 등록 유보"

  - id: D03
    kind: DECISION_OFFER
    rubric_id: ""
    decision_class: "tech_stack"
    decision_key: "tech_stack"
    question: "구현 스택은 무엇으로 할까? (두찬님이 직접 구현하므로 본인 손에 맞는 것이 중요)"
    options:
      - label: "Python + FastAPI + 바닐라 HTML/JS 채팅 페이지 (권장)"
        recommended: true
        tradeoff: "sqlite3·json 표준 라이브러리로 저장 구조가 공짜. rate limit 미들웨어도 단순. 프론트는 정적 페이지 1장이면 충분."
      - label: "Node.js + Express"
        tradeoff: "JS 단일 언어. better-sqlite3 등 의존성 추가 필요. 배치 스케줄링은 동일하게 호스트 크론 의존."
      - label: "Next.js 풀스택"
        tradeoff: "claude_design에서 써본 스택이지만 서버 파일 쓰기·SQLite·크론이 서버리스 모델과 상성이 나빠 이번 저장 구조엔 부적합."
    default: "Python + FastAPI + 바닐라 HTML/JS 채팅 페이지"
    provenance:
      source_type: missing_rubric
      source_refs: ["docs/planning/lmwiki-chatbot-proto/origin.md §4, §7"]
      last_reviewed: "2026-07-11"
      volatility: low
      refresh_required: false
    needs_research: false
    blocks_phase_init: true
    status: answered
    accepted_default: ""
    answer: "Python + FastAPI + 바닐라 HTML/JS 채팅 페이지"
    author_or_defer_state: explicit_defer
    reason: "사용자 D04 선택(2026-07-11): 이번 task 한정 처리, 재사용 rubric 등록 유보"

  - id: D04
    kind: DECISION_OFFER
    rubric_id: ""
    decision_class: "canonical_rubric_gap_resolution"
    decision_key: "rubric_gap_resolution"
    question: "위 세 결정(hosting_platform, llm_provider_and_key_custody, tech_stack)은 재사용 rubric이 없는 클래스다. 이번 답변을 재사용 rubric으로 등록할까, 이번 task 한정으로 둘까?"
    options:
      - label: "이번 task 한정 (explicit defer) (권장)"
        recommended: true
        tradeoff: "가볍다. 다음 유사 프로젝트에서 같은 질문이 다시 나올 수 있음. front gate는 defer 사유 기록으로 해소."
      - label: "재사용 rubric 3건 등록 (author)"
        tradeoff: "다음 챗봇/배포 프로젝트에서 자동 제안됨. 단 rubric 초안 3건 검토·승인 절차가 지금 추가됨."
    default: "이번 task 한정 (explicit defer)"
    provenance:
      source_type: missing_rubric
      source_refs: ["decision_rubrics.py front_gate_block 2026-07-11"]
      last_reviewed: "2026-07-11"
      volatility: low
      refresh_required: false
    needs_research: false
    blocks_phase_init: true
    status: answered
    accepted_default: ""
    answer: "이번 task 한정 (explicit defer)"

  - id: D05
    kind: DECISION_OFFER
    rubric_id: ""
    decision_class: "rate_limit_semantics"
    decision_key: "rate_limit_unit"
    question: "'IP당 1시간 5회'의 단위는? (phase-init purpose review에서 승격된 질문)"
    options:
      - label: "대화 세션 5회 (권장)"
        recommended: true
        tradeoff: "상담형 UX 자연스러움, 세션당 최대 10턴으로 비용 캡"
      - label: "메시지 5건"
        tradeoff: "엄격하나 대화 한 번이면 소진 — UX 충돌"
      - label: "세션 5회 + 메시지 총량 병행"
        tradeoff: "이중 방어, 구현 추가"
    default: "대화 세션 5회"
    provenance:
      source_type: repo_local
      source_refs: ["spec purpose review 2026-07-11", "docs/planning/lmwiki-chatbot-proto/origin.md §6"]
      last_reviewed: "2026-07-11"
      volatility: low
      refresh_required: false
    needs_research: false
    blocks_phase_init: true
    status: answered
    accepted_default: ""
    answer: "대화 세션 5회"

  - id: D06
    kind: DECISION_OFFER
    rubric_id: ""
    decision_class: "deployment_scope"
    decision_key: "sc5_scope"
    question: "SC5(실배포 검증)를 이번 task에서 어디까지 완결할까? (실배포는 계정·과금 승인 필요)"
    options:
      - label: "실배포까지 함께 (권장)"
        recommended: true
        tradeoff: "Phase 8 intervention에서 사용자 참여로 실배포+실환경 검증 완결. 원 요청 그대로"
      - label: "배포 준비물까지만"
        tradeoff: "실배포는 후속 세션 — SC5 공식 축소 필요"
    default: "실배포까지 함께"
    provenance:
      source_type: repo_local
      source_refs: ["spec purpose review 2026-07-11", "docs/planning/lmwiki-chatbot-proto/capabilities.md CAP11/CAP12"]
      last_reviewed: "2026-07-11"
      volatility: low
      refresh_required: false
    needs_research: false
    blocks_phase_init: true
    status: answered
    accepted_default: ""
    answer: "실배포까지 함께"

  - id: D07
    kind: DECISION_OFFER
    rubric_id: ""
    decision_class: "llm_model_tier"
    decision_key: "default_model"
    question: "챗봇 기본 모델 티어는? (spec critic O5에서 승격 — MODEL env로 교체 가능)"
    options:
      - label: "Haiku 4.5 (권장)"
        recommended: true
        tradeoff: "$1/$5 최저가 — 지식기반 짧은 Q&A에 충분, 비용 공격 노출 최소"
      - label: "Sonnet 5"
        tradeoff: "$3/$15 — 품질·비용 균형"
      - label: "Opus 4.8"
        tradeoff: "$5/$25 — 최고 품질, 비용 노출 최대"
    default: "Haiku 4.5"
    provenance:
      source_type: research
      source_refs: ["claude-api 번들 스킬 (cached 2026-06-24) 모델 가격표", "spec critic O5 2026-07-11"]
      last_reviewed: "2026-07-11"
      volatility: medium
      refresh_required: false
    needs_research: false
    blocks_phase_init: true
    status: answered
    accepted_default: ""
    answer: "Haiku 4.5 (claude-haiku-4-5)"

  - id: D08
    kind: DECISION_OFFER
    rubric_id: ""
    decision_class: "intake_persona_injection"
    decision_key: "intake_persona_injection"
    question: "접수 면담 페르소나(면담 주도 지시문)를 어디에 둘까? (Phase 6 지식/로직 분리 invariant을 깨지 않아야 함)"
    options:
      - label: "knowledge/_persona.md (권장)"
        recommended: true
        tradeoff: "`_` 접두 파일은 검색 제외 + 존재 시 시스템 프롬프트 선두 결합. 지식셋 스왑 시 페르소나도 함께 스왑, 부재 시 기존 Q&A 프리앰블 폴백 — invariant 보존, 코드 수정 최소."
      - label: "PERSONA_FILE 환경변수"
        tradeoff: "지식과 페르소나 독립 교체 가능하나 설정 항목·배포 문서 갱신 부담."
      - label: "chat.py 직접 작성"
        tradeoff: "가장 단순하나 지식/로직 분리 invariant 파괴 — Phase 6 스왑 검증과 충돌."
    default: "knowledge/_persona.md"
    provenance:
      source_type: user
      source_refs: ["phase-add AskUserQuestion 2026-07-11"]
      last_reviewed: "2026-07-11"
      volatility: low
      refresh_required: false
    needs_research: false
    blocks_phase_init: false
    status: answered
    accepted_default: ""
    answer: "knowledge/_persona.md — `_` 접두 검색 제외 + 부재 시 프리앰블 폴백"

  - id: D09
    kind: DECISION_OFFER
    rubric_id: ""
    decision_class: "intake_summary_storage"
    decision_key: "intake_summary_storage"
    question: "면담 종료(10턴 도달) 시 접수 요약을 구조화해서 저장할까?"
    options:
      - label: "이번 phase는 제외 (권장)"
        recommended: true
        tradeoff: "대화 원문이 전부 저장되므로 요약은 나중에 배치로도 추출 가능 — YAGNI."
      - label: "포함"
        tradeoff: "면담 종료 시 구조화 요약 생성·저장. 실모델 호출 1회 추가 비용, 저장 스키마에 role 값 추가."
    default: "이번 phase는 제외"
    provenance:
      source_type: user
      source_refs: ["phase-add AskUserQuestion 2026-07-11"]
      last_reviewed: "2026-07-11"
      volatility: low
      refresh_required: false
    needs_research: false
    blocks_phase_init: false
    status: answered
    accepted_default: ""
    answer: "포함 — MAX_TURNS 도달 시 role=\"intake_summary\" 턴으로 구조화 요약 저장 (사용자가 권장 대신 포함 선택)"

  - id: D10
    kind: DECISION_OFFER
    rubric_id: ""
    decision_class: "interview_sequencing"
    decision_key: "interview_sequencing"
    question: "10턴 면담의 단계별 질문을 미리 정의해 순차 진행하는 방식을 어떻게 구현할까?"
    options:
      - label: "대화형 순차 진행 (권장)"
        recommended: true
        tradeoff: "단계 스크립트를 매 턴 시스템 프롬프트에 주입, 봇이 공감+단계 질문을 자연스럽게 수행. 대화 느낌 유지 + 단계 누락 방지."
      - label: "단계 라벨 + 대화형"
        tradeoff: "위와 동일하되 UI에 현재 단계 표시 — 투명하나 UI 변경 추가."
      - label: "설문형 UI"
        tradeoff: "질문 고정 표시, 예측 가능성 최대지만 라포 형성 원칙과 멀어짐."
    default: "대화형 순차 진행"
    provenance:
      source_type: user
      source_refs: ["phase-add AskUserQuestion 2026-07-11"]
      last_reviewed: "2026-07-11"
      volatility: low
      refresh_required: false
    needs_research: false
    blocks_phase_init: false
    status: answered
    accepted_default: ""
    answer: "대화형 순차 진행 — knowledge/_script.md 단계 스크립트 + 매 턴 단계 지시 주입, 부재 시 폴백. fake 모드는 단계 예시 질문 반환"
```

## Notes

- Keep this file in the same task directory packet as `request.json`, `intake.md`, and `research.md`; registry reruns should read sibling artifacts from `docs/planning/lmwiki-chatbot-proto/`.
- non-LB 파생 클래스 2건(`rate_limit_semantics`, `knowledge_retrieval_strategy`)은 flood-control 규칙에 따라 여기 올리지 않음 — research.md의 Rubric Registry Gaps와 intake.md open questions에 기본값과 함께 기록.
- `blocks_phase_init: true` 근거: D01~D03은 아키텍처·저장 구조·배포 phase 구성을 지배하고, D04는 front_gate_block 해소에 필요.
- Accepted defaults, explicit answers, and local decision ledgers stay task-local. Do not auto-promote them to memory.
