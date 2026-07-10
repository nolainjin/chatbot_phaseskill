---
artifact: capabilities
task: lmwiki-chatbot-proto
created: 2026-07-11
origin: origin.md
---

# LM Wiki 챗봇 프로토타입 — Capability Ledger (CAP 원장)

핸드오프(intake → init → run → e2e)를 가로질러 보존해야 하는 능력(CAP)의 원장.
`capability_ledger.py validate` 가 필드 타입·status enum·reduction 무결성·evidence
존재·origin sha256 재해시를 결정론적으로 검증한다. 아래 YAML 블록이 검증 대상이며,
어드버서리얼 플래그는 YAML 밖 "## Adversarial Flags" 섹션에만 둔다.

```yaml
capabilities:
  - id: CAP01
    statement: "사용자와 텍스트 기반 채팅으로 대화한다 (1차 버전 텍스트 채팅 중심)"
    origin: "1차 버전은 텍스트 채팅 중심"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP02
    statement: "제공된 LM Wiki 지식 데이터를 로딩해 답변 근거로 사용한다"
    origin: "현재 제공받은 LM Wiki 지식 데이터를 사용"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP03
    statement: "사용자 질문에 LM Wiki 지식을 근거로 응답하는 질의응답 대화 루프가 실제 동작한다"
    origin: "LM Wiki 자료를 기반으로 챗봇 제작 / 짧은 상담·질의응답 형태로 설계 / 실제 작동하는 수준으로 먼저 구현"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP04
    statement: "한 사용자의 한 대화 세션을 10턴 미만으로 제한하고 실제로 집행한다"
    origin: "한 사용자의 대화는 10턴 미만으로 제한"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP05
    statement: "챗봇 로직과 지식 콘텐츠를 분리된 구조로 구현한다"
    origin: "즉, 챗봇 로직과 지식 콘텐츠를 분리"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP06
    statement: "로직 무수정으로 지식 데이터만 교체하면 다른 분야 챗봇으로 전환되며, 실제 데이터 스왑으로 증명된다"
    origin: "특정 자료에 종속되지 않고, 지식 데이터만 교체하면 다른 분야의 챗봇으로 전환 가능해야 함"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP07
    statement: "프론트매터 등 문서 메타데이터를 파싱해 활용할 수 있는 구조를 갖춘다"
    origin: "프론트매터 등 문서 메타데이터를 활용할 수 있는 구조"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP08
    statement: "대화 내역을 JSON 파일로 저장한다"
    origin: "대화 내역을 우선 JSON 파일로 저장"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP09
    statement: "하루 1회 JSON 데이터를 SQLite DB에 적재하는 배치가 스케줄되어 실제 실행된다"
    origin: "하루에 한 번 JSON 데이터를 SQLite DB에 적재"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP10
    statement: "외부 AI 모델을 API 키 입력 방식으로 호출한다"
    origin: "외부 AI 모델은 API 키를 입력해 호출하는 방식"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP11
    statement: "저비용 또는 무료 호스팅 환경에 실제 배포되어 실행된다 (localhost 아님)"
    origin: "가능하면 저비용 또는 무료 호스팅 환경에서 실행"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP12
    statement: "실제 배포 환경에서 JSON 저장과 SQLite 적재가 동작하는지 확인한다"
    origin: "실제 배포 환경에서 JSON 저장과 SQLite 적재가 가능한지 확인 필요"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP13
    statement: "동일 IP는 1시간에 5회 이상 사용할 수 없도록 rate limit 을 실제로 집행한다"
    origin: "동일 IP는 1시간에 5회 이상 사용할 수 없도록 제한 / 반복 호출·API 비용 공격을 막기 위한 Rate Limit 적용"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP14
    statement: "배포 전 보안상 추가 문제가 없는지 AI 로 별도 보안 검토를 수행한다"
    origin: "보안상 추가 문제가 없는지 별도 검토 / AI 검토"
    load_bearing: true
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP15
    statement: "음성 기능은 기본 챗봇 완성 이후 검토 대상 (이번 프로토타입 범위 아님)"
    origin: "음성 기능은 기본 챗봇 완성 이후 검토"
    load_bearing: false
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP16
    statement: "PDF·Markdown 파일을 LM Wiki 구조로 일괄 변환하는 기능은 추후 고려 대상 (이번 범위 아님)"
    origin: "PDF, Markdown 파일 등을 LM Wiki 구조로 일괄 변환하는 기능도 추후 고려"
    load_bearing: false
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP17
    statement: "복잡한 서버 DB 는 초기 도입 제외이며 가볍고 단순한 구조 유지 (추후 검토 대상)"
    origin: "초기에는 복잡한 서버 DB보다 가볍고 단순한 구조로 구현"
    load_bearing: false
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP18
    statement: "100% 완성도·커스터마이징·성능 개선은 배포 이후 과제 (이번 범위 아님)"
    origin: "100% 완성보다 우선 배포 가능한 수준을 만들고, 이후 커스터마이징과 성능 개선"
    load_bearing: false
    status: live
    evidence: []
    reduction_ref: ""
  - id: CAP19
    statement: "필요 시 보안 개발자(사람) 의견을 확인한다 (조건부, 상황에 따라 판단)"
    origin: "AI 검토뿐 아니라 필요하면 보안 개발자 의견도 확인"
    load_bearing: false
    status: live
    evidence: []
    reduction_ref: ""

reductions: []

origin_manifest:
  artifact: origin.md
  block: verbatim_intent
  sha256: "6d9f1f0f8630f9c7d04b78973982bc16fc98c1ce032a8d10f83e4e9677c85773"
```

## Adversarial Flags

토큰·노력을 아끼려는 게으른 구현자가 드롭하거나 가짜로 충족시킬 위험이 큰 CAP.

- **CAP06 — 지식 스왑 전환**: 로직/지식 분리를 "코드상 분리했다"고만 주장하고, 실제로 다른 분야 지식 데이터를 넣어 갈아끼워 동작을 증명하는 스왑 테스트를 건너뛰기 쉽다. 전환 증명 = 실제 데이터 교체 e2e 없이는 미충족.
- **CAP05 — 로직/콘텐츠 분리**: 하드코딩된 지식이 로직에 섞여 있어도 겉으로는 분리된 것처럼 보이게 만들 수 있다. CAP06 스왑으로만 진짜 분리가 드러난다.
- **CAP13 — IP rate limit**: 코드에만 넣고 실제로 집행되지 않거나(메모리 리셋·배포 환경에서 IP 식별 실패), 임계치(1시간 5회)를 느슨하게 잡아 사실상 무력화하기 쉽다. 실제 6번째 호출이 차단되는지 검증 필요.
- **CAP09 — JSON→SQLite 일 1회 배치**: 적재 함수만 만들어두고 스케줄러(cron 등)를 배포 환경에 실제로 걸어 매일 도는지는 확인 안 하기 쉽다. 무료 호스팅은 크론·백그라운드 잡이 제한되는 경우가 많아 "코드 존재"와 "실제 실행"의 간극이 크다.
- **CAP11 — 저비용/무료 호스팅 실배포**: localhost 데모로 갈음하고 실제 무료 호스트에 라이브 배포는 안 하기 쉽다. 공개 URL로 접근 가능해야 충족.
- **CAP12 — 배포 환경 저장/적재 검증**: 무료 호스트는 파일시스템이 임시(ephemeral)·읽기전용인 경우가 많아 JSON 저장·SQLite 적재가 로컬에선 되고 배포에선 깨진다. 로컬 통과로 배포 검증을 대체하기 쉬운 대표 항목.
- **CAP04 — 10턴 제한**: 상수만 선언하고 실제 세션 카운팅·차단을 구현하지 않아 11턴째가 그대로 통과할 수 있다.
- **CAP07 — 프론트매터 메타데이터 활용**: 프론트매터를 파싱만 하고 실제 답변·검색에 쓰지 않거나, 통째로 무시하고 본문만 넣기 쉽다.
- **CAP14 — 배포 전 보안 검토**: "문제 없어 보인다"로 뭉개고 실제 별도 보안 검토 절차(입력 검증·키 노출·rate limit 우회 등)를 생략하기 쉽다.
