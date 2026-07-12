---
task: intake-slot-engine
spec_review_version: 2
created: 2026-07-12
final_verdict: pass
risk: low
appeal_used: false
fallback_used: false
fallback_reason: ""
contamination_risk: ""
fallback_user_approved: false
---

# 슬롯 스키마 문진 엔진 + 상담 접수면담 데모 — Spec Review

## Active Lenses

architecture, testing, backend, security

## Evidence Ledger

```yaml
evidence_ledger:
  evidence_commit: "baa7f0ab0b8bfdd823a878060abd6478c5c2dfbc"
```

- E01 Read app/chat.py:57-100 — handle_message가 persona+[진행 n/10턴]+docs로 system 조립, MAX_TURNS=10, 반환 {reply,turn,limit_reached}, 10턴 도달 시 _SUMMARY_INSTRUCTION 요약을 role=intake_summary 저장(try/except 격리).
- E02 Read app/chat.py:31-46 — ChatSession(session_id,turns,history) 메모리 dict.
- E03 Read app/knowledge.py:30-70 — yaml.safe_load 프론트매터 파서 기존재; load_documents가 "_" 시작 파일 검색 제외.
- E04 Read app/llm.py:15-37 — ask(system,history,user,doc_titles,settings); fake 분기 "[fake] 참고 문서: <titles>" / "[fake] 관련 문서를 찾지 못했습니다."
- E05 Read app/storage.py:25-40 — append_turn {seq,role,text}, text=str → JSON 문자열 직렬화로 스키마 무변경. 평문 저장(암호화·마스킹 없음).
- E06 Read knowledge/_persona.md:7-15 — "면담 순서" 1~5 실재(소유권 충돌 실재); 비밀보장 원칙·예외는 목록 1번 항목 내부에만 존재(별도 섹션 없음 — critic 1차 O1 확인).
- E07 Read tests/test_intake.py:41-63 — "접수 면담" in system, "[진행: 1/10턴]" 단언, 페르소나 doc_titles 미포함 단언.
- E08 Read tests/test_intake.py:98-123 — test_summary_failure가 system == chat._SUMMARY_INSTRUCTION일 때만 raise하는 monkeypatch로 "요약 실패 격리" 검증 — 스키마 활성 시 요약이 llm.ask를 안 타 전제 붕괴 → 스키마-less 지식셋 이동 필요 (Phase 5 배치 — Phase 3~4 시점 미파괴, critic 확인).
- E09 Read tests/test_swap_e2e.py:35-46 — fake reply의 문서 제목 인용 단언(상담 목표 설정 방법/원두 보관법). tests/test_chat.py:27,33도 부분문자열 단언 — llm.py 무수정+접미사 방식으로 전부 보존(critic 실파일 대조 확인).
- E10 Bash ls — knowledge/ 상담 6종+_persona.md, knowledge-alt/ 커피 6종(스키마·페르소나 없음).
- E11 Read knowledge/위기-상황-스크리닝.md — 확인 항목: 자해·자살 생각/시도, 계획·수단, 타해, 약물·알코올, 지지체계 → 위기 트랙 슬롯 도출 근거(원문 실재, critic 확인).
- E12 Read knowledge/접수-면접-질문지-구성.md:16 — 개방형 첫 질문 원문 "오늘 상담을 받으러 오신 이유가 무엇인가요?" 실재; 경과·대처 시도·지지체계·기대 → 공통 슬롯 도출 근거.
- E13 Bash grep docs/planning/lmwiki-chatbot-proto/checklist.md:73 — `## Cross-Phase 메모` 섹션 실재, 'supersede' 문자열 0건 (CAP25 grep 검증 유효).
- E14 Bash tooling_readiness — sem=ready, engramx=missing(Read/Grep 폴백), ts_morph=missing(비-UI 리포 영향 없음), graph=missing, large_files=0.
- E15 Research(intake handoff) — research.md required:false(리포 내부로 닫힘); decisions.md D01=YAML 블록, D02=단일 호출 통합(사용자 답변 2026-07-11, explicit_defer).
- E16 Bash git rev-parse HEAD — baa7f0ab0b8bfdd823a878060abd6478c5c2dfbc.
- E17 Read app/config.py:8-23 — Settings.knowledge_dir(KNOWLEDGE_DIR env), model("fake" 스위치).
- E18 Read tests/test_intake.py:82-96 — intake_summary 1회 기록 role 카운트 단언(text 내용 무단언) — JSON 문자열 요약으로도 유지(critic 확인).
- E19 Grep tests/ app/ '비밀보장' — 단언 0건 (critic 1차 O1) → Phase 2 검증에 grep 게이트 신설(GM20).

## Memory Evidence

MemoryPacket 미사용 — 이번 계획은 현재 intake 패킷(intake.md/decisions.md/research.md/origin.md/capabilities.md)과 현재 리포 Read/Grep/Bash 증거만으로 닫힌다. 과거 메모리 클레임을 확정 사실로 렌더한 항목 없음.

## Purpose Review

1차 리뷰(6-phase 초안): verdict `revise` — CAP12(개방형 첫 질문) 주입 단언 누락 1건 → Phase 3 체크리스트·e2e 시나리오 ①에 단언 추가 후 재리뷰 `pass`. 아래는 재리뷰 결과에 최종 re-check까지 반영한 값.

```yaml
purpose_review:
  intended_outcomes:
    - "도메인 무관 슬롯 문진 엔진: _intake_schema.md YAML 선언(공통/조건부/필수·선택/우선순위/레드플래그) 파싱 + 부재·형식오류 시 기존 페르소나/Q&A 폴백 (CAP01/02/09)"
    - "매 턴 시스템 프롬프트에 채워진/미충족 슬롯(우선순위순)·턴 예산·개방형 첫 질문 주입 — 1턴 포함이 단위 테스트와 e2e 양쪽에서 단언 (CAP03/06/12)"
    - "한 발화 다중 슬롯 동시 추출(fake 결정론 + 실모드 D02 단일 호출 통합 + 신뢰 경계 검증)과 레드플래그 신호 감지 시 우선 질문 (CAP04/05/10)"
    - "10턴 종료 시 미확인 슬롯 포함 구조화 JSON intake_summary — 기존 role=intake_summary 경로 재사용, 저장 스키마 무변경 (CAP07/08/17)"
    - "상담 3-트랙(정서/관계/위기) 스키마가 기존 지식 6종에서 도출되어 knowledge/에 추가되고 _persona.md 소유권 정리 (CAP11/13/14)"
    - "fake e2e 4종(정서/관계/위기 레드플래그 우선 순서 단언/혼합 2슬롯 동시 단언) + knowledge-alt 스왑 회귀 + 전체 pytest (CAP18/20-24)"
    - "docs/demo-scenario.md(재활 3-트랙 프리뷰 + 지식 교체 시연) + README 링크 + 부모 checklist Phase 10(D10) supersede 메모 (CAP15/19/25)"
  goal_alignment:
    verdict: pass
    rationale: "25 CAP 전수 매핑 확인 — scope 축소(e2e 카탈로그 생략·데모 문서 위치·직렬 계획)는 전부 2026-07-12 사용자 명시 승인."
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
    rationale: "git ls-files '*CONTEXT.md' 결과 0건 — 리포에 tracked context 문서가 없어 selector 스킵. baseline missing / bootstrap 정책만 기록, phase-init은 context 문서를 생성하지 않음."
```

## Source Blueprint

해당 없음 — 이 task는 blueprint 핸드오프가 아니라 `/phase-intake` 산출물(`docs/planning/intake-slot-engine/intake.md`) 핸드오프로 생성됨. `source_blueprint` 블록 생략.

## Decision Surface

```yaml
decision_surface:
  status: present
  source_mode: registry_rerun
  source_artifact: "docs/planning/intake-slot-engine/request.json"
  source_command: "python3 skills/phase-intake/scripts/decision_rubrics.py --request-file docs/planning/intake-slot-engine/request.json --decisions-file docs/planning/intake-slot-engine/decisions.md --pretty"
  freshness: fresh
  no_memory_promotion: true
  accepted_defaults: []
  user_choices:
    - decision_key: "intake_schema_file_format"
      answer: "마크다운 + YAML 블록 1개 — 파싱 실패 = 형식 오류 = 폴백 (D01)"
      source: "decisions.md D01, 사용자 답변 2026-07-11"
    - decision_key: "real_mode_slot_extraction"
      answer: "단일 호출 통합 — 응답 호출에 추출 지시 포함, 출력에서 응답/슬롯 JSON 분리, 파싱 실패 턴 스킵 (D02)"
      source: "decisions.md D02, 사용자 답변 2026-07-11"
    - decision_key: "e2e_catalog_bootstrap"
      answer: "카탈로그 없이 진행 — e2e_refs/e2e_triggers 빈 값, e2e 4종은 pytest(tests/test_slot_e2e.py)로 강제"
      source: "사용자 답변 2026-07-12 (phase-init)"
    - decision_key: "demo_doc_location"
      answer: "docs/demo-scenario.md + README 링크"
      source: "사용자 답변 2026-07-12 (phase-init)"
  deferrals: []
  unresolved_load_bearing_offers: []
  stale_or_missing_rubric_candidates:
    - decision_class: "schema_file_format"
      reason: "registry에 도메인 rubric 없음(missing_canonical) — 사용자 답변으로 task-local 해소, 재사용 rubric 등록 유보"
      source_policy: "official_docs_first"
      canonical_status: missing
      author_or_defer_state: explicit_defer
      rubric_id: ""
    - decision_class: "slot_extraction_strategy"
      reason: "registry에 도메인 rubric 없음(missing_canonical) — 사용자 답변으로 task-local 해소, 재사용 rubric 등록 유보"
      source_policy: "official_docs_first"
      canonical_status: missing
      author_or_defer_state: explicit_defer
      rubric_id: ""
  provenance:
    decisions_file: "docs/planning/intake-slot-engine/decisions.md"
    matched_rubric_ids: []
    suppressed_reasons: []
  finalization_audit: false
```

## Goal Decomposition

```yaml
goal_items:
  - id: G1
    source: "origin §2 엔진 요구 (도메인 무관 슬롯 엔진)"
    decomposed_to: [SC1, SC2, SC3]
  - id: G2
    source: "origin §3 상담 접수면담 스키마 + 페르소나 소유권"
    decomposed_to: [SC4]
  - id: G3
    source: "origin §1/§3 의사 시연 데모 (재활 프리뷰·지식 교체 시연)"
    decomposed_to: [SC5]
  - id: G4
    source: "origin §4 제약 (API·rate·저장·폴백 무변경)"
    decomposed_to: [SC6, SC7]
  - id: G5
    source: "origin §5 검증 (fake e2e 4종 + 전체 pytest)"
    decomposed_to: [SC8]
  - id: G6
    source: "origin §1 Phase 10(D10) supersede 기록"
    decomposed_to: [SC9]
scope_deferrals: []
```

## Success Criteria Coverage

```yaml
success_criteria:
  - id: SC1
    criterion: "스키마 선언 파싱 + 부재·형식오류 시 기존 Q&A/페르소나 폴백"
    cap_refs: [CAP01, CAP09]
    covered_by: [GM1, GM15]
  - id: SC2
    criterion: "매 턴 주입·조건부 활성·다중 추출·레드플래그 우선·턴 예산·개방형 첫 질문 + 실모드 추출 신뢰 경계"
    cap_refs: [CAP02, CAP03, CAP04, CAP05, CAP06, CAP12]
    covered_by: [GM2, GM3, GM4, GM11, GM13, GM21, GM23]
  - id: SC3
    criterion: "구조화 JSON 요약 + 미확인 표기"
    cap_refs: [CAP07, CAP08]
    covered_by: [GM8]
  - id: SC4
    criterion: "3-트랙 스키마 지식 6종 정합 + 페르소나 소유권 정리·비밀보장 보존"
    cap_refs: [CAP11, CAP13, CAP14]
    covered_by: [GM16, GM17, GM20]
  - id: SC5
    criterion: "fake 모드 전체 시연 + 데모 문서(재활 3-트랙 프리뷰·지식 교체 시연)"
    cap_refs: [CAP10, CAP15, CAP19]
    covered_by: [GM5, GM18]
  - id: SC6
    criterion: "API 계약·저장 스키마·rate limit 무변경"
    cap_refs: [CAP16, CAP17]
    covered_by: [GM14, GM10]
  - id: SC7
    criterion: "knowledge-alt 스왑 Q&A 폴백 회귀 없음"
    cap_refs: [CAP18]
    covered_by: [GM6, GM7]
  - id: SC8
    criterion: "fake e2e 4종 + 전체 pytest 통과"
    cap_refs: [CAP20, CAP21, CAP22, CAP23, CAP24]
    covered_by: [GM4, GM5, GM19]
  - id: SC9
    criterion: "부모 checklist에 Phase 10(D10) supersede 기록"
    cap_refs: [CAP25]
    covered_by: [GM12]
```

## Failure Path Seeds

```yaml
failure_paths:
  - id: FP1
    scenario: "스키마 YAML 형식 오류가 None 폴백 대신 예외로 전파"
    impact: "스키마 오류 하나로 대화 전체 다운 — CAP09 위반"
    mapped_gates: [GM1]
  - id: FP2
    scenario: "조건부 슬롯을 선언만 하고 활성 트리거 미배선"
    impact: "트랙=위기에서 자해 계획·수단 미질문 (CAP02 어드버서리얼)"
    mapped_gates: [GM2]
  - id: FP3
    scenario: "다중 추출이 항상 1슬롯만 채우며 다중 지원으로 위장"
    impact: "CAP04/23 fake-satisfy"
    mapped_gates: [GM3]
  - id: FP4
    scenario: "레드플래그 선언만 되고 우선 질문 미발동"
    impact: "위기 신호 후순위 처리 (CAP05/22 어드버서리얼)"
    mapped_gates: [GM4]
  - id: FP5
    scenario: "fake 모드가 슬롯 흐름을 안 태우고 고정 응답으로 시연 가능 위장"
    impact: "의사 시연 불가 (CAP10 어드버서리얼)"
    mapped_gates: [GM5]
  - id: FP6
    scenario: "fake reply 형식 변경으로 test_swap_e2e 인용 단언·knowledge-alt 폴백 회귀"
    impact: "Phase 6 스왑 invariant 파괴 (CAP18)"
    mapped_gates: [GM6, GM7]
  - id: FP7
    scenario: "요약이 LLM 경유로 남아 미확인 누락·비결정, 또는 text에 비문자열 저장"
    impact: "CAP07/08/17 위반"
    mapped_gates: [GM8]
  - id: FP8
    scenario: "test_summary_failure 전제(요약=LLM 호출) 붕괴로 기존 스위트 실패"
    impact: "전체 pytest 실패 — 회귀로 오판"
    mapped_gates: [GM9]
  - id: FP9
    scenario: "위기 슬롯 민감정보가 신규 저장 표면으로 확대"
    impact: "부모 Phase 7 저장 데이터 점검 무력화"
    mapped_gates: [GM10]
  - id: FP10
    scenario: "실모드 슬롯 JSON 파싱 실패가 사용자 응답 자체를 파괴"
    impact: "실모드 대화 품질 저하·턴 유실"
    mapped_gates: [GM11]
  - id: FP11
    scenario: "코드 작업에 밀려 supersede 기록 조용히 누락"
    impact: "CAP25 어드버서리얼 — 부모 task 상태 불일치"
    mapped_gates: [GM12]
  - id: FP12
    scenario: "opening_question 주입이 조용히 깨져도 다른 검증은 전부 통과"
    impact: "CAP12 위반 — 첫 질문 개방형 보장 상실"
    mapped_gates: [GM13]
  - id: FP13
    scenario: "API 반환 필드·storage 호출 형태 변형"
    impact: "CAP16/17 위반 — UI·배치 파손"
    mapped_gates: [GM14]
  - id: FP14
    scenario: "_intake_schema.md가 Q&A 검색에 섞여 인용 오염"
    impact: "CAP01 예약 규칙 위반"
    mapped_gates: [GM15]
  - id: FP15
    scenario: "페르소나 정리로 '접수 면담' 단언 또는 비밀보장 안내 소실"
    impact: "test_intake 파손 + 페르소나 소유 영역 훼손 (CAP14)"
    mapped_gates: [GM16, GM20]
  - id: FP16
    scenario: "스키마 콘텐츠에 트랙 3종·조건부·레드플래그 선언 누락"
    impact: "CAP11/13 미충족"
    mapped_gates: [GM17]
  - id: FP17
    scenario: "데모 문서가 재활 프리뷰·지식 교체 시연 누락"
    impact: "CAP15/19 미충족"
    mapped_gates: [GM18]
  - id: FP18
    scenario: "국지 테스트만 돌아 전체 회귀 미검출"
    impact: "CAP24 위반"
    mapped_gates: [GM19]
  - id: FP19
    scenario: "파싱 성공한 비정상 슬롯 출력(미선언 id·비문자열·과길이)이 session.slots→프롬프트→요약 저장으로 증폭"
    impact: "LLM 신뢰 경계 붕괴·저장 오염"
    mapped_gates: [GM21]
  - id: FP20
    scenario: "위기 슬롯 민감정보가 구조화 JSON으로 기계판독 용이해진 채 평문 저장"
    impact: "유출 시 민감정보 추출 용이성 상승 (저장 표면은 기존과 동일)"
    mapped_gates: [GM22]
  - id: FP21
    scenario: "후속 발화가 기채움 슬롯(트랙 등)을 뒤집어 조건부 활성 상태 붕괴"
    impact: "위기 트랙 red_flag 슬롯 비활성화 — 우선 질문 소실"
    mapped_gates: [GM23]
```

## Failure Path Gate Mapping

```yaml
gate_mappings:
  - id: GM1
    failure_path: FP1
    target_type: test
    target:
      file: tests/test_intake_schema.py
      status: planned
      phase: 1
      checklist_text: "tests/test_intake_schema.py — 부재·YAML 오류·필수 키 누락 → None 폴백 3케이스 테스트"
    rationale: "형식 오류 → None 폴백을 결정론 단위 테스트로 고정"
  - id: GM2
    failure_path: FP2
    target_type: test
    target:
      file: tests/test_slot_flow.py
      status: planned
      phase: 3
      checklist_text: "tests/test_slot_flow.py — 조건부 활성 배선 단언: 트랙=위기 채움 시 자해 계획·수단 슬롯 활성 (CAP02)"
    rationale: "선언-트리거 배선을 직접 단언"
  - id: GM3
    failure_path: FP3
    target_type: test
    target:
      file: tests/test_slot_flow.py
      status: planned
      phase: 3
      checklist_text: "tests/test_slot_flow.py — fake 다중 추출 단언: 1발화에서 2슬롯 동시 충족 (CAP04)"
    rationale: "동시 충족을 개수 단언으로 강제"
  - id: GM4
    failure_path: FP4
    target_type: test
    target:
      file: tests/test_slot_e2e.py
      status: planned
      phase: 6
      checklist_text: "tests/test_slot_e2e.py — 위기 시나리오: 레드플래그 슬롯 우선 질문 순서 단언 (CAP22)"
    rationale: "우선 질문을 순서 단언으로 강제"
  - id: GM5
    failure_path: FP5
    target_type: test
    target:
      file: tests/test_slot_e2e.py
      status: planned
      phase: 6
      checklist_text: "tests/test_slot_e2e.py — 정서 시나리오: 1턴 opening_question 단언 + 요약 JSON track=정서 단언"
    rationale: "fake 흐름이 실제 슬롯 채움·요약까지 도달함을 내용 단언"
  - id: GM6
    failure_path: FP6
    target_type: test
    target:
      file: tests/test_swap_e2e.py
    rationale: "기존 스왑 인용 단언이 그대로 회귀 가드"
  - id: GM7
    failure_path: FP6
    target_type: test
    target:
      file: tests/test_slot_e2e.py
      status: planned
      phase: 6
      checklist_text: "tests/test_slot_e2e.py — knowledge-alt 스왑 회귀 단언: 진행 접미사 없음·기존 스텁 형식 유지 (CAP18)"
    rationale: "스키마 없는 지식셋에서 신규 흐름 미개입을 직접 단언"
  - id: GM8
    failure_path: FP7
    target_type: phase_checklist
    target:
      phase: 5
      checklist_text: "tests/test_intake.py — 요약 JSON 파싱 가능·미확인 필드 존재 단언 추가"
    rationale: "JSON 파싱·미확인 표기를 테스트로 고정"
  - id: GM9
    failure_path: FP8
    target_type: phase_checklist
    target:
      phase: 5
      checklist_text: "tests/test_intake.py — test_summary_failure를 스키마 없는 지식셋으로 이동해 레거시 요약 실패 격리 검증 유지"
    rationale: "레거시 경로 검증을 보존하며 전제 붕괴 해소"
  - id: GM10
    failure_path: FP9
    target_type: phase_checklist
    target:
      phase: 5
      checklist_text: "요약 저장은 기존 append_turn(role=intake_summary) 경로만 사용 — 신규 저장 표면 없음 확인"
    rationale: "민감정보 저장 표면 확대 차단"
  - id: GM11
    failure_path: FP10
    target_type: test
    target:
      file: tests/test_slot_extract.py
      status: planned
      phase: 4
      checklist_text: "tests/test_slot_extract.py — 실모드 슬롯 JSON 분리·파싱 실패 시 추출 스킵·응답 원문 유지 단언"
    rationale: "D02 파싱 실패 스킵 계약을 테스트로 고정"
  - id: GM12
    failure_path: FP11
    target_type: verification
    target:
      phase: 7
      command: "grep -n 'supersede' docs/planning/lmwiki-chatbot-proto/checklist.md"
    rationale: "기록 존재를 기계 확인"
  - id: GM13
    failure_path: FP12
    target_type: test
    target:
      file: tests/test_slot_flow.py
      status: planned
      phase: 3
      checklist_text: "tests/test_slot_flow.py — 1턴 시스템 프롬프트에 opening_question 포함 단언 (CAP12)"
    rationale: "purpose 리뷰 지적 갭 폐쇄"
  - id: GM14
    failure_path: FP13
    target_type: verification
    target:
      phase: 3
      command: "pytest -q"
    rationale: "기존 계약·스왑 테스트 전체 회귀로 무변경 확인"
  - id: GM15
    failure_path: FP14
    target_type: phase_checklist
    target:
      phase: 2
      checklist_text: "load_documents 검색 결과에 _intake_schema.md 미포함 확인"
    rationale: "예약 규칙 준수를 직접 확인"
  - id: GM16
    failure_path: FP15
    target_type: phase_checklist
    target:
      phase: 2
      checklist_text: "knowledge/_persona.md 소유권 정리 — 면담 순서 목록 제거, 태도·비밀보장·요약 형식 유지, '접수 면담' 문자열 보존"
    rationale: "단언 보존 조건을 체크리스트로 명시"
  - id: GM17
    failure_path: FP16
    target_type: phase_checklist
    target:
      phase: 2
      checklist_text: "knowledge/_intake_schema.md 작성 — 트랙 3종(정서/관계/위기)·공통 슬롯·조건부 슬롯·레드플래그·signals 선언, 기존 지식 6종과 정합"
    rationale: "스키마 필수 구성요소를 체크리스트로 강제"
  - id: GM18
    failure_path: FP17
    target_type: phase_checklist
    target:
      phase: 7
      checklist_text: "docs/demo-scenario.md 작성 — 시연 순서·재활 3-트랙(암재활/근골격/자율신경) 프리뷰 포인트·knowledge-alt 지식 교체 시연·민감정보 주의 포함"
    rationale: "데모 필수 3요소+주의를 체크리스트로 강제"
  - id: GM19
    failure_path: FP18
    target_type: verification
    target:
      phase: 6
      command: "pytest -q"
    rationale: "전체 스위트로 회귀 폐쇄"
  - id: GM20
    failure_path: FP15
    target_type: verification
    target:
      phase: 2
      command: "grep -q '^## 비밀보장' knowledge/_persona.md && grep -q '예외' knowledge/_persona.md"
    rationale: "별도 섹션 승격(헤딩)과 예외 열거 보존을 기계 검증 — 현행 파일은 헤딩이 없어 변경 전에는 실패한다"
  - id: GM21
    failure_path: FP19
    target_type: test
    target:
      file: tests/test_slot_extract.py
      status: planned
      phase: 4
      checklist_text: "tests/test_slot_extract.py — 비정상 슬롯 id·비문자열 값·과길이 값·기채움 덮어쓰기 폐기 단언 (신뢰 경계)"
    rationale: "화이트리스트·형·길이·덮어쓰기 검증을 테스트로 고정"
  - id: GM22
    failure_path: FP20
    target_type: accepted_risk
    target:
      risk_id: RISK-PII-STRUCTURED-SUMMARY
      risk: "위기 슬롯 민감정보가 구조화 JSON으로 평문 저장되어 기계판독 용이성 상승 (저장 표면은 기존 경로 재사용으로 무확대)"
      accepted_by: "user — origin verbatim §2 구조화 JSON 저장 지시(2026-07-11) + intake.md Risks 기표면화"
      rationale: "구조화 저장 자체가 사용자 명시 요구사항이며 잔여 위험은 intake에서 이미 표면화·수용됨"
    rationale: "구조화 저장 자체가 사용자 명시 요구사항이며 잔여 위험은 intake에서 이미 표면화·수용됨 — Phase 5 배경·영향 범위에 명기"
  - id: GM23
    failure_path: FP21
    target_type: test
    target:
      file: tests/test_slot_flow.py
      status: planned
      phase: 3
      checklist_text: "tests/test_slot_flow.py — 기채움 슬롯 덮어쓰기 금지 단언: 후속 발화가 트랙 값을 못 뒤집음"
    rationale: "덮어쓰기 금지 불변식을 fake 경로 테스트로 고정"
```

## Translation Baseline

not_required — 기존 프로토콜 텍스트의 언어 규칙 재작성·번역이 계획에 없다 (신규 지식 파일 작성과 페르소나 소유권 정리는 번역이 아닌 콘텐츠 재구성).

```yaml
translation_baseline:
  status: not_required
  baseline_ref: ""
  files_subject_to_rewrite_or_translation: []
  semantic_review_categories: []
  phase_10_input_source: ""
```

## Claims

```yaml
claims:
  - {id: P01-C1, phase: 1, kind: design, claim: "app/intake.py [NEW]에 _intake_schema.md 첫 YAML fenced 블록을 yaml.safe_load로 파싱하는 파서를 만든다 (D01 정합, yaml 선례 app/knowledge.py:38 실재)", evidence_refs: [E03, E15], confidence: verified, load_bearing: true}
  - {id: P01-C2, phase: 1, kind: design, claim: "파일 부재·블록 부재·YAML 오류·키 누락 전부 None 반환 = 폴백 신호, 예외 전파 금지 (CAP09)", evidence_refs: [E15], confidence: verified, load_bearing: true}
  - {id: P01-C3, phase: 1, kind: verification, claim: "tests/test_intake_schema.py [NEW]가 부재·형식오류 3케이스와 조건부 활성·정렬을 단위 검증", evidence_refs: [], confidence: assumed, load_bearing: true}
  - {id: P02-C1, phase: 2, kind: design, claim: "3-트랙 슬롯 세부는 기존 지식 6종에서 도출 — opening_question·위기 슬롯 원문 실재 확인 (CAP11/13)", evidence_refs: [E11, E12], confidence: verified, load_bearing: true}
  - {id: P02-C2, phase: 2, kind: design, claim: "_persona.md 면담 순서 목록 제거 + 비밀보장 원칙·예외를 별도 섹션으로 승격 유지 + '접수 면담' 문자열 보존, 강화 grep 검증 게이트 신설 (CAP14)", evidence_refs: [E06, E07, E19], confidence: verified, load_bearing: true}
  - {id: P02-C3, phase: 2, kind: design, claim: "_ 예약 규칙으로 스키마 파일이 Q&A 검색에 안 섞임 — 기존 knowledge 테스트 영향 없음 (CAP01)", evidence_refs: [E03], confidence: verified, load_bearing: true}
  - {id: P03-C1, phase: 3, kind: design, claim: "ChatSession 메모리 dict에 slots 추가 — 기존 세션 설계 일관, 재시작 소실 수용", evidence_refs: [E02], confidence: verified, load_bearing: true}
  - {id: P03-C2, phase: 3, kind: design, claim: "handle_message system 조립 지점에 채워진/미충족(우선순위순) 슬롯 섹션·턴 예산·개방형 첫 질문 주입 (CAP03/06/12)", evidence_refs: [E01], confidence: verified, load_bearing: true}
  - {id: P03-C3, phase: 3, kind: design, claim: "조건부 활성 when 배선 + 레드플래그 신호 감지 시 미충족 최상단 정렬·우선 질문 규칙 주입 (CAP02/05)", evidence_refs: [E11], confidence: doc, load_bearing: true}
  - {id: P03-C4, phase: 3, kind: design, claim: "fake 추출은 스키마 signals 키워드 결정론 매칭(다중 슬롯 동시), llm.py 무수정 + 접미사 방식으로 test_swap_e2e·test_chat 단언 보존 (CAP04/10/18, critic 실파일 대조 확인)", evidence_refs: [E04, E09], confidence: verified, load_bearing: true}
  - {id: P03-C5, phase: 3, kind: verification, claim: "tests/test_slot_flow.py [NEW]가 주입·opening_question 1턴 포함(CAP12)·조건부 활성·레드플래그 정렬·다중 추출·덮어쓰기 금지·스키마-less 미개입을 검증", evidence_refs: [], confidence: assumed, load_bearing: true}
  - {id: P03-C6, phase: 3, kind: risk, claim: "API 계약 {reply,turn,limit_reached}·storage 호출 형태 무변경 (CAP16/17)", evidence_refs: [E01, E05], confidence: verified, load_bearing: true}
  - {id: P04-C1, phase: 4, kind: design, claim: "실모드 단일 호출 통합(D02): system 추출 지시 + 응답 말미 fenced 슬롯 JSON 분리, 파싱 실패 턴 스킵·응답 원문 유지", evidence_refs: [E15, E04], confidence: doc, load_bearing: true}
  - {id: P04-C2, phase: 4, kind: design, claim: "LLM 출력 신뢰 경계 검증: 스키마 활성 슬롯 id 화이트리스트·값 str 강제·길이 상한 200자·기채움 덮어쓰기 금지 — 통과분만 병합", evidence_refs: [E05], confidence: doc, load_bearing: true}
  - {id: P04-C3, phase: 4, kind: verification, claim: "tests/test_slot_extract.py [NEW]가 파싱 실패 스킵·비정상 슬롯 폐기·제거본 저장을 검증", evidence_refs: [], confidence: assumed, load_bearing: true}
  - {id: P05-C1, phase: 5, kind: design, claim: "스키마 활성 시 요약은 LLM 무호출 결정론 JSON(미확인 포함, red_flags는 채워진 red_flag 슬롯 id 파생)을 text 문자열로 기존 intake_summary 경로에 저장 — 저장 스키마 무변경·신규 저장 표면 없음 (CAP07/08/17)", evidence_refs: [E01, E05], confidence: verified, load_bearing: true}
  - {id: P05-C2, phase: 5, kind: design, claim: "test_summary_failure는 레거시(LLM 요약) 경로 전제라 스키마-less 지식셋으로 이동해 계속 검증 — Phase 5 배치가 정확 (critic 확인)", evidence_refs: [E08], confidence: verified, load_bearing: true}
  - {id: P05-C3, phase: 5, kind: risk, claim: "위기 슬롯 민감정보의 구조화 JSON 평문 저장은 accepted risk — origin verbatim §2 사용자 지시·intake Risks 기표면화, 저장 표면 무확대", evidence_refs: [E05], confidence: verified, load_bearing: true}
  - {id: P06-C1, phase: 6, kind: e2e, claim: "tests/test_slot_e2e.py [NEW] 4종 — 위기=레드플래그 우선 질문 순서 단언, 혼합=2슬롯 동시 충족 단언 (CAP20~23 어드버서리얼 강제)", evidence_refs: [], confidence: assumed, load_bearing: true}
  - {id: P06-C2, phase: 6, kind: verification, claim: "knowledge-alt 스왑 회귀는 기존 test_swap_e2e + 신규 스텁 형식 단언 + 전체 pytest로 닫음 (CAP18/24)", evidence_refs: [E09], confidence: verified, load_bearing: true}
  - {id: P07-C1, phase: 7, kind: design, claim: "부모 checklist `## Cross-Phase 메모` 실재·supersede 0건 — Phase 10(D10) supersede 기록 append 후 grep 검증 유효 (CAP25)", evidence_refs: [E13], confidence: verified, load_bearing: true}
  - {id: P07-C2, phase: 7, kind: design, claim: "docs/demo-scenario.md + README 링크 — 시연 순서·재활 3-트랙 프리뷰·지식 교체 시연·민감정보 주의 포함 (CAP15/19, 사용자 위치 결정)", evidence_refs: [E13], confidence: doc, load_bearing: true}
```

## Critic Objections

2 라운드 진행. 1차(O1~O5)는 6-phase 초안 대상 — REV2에서 반영. 재실행(R-O1~R-O5)은 REV2 대상 — REV3에서 반영. 전 항목 해소 완료.

```yaml
objections:
  - {id: O1, claim_id: P02-C2, lens: architecture, severity: warn, confidence: 8, basis: verified, objection: "비밀보장 원칙·예외가 면담 순서 목록 1번 항목 내부에만 존재 — 목록 제거 시 소실 위험, 보존 단언 0건", proposed_action: revise, resolution: "REV2/REV3: 별도 섹션 승격 + GM20 강화 grep 게이트"}
  - {id: O2, claim_id: P03-C5(초안), lens: security, severity: warn, confidence: 7, basis: failure_path_missing, objection: "실모드 슬롯 JSON에 id 화이트리스트·str 강제·길이 상한 부재 — 비정상 출력 증폭 경로 미게이트", proposed_action: revise, resolution: "REV2: Phase 4 신뢰 경계 검증 설계 + FP19/GM21"}
  - {id: O3, claim_id: P03-C5(초안), lens: architecture, severity: warn, confidence: 6, basis: phase_unit_too_large, objection: "구 Phase 3가 fake 루프·실모드 추출 invariant 2개를 한 phase에 담음", proposed_action: split_phase, resolution: "REV2: Phase 3/4 분할 — 7 phases"}
  - {id: O4, claim_id: P04-C1(초안), lens: security, severity: info, confidence: 6, basis: risk_acceptance, objection: "위기 슬롯 민감정보 구조화 JSON 평문 저장 — accepted risk 명기 필요", proposed_action: accept_risk, resolution: "REV2: FP20/GM22 accepted_risk + P05-C3"}
  - {id: O5, claim_id: P02-C2, lens: architecture, severity: info, confidence: 5, basis: heuristic, objection: "Phase 2~3 사이 중간 상태 창(페르소나 순서 제거·엔진 미배선)", proposed_action: accept_risk, resolution: "직렬 실행 전제 수용 기록"}
  - {id: R-O1, claim_id: P05-C1, lens: architecture, severity: warn, confidence: 8, basis: verified, objection: "분할 부작용 — Phase 5 depends:[3]이 Phase 4와 동일 scope인데 병렬 신호", proposed_action: revise, resolution: "REV3: Phase 5 depends:[4]"}
  - {id: R-O2, claim_id: P02-C2, lens: security, severity: warn, confidence: 8, basis: verified, objection: "GM20 grep이 변경 전 파일도 통과 — 승격·예외 열거 소실 미탐지", proposed_action: revise, resolution: "REV3: '^## 비밀보장' 헤딩 + '예외' 이중 grep으로 강화 (변경 전 실패)"}
  - {id: R-O3, claim_id: P04-C2, lens: testing, severity: warn, confidence: 7, basis: coverage_gap, objection: "기채움 슬롯 덮어쓰기 금지 불변식이 무게이트 — 트랙 뒤집힘 실패 경로", proposed_action: revise, resolution: "REV3: FP21/GM23 + Phase 3 체크리스트 6 + GM21 문구 확장"}
  - {id: R-O4, claim_id: P04-C1, lens: architecture, severity: info, confidence: 7, basis: risk_acceptance, objection: "Phase 3~4 사이 실모드 중간 상태 창(주입은 모드 공통·실모드 추출 미배선)", proposed_action: accept_risk, resolution: "직렬 실행·fake 데모 전제 수용 기록"}
  - {id: R-O5, claim_id: P05-C1, lens: backend, severity: info, confidence: 6, basis: heuristic, objection: "요약 red_flags 필드의 감지 이력 상태 소재 미선언", proposed_action: revise, resolution: "REV3: 채워진 red_flag 슬롯 id 파생으로 명시 — 별도 상태 없음"}
supplements:
  - {claim_id: P03-C4, lens: testing, note: "접미사 방식 보존을 실파일 대조로 확인 — test_swap_e2e.py:40-46 4개 단언 전부 문서 제목 부분문자열 검사, test_chat.py:27,33 동일. '[fake]' 문자열 단언 다른 테스트 없음(grep 확인)."}
  - {claim_id: P05-C2, lens: testing, note: "E08 실증 — flaky_ask는 system == chat._SUMMARY_INSTRUCTION일 때만 raise. 요약 경로는 Phase 5에서만 바뀌므로 Phase 3·4 커밋 시점에는 기존 스위트가 깨지지 않음 — 배치 정확."}
  - {claim_id: P06-C1, lens: architecture, note: "재번호 게이트 매핑 전수 대조 — GM1=p1, GM2/3/13/14/23=p3, GM15/16/17/20=p2, GM11/21=p4, GM8/9/10=p5, GM4/5/7/19=p6, GM12/18=p7, GM6=기존 파일, GM22=accepted_risk. dangling 없음."}
  - {claim_id: P04-C1, lens: backend, note: "chat.py:72-82 실측 — llm.ask 반환 직후 storage.append_turn(assistant)·history append 순서라 extract_real 삽입이 기존 흐름과 충돌 없음."}
  - {claim_id: P02-C1, lens: backend, note: "opening_question 원문이 접수-면접-질문지-구성.md:16에, 위기 조건부 슬롯 근거가 위기-상황-스크리닝.md 확인 항목 1·2에 원문 실재."}
  - {claim_id: P05-C3, lens: security, note: "intake.md:44-46 Risks에 위기 트랙 슬롯 구조화 저장 위험 원문 실재 — GM22 accepted_by 근거 성립."}
```

## Judge

1차: verdict `revise` (risk medium, issues 4) — O1/O2/O3 반영 지시. 최종(REV3 대상): 아래.

```yaml
judge:
  verdict: pass
  risk: low
  issues: 0
  top_issue: "none"
  required_action: "phase-init may create planning files from REV3 as-is (7 phase specs, GM22 accepted risk 명기 유지)"
  appeal_allowed: false
  claim_rulings_summary: "22개 클레임 전부 upheld — R-O1(depends 수정)·R-O2(grep 강화)·R-O3(FP21/GM23)·R-O4(수용 기록)·R-O5(파생 명시) 해소 확인"
```

## Triage

```yaml
triage:
  action: pass
  appeal_claims: []
  reasons: ["no blocking review condition"]
  deterministic_basis: ["default pass"]
  history:
    - round: 1
      action: revise
      note: "judge.verdict == revise — REV2/REV3 반영 후 재실행"
    - round: 2
      action: pass
```

## Appeal

미사용 — 두 라운드 모두 triage가 appeal을 반환하지 않음 (1차 revise → 2차 pass).

## Final Purpose Re-check

```yaml
final_purpose_recheck:
  status: pass
  rationale: "7-phase 분할·의존 재배선(5←4)·비밀보장 grep 게이트·신뢰 경계(FP19/GM21)·덮어쓰기 금지(FP21/GM23)·accepted risk(GM22)·red_flags 파생 명시는 전부 추가·강화이고, origin 6개 goal과 25 CAP(어드버서리얼 9종 포함)이 여전히 전수 폐쇄되며 새 scope 축소·과대 주장 없음."
  compared_to: revised_plan_ir
```

## Final Disposition

pass — 7-phase 직렬 계획 렌더 승인. Sub-agent 리뷰 체인(purpose ×2 → critic ×2 → judge ×2 → triage ×2 → final re-check) 전부 통과, fallback 미사용. E2E 카탈로그는 사용자 결정으로 생략(e2e_refs 빈 값, pytest e2e로 대체). 실행 중 준수 사항: GM22 accepted risk 유지, 직렬 실행(중간 상태 창 2곳은 fake 데모 전제 수용).
