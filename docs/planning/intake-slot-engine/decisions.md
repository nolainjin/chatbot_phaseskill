---
task: intake-slot-engine
created: 2026-07-11
decision_count: 2
---

# 슬롯 스키마 문진 엔진 + 상담 접수면담 데모 — Decisions

## Decisions

```yaml
decisions:
  - id: D01
    kind: DECISION_OFFER
    rubric_id: "missing_rubric:schema_file_format"
    decision_class: "schema_file_format"
    decision_key: "intake_schema_file_format"
    question: "_intake_schema.md 안에서 슬롯 선언(공통/조건부/필수·선택/우선순위/레드플래그)을 어떤 형식으로 쓸까?"
    options:
      - label: "마크다운 + YAML 블록 (기계 파싱은 YAML 블록 하나, 주변 산문 자유)"
        recommended: true
        tradeoff: "리포에 yaml 파서 기존재(app/knowledge.py), 파싱 실패=형식 오류 판정 결정론적(폴백 invariant와 정합). 지식 작성자가 YAML 문법을 지켜야 함"
      - label: "마크다운 표"
        tradeoff: "사람이 읽기 쉬우나 표 파서 자체 구현 필요 + 형식 오류 경계 모호"
      - label: "산문 + LLM 해석"
        tradeoff: "작성 자유도 최고이나 완결성 기계 검증 불가, fake 모드에서 스키마 읽기 불가"
    default: "마크다운 + YAML 블록"
    provenance:
      source_type: missing_rubric
      source_refs: ["docs/planning/intake-slot-engine/request.json", "app/knowledge.py"]
      last_reviewed: "2026-07-11"
      volatility: low
      refresh_required: false
    needs_research: false
    blocks_phase_init: true
    status: answered
    accepted_default: ""
    answer: "YAML 블록 — 사용자 답변(2026-07-11). author_or_defer_state: explicit_defer (이번 task 한정, 재사용 rubric 등록 유보)"

  - id: D02
    kind: DECISION_OFFER
    rubric_id: "missing_rubric:slot_extraction_strategy"
    decision_class: "slot_extraction_strategy"
    decision_key: "real_mode_slot_extraction"
    question: "실모드에서 매 턴 슬롯 추출을 어떻게 할까? (API 호출 수 = 비용 직결)"
    options:
      - label: "단일 호출 통합 — 응답 생성 호출에 추출 지시 포함, 출력에서 응답/슬롯 JSON 분리"
        recommended: true
        tradeoff: "턴당 호출 1회 유지(비용 무증가). 프롬프트 복잡도 증가, 파싱 실패 턴은 추출 스킵(다음 턴 만회)"
      - label: "별도 추출 호출"
        tradeoff: "추출 정확도·책임 분리 명확하나 턴당 호출 2회 = 비용 2배(10턴 세션 최대 20회)"
    default: "단일 호출 통합"
    provenance:
      source_type: missing_rubric
      source_refs: ["docs/planning/intake-slot-engine/request.json", "app/llm.py", "app/chat.py"]
      last_reviewed: "2026-07-11"
      volatility: low
      refresh_required: false
    needs_research: false
    blocks_phase_init: true
    status: answered
    accepted_default: ""
    answer: "단일 호출 통합 — 사용자 답변(2026-07-11). author_or_defer_state: explicit_defer (이번 task 한정, 재사용 rubric 등록 유보)"
```

## Early CAP Confirmation (task-local evidence)

- 적대적 추출에서 플래그된 LB CAP 9종(CAP02/04/05/09/10/18/22/23/25) — 사용자 전부 확정(2026-07-11), 축소 없음. reductions 기록 불필요. capabilities.md의 Adversarial Flags 섹션이 phase 설계·리뷰 게이트의 강제 추적 목록.

## Notes

- registry 실행 이력: 1차(2026-07-11) front_gate_block.blocked=true (schema_file_format·slot_extraction_strategy missing_canonical) → 사용자 답변을 request.json resolved_decisions에 explicit_defer로 기록 → 2차 재실행 blocked=false, offers/suppressed/missing_canonical 모두 빈 배열. 핸드오프 개방.
- non-LB derived classes(fake_mode_slot_demo, red_flag_priority_semantics, turn_budget_semantics)는 origin 지시에서 의미 도출 가능 — 결정 패킷에 올리지 않고 phase-init 스펙 설계로 위임 (flood-control).
- D01·D02 답변은 task-local 계획 기록 — memory 승격 없음 (no-memory-promotion rule).
- Keep this file in the same task directory packet as `request.json`, `intake.md`, and `research.md`.
