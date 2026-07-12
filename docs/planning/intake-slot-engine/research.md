---
task: intake-slot-engine
created: 2026-07-11
research_status: skipped
---

# 슬롯 스키마 문진 엔진 + 상담 접수면담 데모 — Research

## Research Need Gate

```yaml
research:
  required: false
  reason: "전 항목이 리포 내부 구현으로 닫힌다. 엔진 변경(스키마 파서·프롬프트 주입·슬롯 추출·요약 JSON)은 기존 코드(app/chat.py, app/knowledge.py, app/llm.py, app/storage.py) 확장이고, 상담 스키마 슬롯 세부는 origin 지시대로 기존 knowledge/ 지식 6종에서 도출한다. 외부 API 동향·정책·과금·최신성 의존 결정 없음 — Anthropic SDK 사용 방식은 리포에 이미 확립(app/llm.py). 남은 불확실성은 /phase-init 리포 탐색으로 해소 가능."
  source_policy: official_docs_first
  queries: []
```

## Sources

```yaml
sources: []
```

## Findings

- research skipped — 리포 내부 증거로 충분. 외부 최신성이 계획에 load-bearing한 항목 없음.
- rubric registry (2026-07-11 실행): `schema_file_format`, `slot_extraction_strategy` 두 LB 클래스가 `canonical_status: missing` (registry에 도메인 rubric 없음) → front_gate_block. 두 클래스 모두 외부 research가 아니라 **사용자 판단**으로 해소하는 task-local 결정 — 부모 task(lmwiki-chatbot-proto)와 동일하게 `explicit_defer`(이번 task 한정 처리, 재사용 rubric 등록 유보)로 처리. 해소 결과는 `decisions.md`와 `request.json`의 `resolved_decisions`에 기록.
- non-LB 클래스(`fake_mode_slot_demo`, `red_flag_priority_semantics`, `turn_budget_semantics`)는 origin 지시에서 의미가 도출 가능 — 결정 패킷에 올리지 않고 phase-init 스펙 설계로 넘긴다.

## Remaining Uncertainty

- 없음 (외부 근거 관련). 리포 검증 필요 항목은 intake.md Handoff Notes 참조.
