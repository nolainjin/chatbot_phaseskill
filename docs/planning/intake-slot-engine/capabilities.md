---
artifact: capabilities
task: intake-slot-engine
created: 2026-07-11
origin: origin.md
---

# 슬롯 스키마 문진 엔진 + 상담 접수면담 데모 — Capability Ledger (CAP 원장)

핸드오프(intake → init → run → e2e)를 가로질러 보존해야 하는 능력(CAP)의 원장.
`capability_ledger.py validate` 가 필드 타입·status enum·reduction 무결성·evidence
존재·origin sha256 재해시를 결정론적으로 검증한다. 아래 YAML 블록이 검증 대상이며,
어드버서리얼 플래그는 YAML 밖 "## Adversarial Flags" 섹션에만 둔다.

```yaml
capabilities:
  - id: CAP01
    statement: "knowledge 언더스코어 예약 파일(_intake_schema.md)에 수집 슬롯을 선언한다 (공통 슬롯 + 필수·선택 + 우선순위 + 레드플래그 표시 메타)"
    origin: "언더스코어 예약 파일(가칭 _intake_schema.md)에 수집 항목(슬롯)을 선언"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP02
    statement: "조건부 슬롯의 활성 조건을 스키마에 선언하고 엔진이 조건 충족 시에만 활성화한다 (예: 트랙=위기 → 자해 계획·수단 슬롯)"
    origin: "조건부 슬롯(활성 조건, 예: '트랙=위기면 자해 계획·수단 슬롯 활성화')"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP03
    statement: "매 턴 시스템 프롬프트에 채워진 슬롯과 미충족 슬롯(우선순위순)을 주입한다"
    origin: "매 턴 시스템 프롬프트에 '채워진 슬롯 / 미충족 슬롯(우선순위순)'을 주입"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP04
    statement: "한 발화에서 여러 슬롯을 동시에 추출한다 (예: '남편과 갈등 때문에 잠을 못 자요' → 트랙=관계 + 정서 증상)"
    origin: "한 발화에서 여러 슬롯을 동시에 추출할 수 있어야 한다"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP05
    statement: "레드플래그 슬롯 신호를 감지하면 우선 질문한다"
    origin: "레드플래그 슬롯은 신호 감지 시 우선 질문한다"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP06
    statement: "10턴 캡을 예산으로 삼아 우선순위 높은 슬롯부터 소비한다"
    origin: "10턴 캡은 예산이다: 우선순위 높은 슬롯부터 소비"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP07
    statement: "10턴 안에 못 채운 슬롯은 요약에 '미확인'으로 남긴다"
    origin: "못 채운 슬롯은 요약에 '미확인'으로 남긴다"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP08
    statement: "면담 종료 시 intake_summary를 채워진 스키마의 구조화 JSON으로 저장한다 (기존 role=intake_summary 턴 재사용)"
    origin: "intake_summary는 채워진 스키마의 구조화 JSON으로 저장한다"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP09
    statement: "스키마 부재·형식 오류 시 기존 페르소나/Q&A 동작으로 폴백한다 (Phase 6 지식 스왑 invariant 유지)"
    origin: "스키마 부재·형식 오류 시 기존 페르소나/Q&A 동작으로 폴백한다"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP10
    statement: "fake 모드(MODEL=fake)에서 API 키 없이 문진 흐름 전체를 시연할 수 있다"
    origin: "fake 모드(MODEL=fake)에서 API 키 없이 문진 흐름 전체를 시연할 수 있어야 한다"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP11
    statement: "상담 접수면담 3-트랙(정서/관계/위기) 스키마를 기존 knowledge/ 셋에 추가하며 기존 지식 6종과 정합한다"
    origin: "트랙 3종: 개인 정서 / 관계 / 위기. 근거는 기존 지식 6종과 정합할 것"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP12
    statement: "첫 질문은 개방형 하나로, 내담자 발화에서 트랙과 다른 슬롯을 동시에 잡는다"
    origin: "첫 질문은 개방형 하나 — 내담자 발화에서 트랙과 다른 슬롯을 동시에 잡는다"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP13
    statement: "트랙별 조건부 슬롯 세부항목을 기존 지식 문서에서 도출한다 (정서=시기·일상 영향, 관계=대상·기간, 위기=계획·수단·시도 이력)"
    origin: "트랙별 조건부 슬롯 예... 세부 항목은 기존 지식 문서에서 도출"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP14
    statement: "_persona.md를 스키마와 소유권 충돌 없게 정리한다 (순서·항목=스키마 소유, 페르소나=태도·비밀보장·요약 형식만)"
    origin: "_persona.md는 스키마와 소유권 충돌이 없게 정리"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP15
    statement: "3-트랙 분기 구조가 재활병원 버전(암재활/근골격/자율신경) 프리뷰라는 점을 데모 시나리오에 반영한다"
    origin: "이 3-트랙 분기 구조가 재활병원 버전의 프리뷰라는 점을 데모 시나리오에 반영"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP16
    statement: "API 계약 {reply, turn, limit_reached}을 무변경으로 유지한다"
    origin: "API 계약 {reply, turn, limit_reached} 무변경"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP17
    statement: "rate limit·저장 스키마·SQLite 배치를 무변경으로 유지한다"
    origin: "rate limit·저장 스키마·SQLite 배치 무변경"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP18
    statement: "knowledge-alt(커피, 스키마 없음) 스왑 시 기존 Q&A 폴백에 회귀가 없다"
    origin: "knowledge-alt/(커피, 스키마 없음) 스왑 시 기존 Q&A 폴백 회귀 없음"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP19
    statement: "데모 마지막에 knowledge-alt 스왑으로 지식 교체 시연을 수행한다"
    origin: "데모 마지막 '지식 교체 시연'에 사용"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP20
    statement: "fake 모드 e2e 시나리오 — 정서 트랙 문진 흐름이 통과한다"
    origin: "fake 모드 e2e 시나리오 4종: 정서 ..."
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP21
    statement: "fake 모드 e2e 시나리오 — 관계 트랙 문진 흐름이 통과한다"
    origin: "fake 모드 e2e 시나리오 4종: ... 관계 ..."
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP22
    statement: "fake 모드 e2e 시나리오 — 위기 트랙에서 레드플래그가 우선 질문됨을 검증한다"
    origin: "위기(레드플래그 우선 질문)"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP23
    statement: "fake 모드 e2e 시나리오 — 혼합 발화에서 트랙 2개 슬롯이 동시에 채워짐을 검증한다"
    origin: "혼합 발화 (트랙 2개 슬롯 동시 채움)"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP24
    statement: "전체 pytest 스위트가 통과한다"
    origin: "전체 pytest 통과"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP25
    statement: "부모 task lmwiki-chatbot-proto checklist의 cross-phase 메모에 Phase 10(선형 단계 스크립트, D10) supersede 기록을 남긴다"
    origin: "기존 task checklist의 cross-phase 메모에 supersede 기록을 남길 것"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""

reductions: []

origin_manifest:
  artifact: origin.md
  block: verbatim_intent
  sha256: "b2635ab0094fd2cb2dde3d621252e5dc62ac23981add93c5ff4552e1571be37c"
```

## Adversarial Flags

토큰·노력을 아끼려는 게으른 구현자가 드롭하거나 가짜로 충족시킬 위험이 큰 load-bearing CAP.

- **CAP02 — 조건부 슬롯 활성 조건**: 모든 슬롯을 정적으로 선언해 조건부 활성 로직을 아예 넣지 않거나, 조건을 선언만 하고 트리거를 배선하지 않기 쉽다. 트랙=위기에서 자해 계획·수단 슬롯이 실제로 활성화되는지 검증 필요.
- **CAP04 — 한 발화 다중 슬롯 추출**: 추출기가 한 발화에서 언제나 슬롯 하나만 채우면서 "다중 추출 지원"으로 위장하기 쉽다. 예시 발화로 트랙+증상 2슬롯이 실제 동시 충족되는지 확인.
- **CAP05 — 레드플래그 우선 질문**: 레드플래그 슬롯을 스키마에 선언만 하고 감지·우선 질문 트리거는 배선하지 않아 실전에서 발동 안 하기 쉽다.
- **CAP09 — 스키마 폴백**: 스키마 경로를 애초에 배선하지 않아 "폴백이 된다"고 주장하지만, 스키마 경로가 있을 때 폴백만 남아있고 스키마 경로가 죽은 경우와 구분 안 됨. 스키마 있음/없음 두 경로가 모두 실동작하는지 확인.
- **CAP10 — fake 모드 전체 시연**: fake 모드가 스키마 흐름을 실제로 태우지 않고 고정 응답만 뱉으며 "시연 가능"으로 위장하기 쉽다. fake 모드에서도 슬롯 주입·추출·요약이 실제로 도는지 확인.
- **CAP18 — knowledge-alt 폴백 회귀**: 스키마 없는 knowledge-alt 스왑에서 Q&A 폴백이 "된다"고만 주장하고, 실제로 스키마 경로가 배선된 상태에서 스왑했을 때 회귀 없이 폴백하는지는 검증 안 하기 쉽다.
- **CAP22 — e2e 위기 레드플래그 우선**: e2e가 위기 트랙을 태우기만 하고 레드플래그가 다른 슬롯보다 먼저 질문됐다는 순서 단언 없이 통과 처리하기 쉽다.
- **CAP23 — e2e 혼합 발화 2슬롯**: e2e가 혼합 발화 시나리오를 통과시키되 실제로는 슬롯 하나만 채워진 상태를 단언 없이 넘기기 쉽다. 2슬롯 동시 충족 단언 필요.
- **CAP25 — supersede 기록 bookkeeping**: 코드 작업에 밀려 부모 checklist cross-phase 메모에 Phase 10(D10) supersede 기록 남기기를 조용히 누락하기 쉽다.
