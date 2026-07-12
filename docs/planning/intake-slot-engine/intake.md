---
task: intake-slot-engine
created: 2026-07-11
source: rough_request
research_required: false
---

# 슬롯 스키마 문진 엔진 + 상담 접수면담 데모 — Intake

## Goal

knowledge 디렉토리의 언더스코어 예약 파일(_intake_schema.md)로 수집 슬롯을 선언하는 도메인 무관 문진 엔진을 추가하고, 기존 상담 지식셋에 3-트랙(정서/관계/위기) 접수면담 스키마를 얹어 fake 모드 의사 시연 데모까지 완성한다.
성공 기준: fake 모드 e2e 시나리오 4종(정서/관계/위기 레드플래그 우선/혼합 발화 다중 슬롯) 통과 + knowledge-alt 스왑 Q&A 폴백 회귀 없음 + 전체 pytest 통과.

## Facts

- 부모 task lmwiki-chatbot-proto checklist: Phase 1~7·9 completed, Phase 8 needs_user(4/5, 실배포 검증 잔여), Phase 10 pending(0/5) — Phase 10(D10 선형 단계 스크립트)이 이번 요청의 supersede 대상 (`docs/planning/lmwiki-chatbot-proto/checklist.md`).
- `app/chat.py`: handle_message가 persona + `[진행: n/10턴]` + 검색 문서로 system 프롬프트를 조립. MAX_TURNS=10, 반환 계약 {reply, turn, limit_reached}. 10턴 도달 시 _SUMMARY_INSTRUCTION으로 요약을 생성해 role="intake_summary"로 저장(현재는 산문 텍스트), 요약 실패는 try/except로 격리.
- `app/knowledge.py`: "_"로 시작하는 파일은 검색 대상에서 제외(예약 규칙) — _intake_schema.md는 규칙만 지키면 검색에 자연히 안 섞임. YAML frontmatter 파서(yaml.safe_load) 이미 존재.
- `app/llm.py`: MODEL=fake면 Anthropic 미호출, "[fake] 참고 문서: <제목들>" 스텁만 반환 — 현재 fake 경로는 슬롯 추출·문진 진행을 전혀 흉내내지 못함. 문진 흐름 전체 시연에는 fake 경로 확장이 필수.
- `app/storage.py`: 턴 저장 스키마 {seq, role, text} — text가 문자열이므로 구조화 JSON 요약은 text 필드에 JSON 문자열로 직렬화해 넣으면 "저장 스키마 무변경" 제약과 정합.
- `knowledge/_persona.md`: 현재 "면담 순서" 1~5단계(비밀보장 안내→방문 이유→필요 질문→위기 스크리닝→10턴 내 요약)를 소유 — origin이 지적한 소유권 충돌(순서·항목은 스키마 소유로 이관) 실재.
- `knowledge/` 상담 지식 6종 존재: 라포-형성-기법, 비밀보장-원칙과-예외, 상담-목표-설정, 위기-상황-스크리닝, 접수-면접-질문지-구성, 초기-면담-목적과-구조. `knowledge-alt/` 커피 6종(스키마·_persona.md 없음) — 폴백 시연용 전제 성립.
- 세션 상태는 메모리 dict(`app/chat.py` ChatSession: session_id/turns/history) — 재시작 소실은 프로토타입 수용 범위로 이미 문서화됨. 슬롯 채움 상태도 같은 세션 객체에 두면 기존 설계와 일관.
- `tests/`: test_intake.py(Phase 9 산출), test_swap_e2e.py 등 8개 테스트 파일 존재.

## Assumptions

- 슬롯 추출은 LLM 출력(실모드) 또는 결정론 규칙(fake 모드)에서 파싱한다 — 구체 방식은 D02(추출 전략) 답변 + phase-init 스펙에서 확정.
- knowledge-alt/에는 _intake_schema.md를 추가하지 않는다 — "스키마 없는 지식셋 = 기존 Q&A 폴백" 시연이 목적이므로.
- 의사 시연용 데모 시나리오(시연 순서, 재활 3-트랙 프리뷰 포인트, 지식 교체 시연 순서)는 리포 내 문서 산출물로 만든다. 재활 트랙 초안 스키마 종이 1장은 scope 외(사용자와 별도 작업).

## Constraints

- 언더스코어 예약 파일 규칙 준수 (신규 _intake_schema.md도 이 규칙 안에서).
- API 계약 {reply, turn, limit_reached} 무변경.
- rate limit·저장 스키마·SQLite 배치 무변경.
- 스키마 부재·형식 오류 시 기존 페르소나/Q&A 동작 폴백 (Phase 6 지식 스왑 invariant 유지) — knowledge-alt 스왑 회귀 없음.
- fake 모드(MODEL=fake)에서 API 키 없이 문진 흐름 전체 시연 가능.
- _persona.md 소유권 정리: 순서·항목=스키마, 태도·비밀보장·요약 형식=페르소나.
- scope 제외: knowledge-rehab/ 제작(후속 task), Phase 8 잔여 실배포 검증(본 task 이후), 재활 트랙 초안 종이 1장(코드 무관).
- 부모 task checklist cross-phase 메모에 Phase 10(D10) supersede 기록을 남길 것 — 단, checklist 수정은 phase 실행 단계의 작업 항목 (phase-intake는 계획 산출물만 생성).

## Risks

- 상담 도메인 민감정보: 위기 트랙 슬롯(자해 계획·수단·시도 이력)이 저장 데이터에 구조화되어 남는다. 부모 Phase 7에서 저장 데이터 점검을 가중했던 영역 — 신규 저장 표면은 기존 경로 재사용이라 제한적이나 phase 설계 시 재점검 필요.
- 레드플래그 우선 질문이 실모델 재량에 밀려 무시될 위험 → 프롬프트 주입 규칙을 명시하고 fake 모드 e2e(위기 시나리오)로 결정론 검증.
- 매 턴 슬롯 추출 방식이 실모드 API 호출 수·비용에 영향(D02, 사용자 결정) — 비용 증가는 escalation 기준.
- 현재 fake 스텁이 문진을 전혀 흉내내지 못하므로, fake 경로 확장 없이는 "데모 완성" 요구가 fake-satisfy될 위험 — e2e 4종이 이를 차단.

## Open Questions

- 데모 시나리오 산출물의 위치·구성(문서 형태) — phase-init에서 scope 확정.

## Memory Candidates

```yaml
memory_candidates:
  - type: decision
    scope: project
    claim: "lmwiki-chatbot-proto Phase 10(D10 선형 단계 스크립트)은 미실행 상태로 intake-slot-engine task가 supersede"
    evidence: "user_stated: origin verbatim §1 배경"
    confidence: user_stated
    promotion: candidate_only
  - type: constraint
    scope: project
    claim: "이 챗봇은 범용 엔진 — 도메인이 무엇을 수집하는지는 코드가 아니라 knowledge 데이터(_intake_schema.md 등 언더스코어 예약 파일)로만 선언한다"
    evidence: "user_stated: origin verbatim §1·§2"
    confidence: user_stated
    promotion: candidate_only
```

## Handoff Notes

- request.json의 rubric registry 실행(2026-07-11)에서 LB 클래스 2종(schema_file_format, slot_extraction_strategy)이 missing_canonical → 사용자 답변으로 explicit_defer 해소. 결과는 decisions.md와 request.json resolved_decisions 참조.
- phase-init 검증 필요: test_intake.py(Phase 9)의 기존 단언이 슬롯 흐름 도입 후에도 유지되는지(페르소나 주입·요약 경로 회귀), llm.ask 시그니처(doc_titles 파라미터가 fake 스텁 전용)가 슬롯 추출 확장과 어떻게 맞물릴지.
- 부모 cross-phase 메모 참고: 문서화 요구는 scope에 README 포함 권장 (Phase 3 회고).
- research.md: Research Need Gate `required: false` — 리포 내부로 닫힘. phase-init에서 외부 최신성 질문을 재개하지 말 것.
- Task directory artifacts live together at `docs/planning/intake-slot-engine/`: keep this file aligned with `request.json`, `decisions.md`, and `research.md`.

## Suggested Next Command

```bash
/phase-init --from docs/planning/intake-slot-engine/intake.md --slug intake-slot-engine
```
