---
task: lmwiki-chatbot-proto
created: 2026-07-11
source: rough_request
research_required: true
---

# LM Wiki 챗봇 프로토타입 — Intake

## Goal

지식 데이터만 교체하면 다른 분야로 전환 가능한 LM Wiki 기반 텍스트 챗봇 프로토타입을 만들어, 다다음 주(2026-07-20 주간)까지 저비용/무료 호스팅에 실제 작동 수준으로 배포한다.

성공 기준:
- 10턴 미만 텍스트 대화가 실제 배포 환경에서 동작
- 대화 내역이 JSON으로 저장되고 하루 1회 SQLite에 적재
- IP당 시간당 사용 제한이 실제로 동작
- 지식 데이터 교체만으로 다른 분야 챗봇으로 전환 가능(로직/콘텐츠 분리)

## Facts

사용자 명시 (origin.md verbatim 근거):
- LM Wiki 자료 기반 챗봇, 프로토타입 우선, 완성품보다 "실제 작동 수준" 우선
- 배포 목표: 다다음 주 = 2026-07-20 주간 (intake일 2026-07-11 기준 환산)
- 1차 버전은 텍스트 채팅 중심. 음성은 기본 챗봇 완성 이후 검토
- 한 사용자의 대화는 10턴 미만, 짧은 상담·질의응답 형태
- 챗봇 로직과 지식 콘텐츠 분리 — 지식 데이터 교체만으로 분야 전환 가능해야 함
- 프론트매터 등 문서 메타데이터를 활용할 수 있는 구조
- 대화 내역은 우선 JSON 파일 저장, 하루 1회 SQLite DB 적재
- 외부 AI 모델은 API 키를 입력해 호출하는 방식
- 초기에는 복잡한 서버 DB 대신 가볍고 단순한 구조
- 저비용 또는 무료 호스팅. 실배포 환경에서 JSON 저장·SQLite 적재 가능 여부 확인 필요(사용자가 직접 요구한 검증 항목)
- 동일 IP 1시간 5회 제한 + rate limit로 반복 호출·API 비용 공격 방지
- 보안 추가 검토 (필요시 보안 개발자 의견까지)
- Phase Skill 사용 순서·가이드에 맞춰 개발, 작은 범위 챗봇 하나에 집중
- 두찬님이 먼저 직접 구현하고 진행 중 피드백을 받는 방식

리포 확인 (2026-07-11):
- 홈 디렉토리에 기존 챗봇 프로젝트·LM Wiki 데이터 폴더 없음 (`~/*chatbot*`, `~/*wiki*` 미존재)
- 기존 phase 작업 패턴은 프로젝트-로컬 planning (`~/trend-viewer/docs/planning/`)
- 신규 프로젝트 루트 `/Users/jinduchan/lmwiki-chatbot/` 생성, planning 산출물은 `docs/planning/lmwiki-chatbot-proto/`
- 프로젝트 루트에 `PHASE-SKILLS.md` 없음 → 기본 프로파일로 진행 (`/phase-config init` 권장, 비차단)

## Assumptions

- "LM Wiki" = 프론트매터를 가진 마크다운 기반 지식베이스(LLM Wiki 형식)로 해석. → 확정(2026-07-11): SecondBrain wiki가 레퍼런스 (Open Questions 참조)
- "외부 AI 모델은 API 키를 입력해 호출" = 운영자가 서버 측에 API 키를 설정하는 방식 (D02 답변으로 확정: Anthropic + 운영자 키 서버측 env)
- "1시간에 5회" 제한의 단위는 '대화 세션' 기준 → 확정(2026-07-11, D05 + 사용자 목적 확인: 남용·비용 공격 방어)
- "10턴 미만" = 사용자 발화 기준 10턴 캡, 11번째 거부 → 확정(2026-07-11, Phase 2 구현·테스트 완료)
- 지식 데이터 규모는 프롬프트 컨텍스트 주입 또는 단순 검색으로 감당 가능한 소규모로 가정 (규모 확인 전까지 RAG/벡터DB 미도입)

## Constraints

- 저비용 또는 무료 호스팅 (핵심 제약 — 배포 플랫폼 선정을 지배)
- 챗봇 로직/지식 콘텐츠 분리 (지식 교체 가능성은 검증 가능한 형태여야 함)
- 저장 구조: JSON 우선 → 일 1회 SQLite 적재. 초기 서버 DB 금지
- rate limit 필수 (IP당 시간당 제한)
- 1차 텍스트 전용 (음성 제외)
- Phase Skill 순서·가이드 준수
- 일정: 2026-07-20 주간 배포 (약 10일)
- 두찬님 직접 구현 + 진행 중 피드백 (풀오토 개발 아님)

## Risks

- 무료 호스팅 다수가 ephemeral 파일시스템 → JSON/SQLite 파일이 재배포·재시작 시 유실될 수 있음. 플랫폼 선정을 잘못하면 저장 구조 전체가 무효화됨 (research.md에서 검증)
- API 비용 공격: IP rate limit는 IP 변조·프록시로 우회 가능. 상한(일일 총 사용량 캡, 토큰 상한) 없이는 비용 노출 지속
- API 키 노출: 클라이언트 측 키 노출 시 비용·보안 사고. 서버 측 보관 + 환경변수 필수
- 대화 내역 저장 = 이용자 데이터 취급. 개인정보 취급 고지·보존 기간 등 최소 검토 필요
- "지식 교체 가능"이 검증 없는 주장으로 남을 위험 — 실제로 두 번째 지식셋으로 스왑하는 테스트가 없으면 fake-satisfy 가능성 (capabilities.md 적대적 플래그 대상)
- 일정 리스크: 배포 포함 약 10일. 스코프가 조금만 커져도 초과

## Open Questions

전부 해소 (2026-07-11 사용자 답변):

- ~~LM Wiki 지식 데이터의 실제 파일 위치와 샘플 형식은?~~ → **SecondBrain wiki를 레퍼런스로** (`/Volumes/부부공용/SecondBrain/wiki/`). 프론트매터 스키마: `type / aliases / author / date / tags [/ cluster]`, 제목은 프론트매터가 아닌 본문 H1. 로더 요건(title 부재 시 H1→파일명 stem 폴백, 미지정 키 `meta` 보존)은 phase-01 스펙에 반영
- ~~첫 챗봇의 대상 도메인은?~~ → **상담 초기 면담 챗봇**으로 테스트. 실배포용 지식셋은 SecondBrain 스키마 기준으로 별도 작성 (Phase 6 스왑 검증 자체는 기존 2벌 샘플로 충분)
- ~~rate limit "5회"의 단위?~~ → 목적 = 해킹·프롬프트 인젝션·API 비용 공격 방어 (사용자 확인). D05 확정대로 **대화 세션 5회/시간** 유지 — 10턴 캡과 결합해 IP당 시간당 최대 50 LLM 호출 + DAILY_REQUEST_CAP 500 전역 캡. 프롬프트 인젝션 자체는 rate limit이 아닌 Phase 7 점검 항목 3에서 방어
- ~~"10턴 미만"의 턴 정의?~~ → **사용자 발화 기준** (추천 채택). 근거: 사용자 발화 1건 = LLM 호출 1회라 비용 단위와 일치하고 구현이 최단. Phase 2에서 이미 이 기준으로 구현·테스트 완료 (11번째 사용자 발화 거부)
- ~~대화 내역 저장 고지 필요?~~ → 현재는 **내부 시연이나 공개 서비스 전환 고려**. 고지 문구는 Phase 5에 이미 포함(FP8). 공개 전환 시 보존 기간·삭제 정책 추가 필요 — Phase 7에 기록

## Handoff Notes

- 결정 확정 (2026-07-11, decisions.md): 스택 = Python + FastAPI + 바닐라 HTML/JS 채팅 페이지 (D03), LLM = Anthropic Claude 단일 + 운영자 키 서버측 env (D02). 배포 플랫폼(D01)은 사용자가 명시 유보 — 후보 4종(Railway Hobby/Fly.io/Oracle Free VM/Hetzner)으로 압축, 배포 phase 전 확정. 그때까지 구현은 플랫폼 비종속(실 파일시스템 + 크론 사용 가능 전제)으로 설계할 것
- rubric front gate: 3개 LB 클래스 explicit_defer로 해소 완료 (`decision_rubrics.py` blocked: false, 2026-07-11). 재사용 rubric 등록은 사용자 선택으로 유보 (D04)
- 프로젝트 루트: `/Users/jinduchan/lmwiki-chatbot/` (이번 intake에서 신설). phase-init 실행 위치도 여기
- `PHASE-SKILLS.md` 부재 → 기본 프로파일. `/phase-config init` 1회 권장 (비차단)
- 배포 플랫폼 후보의 영속 디스크 지원 여부는 research.md 결론을 따를 것 — Research Need Gate `required: true`로 닫힘. phase-init에서 재조사 불요, 선정 플랫폼의 배포 phase에 반영만
- `capabilities.md` 의 load-bearing CAP(특히 적대적 플래그: 지식 스왑 검증, 실배포 rate limit, 일배치 실동작)은 phase 분해 시 보존 게이트로 추적
- 과거 메모리와의 충돌 없음. OMC `wiki` 스킬의 LLM Wiki와 이번 "LM Wiki 지식 데이터"가 같은 것인지는 미확인 — 데이터 파일 확보 시 확인
- Task directory artifacts live together at `docs/planning/lmwiki-chatbot-proto/`: keep this file aligned with `request.json`, `decisions.md`, and `research.md`.

## Memory Candidates

```yaml
memory_candidates:
  - type: constraint
    scope: project
    claim: "lmwiki-chatbot은 챗봇 로직과 지식 콘텐츠를 분리해 지식 데이터 교체만으로 분야 전환이 가능해야 한다."
    evidence: "user_stated: rough request §3"
    confidence: user_stated
    promotion: candidate_only
  - type: decision
    scope: project
    claim: "개발 방식은 두찬님 직접 구현 + 진행 중 피드백. 완성도보다 배포 가능 수준 우선."
    evidence: "user_stated: rough request §7"
    confidence: user_stated
    promotion: candidate_only
```

## Suggested Next Command

```bash
/phase-init --from docs/planning/lmwiki-chatbot-proto/intake.md --slug lmwiki-chatbot-proto
```
