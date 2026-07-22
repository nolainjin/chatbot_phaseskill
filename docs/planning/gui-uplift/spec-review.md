---
task: gui-uplift
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

# GUI 업리프트 — 참조 이미지 수준 재스타일 — Spec Review

## Active Lenses

architecture, testing, frontend, backend, security

## Evidence Ledger

```yaml
evidence_ledger:
  evidence_commit: "b90f71f0f111c325a5f3dfae34350251480aea8e"
```

- E01 Read static/index.html:1-50 — 현행 구조: 헤더(h1+subtitle+turn-counter), progress bar, .notice(22행 "이 대화 내용은 서버에 저장됩니다."), messages ul(하드코딩 인사 li), status, chat-form(input+전송 버튼), intake-panel aside(42행, hidden 기본).
- E02 Read static/app.js:1-162 — IIFE, SESSION_KEY "lmwiki_session_id", addMessage(26), showTyping(40), renderIntake(82: intake 없으면 패널 숨김 유지), sendMessage(107: POST /api/chat {session_id,message}), fake 접미사 strip 정규식(136), limit_reached 시 입력 비활성(140-144).
- E03 Read static/style.css:1-399 — CSS 변수 테마(라이트/다크 @media), 말풍선 비대칭 라운딩 부분 존재(.message-user 147, .message-assistant 155), slot-* 패널 스타일(245-343), 미디어쿼리 860px(345)/520px.
- E04 Read app/chat.py:107-125,207-213 — _intake_state: filled[]={id,label,value}, unfilled[]={id,label,red_flag}. schema is not None일 때만 result["intake"] additive — 기존 {reply,turn,limit_reached} 계약 무변경.
- E05 Read app/main.py:1-46 — 라우트는 POST /api/chat(19) 뿐. static 마운트 html=True(46)는 파일 하단 — 그 위에 선언한 GET 라우트가 우선. 로드 시점 스키마 유무 프로브 없음.
- E06 Read knowledge/_intake_schema.md:30-88 — 슬롯: track(p0, values 위기/관계/정서), chief_complaint(p1, **signals 없음**), coping(p2), support(p3), expectation(p4), symptom_context/relationship_target/relationship_duration/crisis_attempt_history(p5, when 조건부), crisis_plan_means(p6, red_flag). 정서 신호어에 '불안','우울','잠'(43행), 관계 신호어에 '대인'(42행).
- E07 Bash ls knowledge-alt/ — _intake_schema.md·_persona.md 없음(커피 문서 6종) → intake.load_schema None 폴백 → 응답에 intake 키 부재.
- E08 Read docs/design/gui-reference.png — 딥틸 헤더 바, 3단 스테퍼(도움 필요 영역·상황 파악·상담 준비), 보호 카드(쉐브론 접기), 원형 봇 아바타, 비대칭 말풍선, 타임스탬프(오전 10:30), 칩 4종(불안·우울·수면·관계) 2×2, 둥근 입력창+원형 전송, 하단 자물쇠 문구.
- E09 Bash tooling_readiness — sem=ready, engramx=missing(Read/Grep 폴백), ts_morph=missing(비차단), graph=missing, large_files=0.
- E10 Bash ls tests/ + Read tests/test_ui_serving.py — pytest 12파일, TestClient 기반 static 서빙 테스트 선례. 실행은 .venv/bin/python -m pytest (사용자 지시 — 시스템 pytest는 의존성 없어 수집 에러).
- E11 Read app/intake.py — load_schema(191, None 폴백), Schema(47)/Slot(27, red_flag 32), unfilled_by_priority(55), extract_fake(83: **signals 없는 슬롯은 건너뜀** — chief_complaint는 fake에서 절대 안 채워짐).
- E12 Bash git ls-files '*CONTEXT.md' — 0건 → phase_context baseline missing.
- E13 User decision (AskUserQuestion 2026-07-12) — 스키마 프로브 방식으로 GET /api/config 추가 승인. playwright 방법(chromium-1228 캐시 + 스크래치패드 npm i)은 직전 세션 검증 — 사용자 제공 사실.
- E14 Grep docs/planning/*/phase-*.md — 선례: docs/e2e 카탈로그 없이 e2e_refs/e2e_triggers 빈 배열 유지 (intake-slot-engine).

## Memory Evidence

MemoryPacket 미사용 — 이번 계획은 현재 사용자 요청 원문 + 현재 리포 Read/Grep/Bash 증거 + 참조 이미지만으로 닫힌다. 과거 메모리 클레임을 확정 사실로 렌더한 항목 없음.

## Purpose Review

1차 리뷰(수정 전 초안): verdict `pass`. 이후 critic 라운드 반영으로 SC2 재서술·FP10/GM11/GM12 추가 — final re-check로 재확인(하단 Final Purpose Re-check).

```yaml
purpose_review:
  intended_outcomes:
    - "딥틸 테마 비주얼 8종(헤더 바·봇 아바타·비대칭 말풍선·타임스탬프·개인정보 접기 카드·둥근 입력창+원형 전송·하단 자물쇠 문구·테마)이 라이트/다크·데스크톱/모바일에서 렌더 (Phase 2, GM3/GM4/GM9 + Phase 5 스크린샷)"
    - "intake unfilled 집합에서 결정적으로 파생되는 3단계 스테퍼 — 라이브(fake) ①→② 전환 + 순수 함수 3상태 합성 단언(③ 포함, GM10)"
    - "첫 턴 칩 4종(불안·우울·수면·관계)이 신호어 포함 문장을 대신 전송해 fake 추출기가 track을 채움 (Phase 4 + GM2 extract_fake 단언)"
    - "불변 제약 유지 — POST /api/chat 계약은 기존 pytest 회귀로 보존, 엔진 수정은 승인된 GET /api/config 뿐, knowledge-alt에서 패널·스테퍼·칩 미노출을 intakeSchemaActive 게이트로 차단하고 GM1(test)+GM8(playwright)로 이중 확인, _persona.md는 scope 외 불가침"
    - ".venv pytest 전체 통과 + 데스크톱/모바일·knowledge/knowledge-alt playwright 스크린샷 산출·사용자 전달로 참조 이미지 육안 대조 (Phase 5)"
  goal_alignment:
    verdict: pass
    rationale: "원 요청의 3개 범위층과 4개 불변 제약, 검증 지시가 모두 phase 체크리스트·검증·게이트로 닫히며 스왑 회귀는 test+browser로 이중 커버된다."
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

해당 없음 — 이 task는 blueprint 핸드오프가 아니라 사용자 free-text 과업 기술로 생성됨. `source_blueprint` 블록 생략.

## Decision Surface

intake 파이프라인 미경유(free-text 직행) — registry/intake 결정 표면 없음. 계획 중 확정된 사용자 결정 1건은 user_choices에 task-local로 기록.

```yaml
decision_surface:
  status: not_applicable
  source_mode: none
  source_artifact: ""
  source_command: ""
  freshness: not_applicable
  no_memory_promotion: true
  accepted_defaults: []
  user_choices:
    - decision_key: "schema_probe_method"
      answer: "GET /api/config 추가 — {\"intake_schema\": bool} 읽기 전용 엔드포인트, /api/chat 계약 무변경. 대안(낙관적 노출 후 숨김/URL 파라미터)은 스왑 회귀 위반·시연 불편으로 기각"
      source: "사용자 답변 2026-07-12 (phase-init Step 4 AskUserQuestion)"
  deferrals: []
  unresolved_load_bearing_offers: []
  stale_or_missing_rubric_candidates: []
  provenance:
    decisions_file: ""
    matched_rubric_ids: []
    suppressed_reasons: []
  finalization_audit: false
```

## Goal Decomposition

```yaml
goal_items:
  - id: G1
    source: "범위 1: 비주얼 전면 — 참조 이미지 수준 재스타일"
    decomposed_to: [SC1]
  - id: G2
    source: "범위 2: 3단계 스테퍼 — intake 필드 파생"
    decomposed_to: [SC2]
  - id: G3
    source: "범위 3: 퀵리플라이 칩 — 문장 대신 전송(엔진 무수정 절충안)"
    decomposed_to: [SC3]
  - id: G4
    source: "불변 제약 4종(API 계약·스왑 회귀·엔진 최소 수정·페르소나 불가침)"
    decomposed_to: [SC4]
  - id: G5
    source: "검증 환경 지시(.venv pytest + playwright 스크린샷 + rate limit 회피)"
    decomposed_to: [SC5]
scope_deferrals: []
```

## Success Criteria Coverage

```yaml
success_criteria:
  - id: SC1
    criterion: "참조 이미지의 비주얼 8종이 데스크톱/모바일에서 렌더"
    covered_by: [GM3, GM4, GM5, GM9]
  - id: SC2
    criterion: "스테퍼 3단계 파생 — 라이브 fake ①→② 전환 + 파생 함수 3상태 합성 단언(③ 포함; fake는 signals 없는 chief_complaint를 못 채워 라이브 ③은 실모드 전용)"
    covered_by: [GM5, GM10]
  - id: SC3
    criterion: "칩 4종 첫 턴 노출·문장 대신 전송·track 채움"
    covered_by: [GM2, GM7]
  - id: SC4
    criterion: "불변 제약 유지 — /api/chat 계약 무변경·knowledge-alt 미노출·엔진 수정은 승인된 프로브뿐·페르소나 불가침"
    covered_by: [GM1, GM8, GM11, GM12]
  - id: SC5
    criterion: ".venv pytest 전체 통과 + playwright 스크린샷 산출·전달"
    covered_by: [GM5, GM6]
```

## Failure Path Seeds

```yaml
failure_paths:
  - id: FP1
    scenario: "스키마 프로브 부재/오동작 → knowledge-alt 첫 화면에 칩·스테퍼 노출"
    impact: "스왑 회귀 — 지식 교체형 제품 전제 붕괴"
    mapped_gates: [GM1, GM8]
  - id: FP2
    scenario: "칩 문장이 스키마 신호어와 매칭 실패 → track 미채움, 스테퍼 ① 고착"
    impact: "시연 첫 동작 실패"
    mapped_gates: [GM2]
  - id: FP3
    scenario: "CSS 전면 개편이 슬롯 패널·타이핑 인디케이터 등 기존 요소 스타일 파괴"
    impact: "직전 커밋(b90f71f) 기능 시각 회귀"
    mapped_gates: [GM3]
  - id: FP4
    scenario: "개인정보 고지 문구('서버에 저장됩니다') 카드 승격 중 유실"
    impact: "저장 사실 고지 후퇴(신뢰·윤리)"
    mapped_gates: [GM4]
  - id: FP5
    scenario: "addMessage DOM 변경이 타임스탬프·fake 접미사 strip 정규식·스크롤과 충돌해 메시지 렌더 깨짐"
    impact: "대화 표시 자체 실패"
    mapped_gates: [GM5]
  - id: FP6
    scenario: "브라우저 검증 중 신규 세션 남발 → rate limit(IP당 5세션/시간, 디스크 영속) 429로 검증 불능"
    impact: "Phase 5 검증 차단"
    mapped_gates: [GM6]
  - id: FP7
    scenario: "limit_reached/오류 상태에서 칩 잔존·활성 → 한도 초과 후 전송 시도"
    impact: "오류 UX·상태 불일치"
    mapped_gates: [GM7]
  - id: FP8
    scenario: "다크모드 딥틸 변수 미정의 → 다크에서 대비 실패·구 팔레트 잔존"
    impact: "다크 사용자 시각 품질 회귀"
    mapped_gates: [GM9]
  - id: FP9
    scenario: "스테퍼 파생 규칙 오류(조건부 슬롯 활성 시 ③ 조기 진입 등)"
    impact: "진행 상태 오표시"
    mapped_gates: [GM10]
  - id: FP10
    scenario: "스키마 있는 지식셋에서 GET /api/config fetch 실패 → 칩·스테퍼 조용히 미노출 또는 undefined config 접근 예외"
    impact: "시연 기능 무증상 소실 또는 JS 예외"
    mapped_gates: [GM11, GM12]
```

## Failure Path Gate Mapping

```yaml
gate_mappings:
  - id: GM1
    failure_path: FP1
    target_type: test
    target:
      file: tests/test_config.py
      status: planned
      phase: 1
      checklist_text: "tests/test_config.py 신규 — knowledge에서 intake_schema true, knowledge-alt에서 false 단언"
    rationale: "프로브 양경로를 TestClient로 상시 회귀 검증"
  - id: GM2
    failure_path: FP2
    target_type: verification
    target:
      phase: 4
      command: "intake.extract_fake(s, schema, {})"
    rationale: "칩 문장-신호어 표류를 결정적 검증으로 차단"
  - id: GM3
    failure_path: FP3
    target_type: phase_checklist
    target:
      phase: 2
      checklist_text: "타이핑 인디케이터·진행 바·슬롯 패널·상태/에러·disabled 스타일이 개편 후에도 보존된다"
    rationale: "전면 개편의 기존 요소 회귀를 체크리스트로 고정"
  - id: GM4
    failure_path: FP4
    target_type: verification
    target:
      phase: 2
      command: 'grep -q "서버에 저장됩니다" static/index.html'
    rationale: "고지 문구 유실을 기계 단언으로 차단"
  - id: GM5
    failure_path: FP5
    target_type: verification
    target:
      phase: 5
      command: "node gui-smoke.mjs"
    rationale: "브라우저 전용 증상은 실브라우저 스모크로만 닫힌다"
  - id: GM6
    failure_path: FP6
    target_type: phase_checklist
    target:
      phase: 5
      checklist_text: "sessionStorage lmwiki_session_id를 고정값으로 주입해 전 시나리오에서 재사용한다(rate limit 회피)"
    rationale: "검증 환경 제약을 절차 항목으로 강제"
  - id: GM7
    failure_path: FP7
    target_type: phase_checklist
    target:
      phase: 4
      checklist_text: "첫 전송(칩/타이핑 불문) 후 칩 행이 제거되고 limit·오류 상태에서 칩이 노출되지 않는다"
    rationale: "칩 수명주기를 상태 전이와 함께 고정"
  - id: GM8
    failure_path: FP1
    target_type: verification
    target:
      phase: 5
      command: "#stepper/#chips/#intake-panel visible=false 단언 실패 시 exit 1"
    rationale: "스왑 회귀를 실브라우저에서 이중 확인"
  - id: GM9
    failure_path: FP8
    target_type: phase_checklist
    target:
      phase: 2
      checklist_text: "다크모드 @media 블록에 딥틸 팔레트 변수를 정의하고 구 팔레트 값이 남지 않는다"
    rationale: "다크 변수 누락을 체크리스트로 고정"
  - id: GM10
    failure_path: FP9
    target_type: verification
    target:
      phase: 5
      command: "window.lmwikiDeriveStep"
    rationale: "fake 라이브 한계(③ 도달 불가)를 순수 함수 합성 단언으로 대체해 3상태 전부 결정적으로 검증"
  - id: GM11
    failure_path: FP10
    target_type: phase_checklist
    target:
      phase: 3
      checklist_text: "intakeSchemaActive 기본 false — config fetch 실패/비정상 응답 시 스테퍼 미노출 유지(fail-closed)하고 console.warn을 남기며 채팅 동작은 무영향이다"
    rationale: "무증상 기능 소실을 명세된 폴백 + 체크리스트로 고정 (스테퍼 소관 — Phase 3)"
  - id: GM12
    failure_path: FP10
    target_type: phase_checklist
    target:
      phase: 4
      checklist_text: "config fetch 실패 시 칩도 미노출 유지(fail-closed)되고 undefined config 접근 예외가 발생하지 않는다 — intakeSchemaActive 공유 플래그 게이트"
    rationale: "칩 소관 실패 경로를 소유 phase(Phase 4) 체크리스트로 분리 고정"
```

## Translation Baseline

not_required — 기존 프로토콜 텍스트의 언어 규칙 재작성·번역이 계획에 없다 (GUI 텍스트 추가·승격은 번역이 아님).

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
  - {id: P01-C1, phase: 1, kind: scope, claim: "Phase 1 scope는 app/main.py + 신규 tests/test_config.py로 충분 — 라우트 추가 지점(static 마운트 위)과 TestClient 테스트 선례 실재", evidence_refs: [E05, E10], confidence: verified, load_bearing: true}
  - {id: P01-C2, phase: 1, kind: design, claim: "GET /api/config는 intake.load_schema(knowledge_dir) is not None을 bool로 반환하면 스키마 유무를 정확히 반영 — load_schema는 부재/오류 시 None 폴백 계약(app/intake.py:191)", evidence_refs: [E11, E06, E07], confidence: verified, load_bearing: true}
  - {id: P01-C3, phase: 1, kind: verification, claim: "KNOWLEDGE_DIR 전환(knowledge/knowledge-alt)으로 true/false 양경로를 TestClient 테스트로 판정", evidence_refs: [E07, E10], confidence: verified, load_bearing: false}
  - {id: P02-C1, phase: 2, kind: scope, claim: "비주얼 8종은 static 3파일 수정만으로 구현 가능 — 마크업·스타일·타임스탬프 렌더 지점이 모두 3파일 안", evidence_refs: [E01, E02, E03, E08], confidence: verified, load_bearing: true}
  - {id: P02-C2, phase: 2, kind: design, claim: "개인정보 카드는 native <details>로 승격, 기존 고지 문구 원문을 본문에 보존", evidence_refs: [E01], confidence: verified, load_bearing: false}
  - {id: P02-C3, phase: 2, kind: risk, claim: "addMessage DOM 구조 변경(타임스탬프 래퍼)은 .message 클래스·본문 textContent 규약을 유지하면 기존 동작(스크롤·strip 정규식)과 충돌하지 않는다", evidence_refs: [E02], confidence: verified, load_bearing: true}
  - {id: P03-C1, phase: 3, kind: design, claim: "스테퍼 3단계는 intake.unfilled id 집합에서 순수 함수(window.lmwikiDeriveStep)로 결정적 파생 — track∈U→①, U−{expectation}≠∅→②, 그 외→③. fake 추출기는 signals 없는 chief_complaint를 안 채워 fake 라이브 ③ 도달 불가 — 라이브 검증은 ①→②까지, 3상태 전체는 합성 단언(GM10), 실모드는 스키마 계약상 ③ 도달 가능", evidence_refs: [E04, E06, E11], confidence: verified, load_bearing: true}
  - {id: P03-C2, phase: 3, kind: dependency, claim: "Phase 3은 Phase 1(config 프로브)과 Phase 2(헤더·레이아웃 마크업 기반)에 의존", evidence_refs: [E05, E01], confidence: verified, load_bearing: false}
  - {id: P03-C3, phase: 3, kind: design, claim: "공유 플래그 intakeSchemaActive 기본 false — config fetch 성공 시에만 true. fetch 실패는 본질적으로 fail-closed(스테퍼·칩 미노출, undefined 접근 없음), console.warn 기록, 채팅 무영향", evidence_refs: [E02], confidence: assumed, load_bearing: false}
  - {id: P04-C1, phase: 4, kind: design, claim: "칩 4종의 data-send 문장은 각각 스키마 신호어('불안','우울','잠','대인')를 포함해 fake 추출기가 track을 채운다", evidence_refs: [E06, E11], confidence: verified, load_bearing: true}
  - {id: P04-C2, phase: 4, kind: verification, claim: "index.html의 data-send 문장을 추출해 intake.extract_fake로 track 채움을 기계 단언하면 칩 문장-신호어 표류를 차단", evidence_refs: [E06, E11], confidence: verified, load_bearing: false}
  - {id: P04-C3, phase: 4, kind: design, claim: "칩은 intakeSchemaActive && 사용자 발화 0회에만 노출하고 첫 전송 후 제거하면 limit/오류 상태와 충돌하지 않는다", evidence_refs: [E02], confidence: assumed, load_bearing: false}
  - {id: P05-C1, phase: 5, kind: verification, claim: "playwright는 ~/.claude 캐시 chromium-1228 + 스크래치패드 npm i playwright로 구동 가능 — 직전 세션 검증된 방법(사용자 제공 사실)", evidence_refs: [E13], confidence: doc, load_bearing: true}
  - {id: P05-C2, phase: 5, kind: risk, claim: "rate limit(IP당 신규 세션 5/시간, 디스크 영속)은 sessionStorage lmwiki_session_id 고정값 재사용으로 회피(사용자 지시)", evidence_refs: [E02], confidence: doc, load_bearing: true}
  - {id: P05-C3, phase: 5, kind: e2e, claim: "docs/e2e 카탈로그 부재 — e2e_refs 빈 배열 유지가 저장소 선례와 일치, Phase 5 로컬 스모크 + GM1 테스트가 스왑 회귀를 닫는다", evidence_refs: [E14, E07], confidence: verified, load_bearing: false}
```

## Critic Objections

2 라운드 진행. 1차(O1~O3)는 초안 대상 — 수정 반영. 2차(R2-O1)는 수정본 대상 — 재수정 반영. 전 항목 해소 완료.

```yaml
objections:
  - {id: O1, claim_id: P03-C1, lens: testing, severity: block, confidence: 9, basis: verified, objection: "MODEL=fake에서 스테퍼 ③ 도달 불가 — extract_fake는 signals 없는 슬롯을 건너뛰고 chief_complaint(p1, required, signals 없음)가 영구 미충족이라 U−{expectation}가 절대 공집합이 안 됨. GM10의 ③ 라이브 단언은 통과 불가, SC2가 검증 환경에서 전달 불능", proposed_action: revise, resolution: "파생 규칙 유지(실모드 정합) + 검증 재편 — 순수 함수 window.lmwikiDeriveStep 노출, 라이브는 ①→②만 단언, 3상태 전체는 page.evaluate 합성 입력 4종으로 결정적 단언(GM10 개정). SC2·P03-C1 재서술, fake 한계 명문화"}
  - {id: O2, claim_id: P03-C1, lens: testing, severity: warn, confidence: 6, basis: coverage_gap, objection: "load-bearing 파생 규칙에 결정적 게이트 부재 — Phase 3 검증이 pytest+정적 grep뿐, 3상태 로직은 GM10(브라우저, intervention phase)에만 의존", proposed_action: revise, resolution: "GM10 합성 단언이 결정적 게이트(리포에 JS 테스트 러너 부재 — page.evaluate가 유일한 JS 실행 경로, critic 재검토 확인) + Phase 3 edge에 훅 존재 grep 추가"}
  - {id: O3, claim_id: P04-C3, lens: frontend, severity: info, confidence: 5, basis: failure_path_missing, objection: "GET /api/config fetch 실패 폴백 미명세 — 스키마 있는 셋에서 실패 시 칩·스테퍼 무증상 미노출, 커버하는 failure_path 없음", proposed_action: revise, resolution: "FP10 신설 + Phase 3 설계에 fail-closed 명세(intakeSchemaActive 기본 false·console.warn·채팅 무영향) + GM11 체크리스트 게이트 + 신규 클레임 P03-C3"}
  - {id: R2-O1, claim_id: P03-C3, lens: frontend, severity: warn, confidence: 6, basis: coverage_gap, objection: "칩 fail-closed가 GM11(Phase 3 체크리스트)에 얹혀 있으나 칩은 Phase 4 산출물 — 칩 게이트가 undefined config 접근으로 예외 가능, 소유 phase에서 미검증", proposed_action: revise, resolution: "공유 플래그 intakeSchemaActive(기본 false — undefined 접근 원천 제거)로 설계 명세 + GM12(Phase 4 체크리스트) 신설, FP10 mapped_gates [GM11, GM12]"}
supplements:
  - {claim_id: P01-C2, lens: backend, note: "라우트 우선순위 실측 — app/main.py:45-46 StaticFiles 마운트가 파일 하단 조건부라 그 위에 선언한 @app.get('/api/config')가 우선 등록. load_schema는 부재/파싱 실패 시 None 수렴 확인"}
  - {claim_id: P04-C1, lens: frontend, note: "신호어 실측 — _intake_schema.md:40-43에서 불안/우울/잠→정서, 대인→관계가 모두 p0 track 슬롯에 매핑. 칩 문장 4개 각각 정확히 1개 신호어 포함 → extract_fake(문장, schema, {})가 {'track': ...} 산출"}
  - {claim_id: P05-C1, lens: testing, note: ".venv pytest 9.1.1 구동 확인. knowledge-alt는 커피 문서 6종에 _intake_schema.md 없음 → intake 키 부재 — 스왑 회귀 전제 성립"}
  - {claim_id: P03-C1, lens: architecture, note: "2차 재검토 — GM10 합성 입력 4종이 파생 규칙 3분기 전부와 정합(['track',..]→1, ['chief_complaint','expectation']→2, ['expectation']→3, []→3). 라이브 ①→②는 실도달(칩 클릭 → track=정서 채움 → U={chief_complaint,...}→②)"}
```

## Judge

1차: verdict `revise` (risk high, issues 3) — O1/O2/O3 반영 지시. 최종(수정본 대상): 아래.

```yaml
judge:
  verdict: pass
  risk: low
  issues: 0
  top_issue: "none"
  required_action: "Render phase files — round-2 O1 resolved by shared intakeSchemaActive flag (Phase 3) + GM12 chip fail-closed gate (Phase 4)"
  appeal_allowed: false
  claim_rulings_summary: "15개 클레임 전부 upheld — O1(합성 단언 재편)·O2(결정적 게이트)·O3(fail-closed 명세)·R2-O1(공유 플래그+GM12) 해소 확인. fake ③ 도달 불가는 코드로 확증되어 문서화됨"
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
      note: "judge.verdict == revise (O1 block) — GM10 재편·FP10/GM11 신설 후 재실행"
    - round: 2
      action: pass
```

## Appeal

미사용 — 두 라운드 모두 triage가 appeal을 반환하지 않음 (1차 revise → 2차 pass).

## Final Purpose Re-check

```yaml
final_purpose_recheck:
  status: pass
  rationale: "SC2 재서술은 scope 축소가 아닌 검증 재편 — 파생 규칙과 3상태 전부 구현되고 ③은 순수 함수 합성 단언(GM10)으로 결정적 커버·실모드 도달 가능하며, fake 추출기의 ③ 도달 불가는 코드로 확증·문서화됐고 FP10/GM11/GM12는 fail-closed 견고성 추가일 뿐이다."
  compared_to: revised_plan_ir
```

## Final Disposition

pass — 5-phase 계획 렌더 승인. Sub-agent 리뷰 체인(purpose → critic ×2 → judge ×2 → triage ×2 → final re-check) 전부 통과, fallback 미사용, appeal 미사용. E2E 카탈로그는 리포에 없고 선례대로 e2e_refs 빈 값 유지 — Phase 5 playwright 스모크 + GM1 테스트가 대체. 실행 중 준수 사항: 엔진 수정은 GET /api/config(사용자 승인)로 한정, _persona.md·봇 말투 불가침, GM 체크리스트 문구는 phase 파일과 정확 일치 유지.
