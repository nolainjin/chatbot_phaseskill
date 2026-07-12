---
artifact: origin
task: intake-slot-engine
created: 2026-07-11
mutability: append_only
---

# 슬롯 스키마 문진 엔진 + 상담 접수면담 데모 — Origin (frozen 원 의도)

> **append-only / frozen.** 이 문서는 사용자의 원래 의도를 글자 그대로 동결한다.
> 한 번 기록된 verbatim 블록은 수정·삭제하지 않는다. 의도의 변화(축소·연기)는
> 이 파일이 아니라 `capabilities.md` 의 `reductions` 로만 기록하고, 항상
> `user_ack` 를 남긴다. verbatim 블록의 sha256 은 `capabilities.md` 의
> `origin_manifest.sha256` 과 재해시 대조되어 무결성을 강제한다.

## Verbatim Intent

원 요청을 가공·요약하지 말고 그대로 옮긴다. BEGIN/END 마커 사이의 내용만
해시 대상이며, 마커 주변 공백은 정규화(strip)된다.

<!-- BEGIN VERBATIM -->
lmwiki-chatbot 폴더에 새로운 작업을 해야합니다.
슬롯 스키마 문진 엔진 + 상담 접수면담 데모 (의사 시연용)

1. 배경
- 기존 task lmwiki-chatbot-proto(Phase 1~9 완료)의 후속 신규 task. 리포는 이 디렉토리.
- 현재 봇은 knowledge/_persona.md 산문 정책만으로 10턴 면담을 자유 진행 — 필수 항목
  누락을 막을 장치가 없다.
- 기존 Phase 10(선형 단계 스크립트, D10)은 미실행 상태로 이 요청이 대체(supersede)한다.
  기존 task checklist의 cross-phase 메모에 supersede 기록을 남길 것.
- 최종 고객은 재활병원 의사(초진 문진 챗봇, 트랙: 암재활/근골격/자율신경계)이지만, 이
  챗봇은 특정 병원 전용이 아니라 지식 데이터 교체로 분야를 전환하는 범용 엔진이다.
  이번 task는 엔진에 "무엇을 수집해야 하는지"를 지식 데이터로 선언하는 능력을 추가하고,
  이미 리포에 있는 상담(접수면담) 지식셋으로 데모 버전을 완성해 의사에게 시연하는
  것까지다. 재활병원 지식셋(knowledge-rehab/) 제작은 시연 후 의사 문진표를 확보한 뒤의
  후속 task — 이번 scope에서 명시적으로 제외.

2. 엔진 요구 (도메인 무관)
- knowledge 디렉토리의 언더스코어 예약 파일(가칭 _intake_schema.md)에 수집 항목(슬롯)을
  선언: 공통 슬롯 + 조건부 슬롯(활성 조건, 예: "트랙=위기면 자해 계획·수단 슬롯 활성화")
  + 필수/선택 + 우선순위 + 레드플래그 표시.
- 매 턴 시스템 프롬프트에 "채워진 슬롯 / 미충족 슬롯(우선순위순)"을 주입한다. 다음 질문의
  문구와 순서는 모델 재량, 완결성은 스키마가 보장한다.
- 한 발화에서 여러 슬롯을 동시에 추출할 수 있어야 한다 ("남편과 갈등 때문에 잠을 못
  자요" → 트랙=관계 + 정서 증상 동시 충족).
- 레드플래그 슬롯은 신호 감지 시 우선 질문한다.
- 10턴 캡은 예산이다: 우선순위 높은 슬롯부터 소비하고, 못 채운 슬롯은 요약에 "미확인"으로
  남긴다.
- 면담 종료 시 intake_summary는 채워진 스키마의 구조화 JSON으로 저장한다 (기존
  role="intake_summary" 턴 재사용).
- 스키마 부재·형식 오류 시 기존 페르소나/Q&A 동작으로 폴백한다 (Phase 6 지식 스왑
  invariant 유지).
- fake 모드(MODEL=fake)에서 API 키 없이 문진 흐름 전체를 시연할 수 있어야 한다.

3. 상담 접수면담 스키마 (기존 knowledge/ 셋에 추가)
- 트랙 3종: 개인 정서(우울·불안 등) / 관계(부부·가족·대인) / 위기(자·타해 위험).
  근거는 기존 지식 6종(접수-면접-질문지-구성, 위기-상황-스크리닝 등)과 정합할 것.
- 첫 질문은 개방형 하나 — 내담자 발화에서 트랙과 다른 슬롯을 동시에 잡는다.
- 트랙별 조건부 슬롯 예: 정서=증상 시기·일상 영향, 관계=대상·기간, 위기=계획·수단·
  시도 이력(레드플래그). 세부 항목은 기존 지식 문서에서 도출.
- _persona.md는 스키마와 소유권 충돌이 없게 정리 (순서·항목은 스키마 소유, 페르소나는
  태도·비밀보장·요약 형식만).
- 이 3-트랙 분기 구조가 재활병원 버전(암재활/근골격/자율신경)의 프리뷰라는 점을 데모
  시나리오에 반영.

4. 제약
- 기존 아키텍처 준수: 언더스코어 예약 파일 규칙, API 계약 {reply, turn, limit_reached}
  무변경, rate limit·저장 스키마·SQLite 배치 무변경.
- knowledge-alt/(커피, 스키마 없음) 스왑 시 기존 Q&A 폴백 회귀 없음 — 데모 마지막
  "지식 교체 시연"에 사용.
- 기존 task의 Phase 8 잔여(실배포 검증)는 이 task 완료 후 수행.

5. 검증
- fake 모드 e2e 시나리오 4종: 정서 / 관계 / 위기(레드플래그 우선 질문) / 혼합 발화
  (트랙 2개 슬롯 동시 채움).
- knowledge-alt 스왑 폴백 회귀 + 전체 pytest 통과.

intake가 끝나면 Suggested Next Command로 /phase-init --from ... --slug ...가 나옵니다. slug는 intake-slot-engine을 권합니다. 시연용 재활 트랙 초안 스키마 종이 1장은 코드와 무관하니, 데모 준비 시점에 저와 따로 만들면 됩니다 

해주세요. 다 끝나면 바로 다음 단계 하지마시고 제가 클리어 후 다음 단계로 갈 예정입니다.
<!-- END VERBATIM -->

## Parent Goal Trace

원 의도에서 바로 읽히는 parent-level intent/scope/constraint 를 구조화해 둔다.
`selected_task_block` 과 scope narrowing 항목은 아직 child slice 가 정해지지
않았다면 빈 값으로 유지하되, 키 자체는 유지한다.

```yaml
parent_goal_trace:
  original_user_words: "슬롯 스키마 문진 엔진 + 상담 접수면담 데모 (의사 시연용)"
  parent_origin_excerpt: "특정 자료에 종속되지 않고, 지식 데이터만 교체하면 다른 분야의 챗봇으로 전환 가능해야 함 — 즉, 챗봇 로직과 지식 콘텐츠를 분리 (lmwiki-chatbot-proto origin §3)"
  parent_project_intent: "지식 데이터 교체만으로 분야를 전환하는 범용 챗봇 엔진. 최종 고객은 재활병원 의사(초진 문진 챗봇, 트랙: 암재활/근골격/자율신경계)이나 엔진 자체는 병원 전용이 아님"
  parent_success_markers:
    - "지식 데이터 교체만으로 다른 분야 챗봇 전환 가능 (Phase 6 스왑 invariant)"
    - "10턴 미만 텍스트 대화"
    - "API 계약 {reply, turn, limit_reached} 유지"
    - "JSON 저장 + 일 1회 SQLite 적재, IP rate limit 유지"
    - "저비용/무료 호스팅 배포 (Phase 8 잔여 실배포 검증은 본 task 이후)"
  selected_task_scope:
    - "엔진: knowledge 디렉토리 언더스코어 예약 파일(가칭 _intake_schema.md)로 수집 슬롯 선언 능력 (공통/조건부/필수·선택/우선순위/레드플래그)"
    - "엔진: 매 턴 시스템 프롬프트에 채워진/미충족 슬롯(우선순위순) 주입"
    - "엔진: 한 발화 다중 슬롯 동시 추출, 레드플래그 우선 질문, 10턴 예산 소비 + 미확인 슬롯 요약"
    - "엔진: 면담 종료 시 intake_summary를 채워진 스키마 구조화 JSON으로 저장 (기존 role=\"intake_summary\" 턴 재사용)"
    - "엔진: 스키마 부재·형식 오류 시 기존 페르소나/Q&A 폴백"
    - "지식셋: 상담 접수면담 3-트랙 스키마 (정서/관계/위기) — 기존 knowledge/ 지식 6종과 정합"
    - "_persona.md 소유권 정리 (순서·항목=스키마, 태도·비밀보장·요약 형식=페르소나)"
    - "데모: fake 모드(MODEL=fake) 문진 흐름 전체 시연 + 지식 교체 시연(knowledge-alt) + 재활 3-트랙 프리뷰 포인트 반영"
  explicitly_out_of_scope_items:
    - "재활병원 지식셋(knowledge-rehab/) 제작 — 시연 후 의사 문진표 확보 뒤 후속 task"
    - "기존 task Phase 8 잔여(실배포 검증) — 본 task 완료 후 수행"
    - "시연용 재활 트랙 초안 스키마 종이 1장 — 코드와 무관, 데모 준비 시점에 사용자와 별도 작업"
  scope_narrowing_rationale: "의사 문진표를 아직 확보하지 못했으므로 재활 지식셋은 시연 이후로 미루고, 이번 task는 도메인 무관 슬롯 엔진 + 이미 리포에 있는 상담 지식셋 기반 데모까지로 한정"
  inherited_non_droppable_constraints:
    - "언더스코어 예약 파일 규칙 준수"
    - "API 계약 {reply, turn, limit_reached} 무변경"
    - "rate limit·저장 스키마·SQLite 배치 무변경"
    - "knowledge-alt/(커피, 스키마 없음) 스왑 시 기존 Q&A 폴백 회귀 없음 (Phase 6 지식 스왑 invariant)"
    - "fake 모드(MODEL=fake)에서 API 키 없이 시연 가능"
    - "기존 task checklist cross-phase 메모에 Phase 10(D10) supersede 기록"
  selected_task_block: "요청 전체가 이번 task (단일 task, 분할 없음) — 슬롯 스키마 엔진 + 상담 접수면담 스키마 + 의사 시연 데모"
  cross_task_acceptance_matrix:
    - task: lmwiki-chatbot-proto
      relation: "Phase 10(선형 단계 스크립트, D10)을 미실행 상태로 supersede. Phase 8 잔여(실배포 검증)는 본 task 완료 후 수행"
    - task: knowledge-rehab (미래 task)
      relation: "본 task의 3-트랙 스키마 구조가 재활병원 버전(암재활/근골격/자율신경)의 프리뷰. 의사 문진표 확보 후 착수"
```

## Integrity

```yaml
integrity:
  artifact: origin.md
  block: verbatim_intent
  # sha256 = capability_ledger.py origin-hash --origin <this file> 출력값.
  # capabilities.md origin_manifest.sha256 과 동일해야 한다.
  sha256: "b2635ab0094fd2cb2dde3d621252e5dc62ac23981add93c5ff4552e1571be37c"
```

## Append Log

> 동결 원칙상 위 verbatim 은 불변이다. 맥락 보강이 필요하면 아래에 append 만 한다.

- 2026-07-11 — intake 시점 맥락: 부모 task lmwiki-chatbot-proto checklist 기준 Phase 1~7·9 completed, Phase 8 needs_user(4/5), Phase 10 pending(0/5). 사용자 지시: intake 완료 후 다음 단계(phase-init)로 자동 진행하지 말 것 — 사용자가 /clear 후 직접 진행.
