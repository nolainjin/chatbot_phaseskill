---
artifact: origin
task: lmwiki-chatbot-proto
created: 2026-07-11
mutability: append_only
---

# LM Wiki 챗봇 프로토타입 — Origin (frozen 원 의도)

> **append-only / frozen.** 이 문서는 사용자의 원래 의도를 글자 그대로 동결한다.
> 한 번 기록된 verbatim 블록은 수정·삭제하지 않는다. 의도의 변화(축소·연기)는
> 이 파일이 아니라 `capabilities.md` 의 `reductions` 로만 기록하고, 항상
> `user_ack` 를 남긴다. verbatim 블록의 sha256 은 `capabilities.md` 의
> `origin_manifest.sha256` 과 재해시 대조되어 무결성을 강제한다.

## Verbatim Intent

원 요청을 가공·요약하지 말고 그대로 옮긴다. BEGIN/END 마커 사이의 내용만
해시 대상이며, 마커 주변 공백은 정규화(strip)된다.

<!-- BEGIN VERBATIM -->
챗봇 프로토타입 조건

1. 목적과 일정

LM Wiki 자료를 기반으로 챗봇 제작

우선 프로토타입 형태로 개발

다다음 주 배포를 목표

처음부터 완성품보다, 실제 작동하는 수준으로 먼저 구현 


2. 기본 대화 방식

1차 버전은 텍스트 채팅 중심

음성 기능은 기본 챗봇 완성 이후 검토

한 사용자의 대화는 10턴 미만으로 제한

짧은 상담·질의응답 형태로 설계 


3. 지식 구조

현재 제공받은 LM Wiki 지식 데이터를 사용

특정 자료에 종속되지 않고, 지식 데이터만 교체하면 다른 분야의 챗봇으로 전환 가능해야 함

즉, 챗봇 로직과 지식 콘텐츠를 분리

PDF, Markdown 파일 등을 LM Wiki 구조로 일괄 변환하는 기능도 추후 고려

프론트매터 등 문서 메타데이터를 활용할 수 있는 구조 


4. 데이터 저장 구조

대화 내역을 우선 JSON 파일로 저장

하루에 한 번 JSON 데이터를 SQLite DB에 적재

외부 AI 모델은 API 키를 입력해 호출하는 방식

초기에는 복잡한 서버 DB보다 가볍고 단순한 구조로 구현 


5. 배포 환경과 비용

가능하면 저비용 또는 무료 호스팅 환경에서 실행

실제 배포 환경에서 JSON 저장과 SQLite 적재가 가능한지 확인 필요 


6. 사용량 및 공격 방지

동일 IP는 1시간에 5회 이상 사용할 수 없도록 제한

반복 호출, API 비용 공격, 무분별한 사용을 막기 위한 Rate Limit 적용

보안상 추가 문제가 없는지 별도 검토

AI 검토뿐 아니라 필요하면 보안 개발자 의견도 확인 


7. 개발 방식

Phase Skill의 사용 순서와 가이드에 맞춰 개발

먼저 작은 범위의 챗봇 하나에 집중

100% 완성보다 우선 배포 가능한 수준을 만들고, 이후 커스터마이징과 성능 개선

두찬님이 먼저 직접 구현해보고, 진행 과정에서 피드백을 받는 방식  교체 가능한 LM Wiki 지식베이스를 바탕으로, 10턴 이내의 텍스트 대화를 제공하고, 대화는 JSON→SQLite로 저장하며, IP별 사용량 제한을 둔 저비용 배포형 챗봇 프로토타입 제작이 필요합니다.
<!-- END VERBATIM -->

## Parent Goal Trace

원 의도에서 바로 읽히는 parent-level intent/scope/constraint 를 구조화해 둔다.
`selected_task_block` 과 scope narrowing 항목은 아직 child slice 가 정해지지
않았다면 빈 값으로 유지하되, 키 자체는 유지한다.

```yaml
parent_goal_trace:
  original_user_words: "교체 가능한 LM Wiki 지식베이스를 바탕으로, 10턴 이내의 텍스트 대화를 제공하고, 대화는 JSON→SQLite로 저장하며, IP별 사용량 제한을 둔 저비용 배포형 챗봇 프로토타입 제작이 필요합니다."
  parent_origin_excerpt: "챗봇 프로토타입 조건 — 1.목적과 일정 / 2.기본 대화 방식 / 3.지식 구조 / 4.데이터 저장 구조 / 5.배포 환경과 비용 / 6.사용량 및 공격 방지 / 7.개발 방식"
  parent_project_intent: "지식 데이터만 교체하면 다른 분야로 전환 가능한 챗봇 엔진 프로토타입을 다다음 주(2026-07-20 주간)까지 배포 가능한 수준으로 구현"
  parent_success_markers:
    - "다다음 주(2026-07-20 주간) 배포"
    - "실제 작동하는 수준 (100% 완성 아님)"
    - "지식 데이터 교체만으로 다른 분야 챗봇 전환 가능"
    - "10턴 미만 텍스트 대화"
    - "대화 내역 JSON 저장 + 일 1회 SQLite 적재"
    - "IP당 시간당 사용 제한 (rate limit)"
    - "저비용/무료 호스팅에서 실행"
  selected_task_scope:
    - "텍스트 채팅 챗봇 프로토타입 (단일 챗봇, 작은 범위)"
    - "LM Wiki 지식 데이터 로딩 + 프론트매터 메타데이터 활용 구조"
    - "챗봇 로직 / 지식 콘텐츠 분리 아키텍처"
    - "대화 JSON 저장 + 일 1회 SQLite 적재 파이프라인"
    - "외부 AI API 키 기반 호출"
    - "IP rate limit + API 비용 공격 방지"
    - "저비용/무료 배포 환경 선정·검증"
  explicitly_out_of_scope_items:
    - "음성 기능 (기본 챗봇 완성 이후 검토)"
    - "PDF/Markdown → LM Wiki 구조 일괄 변환 기능 (추후 고려)"
    - "복잡한 서버 DB (초기 제외)"
    - "100% 완성도·커스터마이징·성능 개선 (배포 이후)"
  scope_narrowing_rationale: "프로토타입 단일 task — 원 요청 전체가 이번 task 범위이며 child slice 분할 없음"
  inherited_non_droppable_constraints:
    - "챗봇 로직과 지식 콘텐츠 분리 (지식 교체 가능성)"
    - "저비용 또는 무료 호스팅"
    - "IP rate limit 적용"
    - "대화 JSON 저장 → 일 1회 SQLite 적재"
    - "Phase Skill 사용 순서·가이드 준수"
    - "두찬님 직접 구현 + 진행 중 피드백 방식"
  selected_task_block: "챗봇 프로토타입 전체 (단일 task, 분할 없음)"
  cross_task_acceptance_matrix: []
```

## Integrity

```yaml
integrity:
  artifact: origin.md
  block: verbatim_intent
  # sha256 = capability_ledger.py origin-hash --origin <this file> 출력값.
  # capabilities.md origin_manifest.sha256 과 동일해야 한다.
  sha256: "6d9f1f0f8630f9c7d04b78973982bc16fc98c1ce032a8d10f83e4e9677c85773"
```

## Append Log

> 동결 원칙상 위 verbatim 은 불변이다. 맥락 보강이 필요하면 아래에 append 만 한다.

- 2026-07-11 — intake 시점 맥락: "다다음 주"는 2026-07-20 주간으로 해석 (intake 일 2026-07-11 기준). LM Wiki 지식 데이터의 실제 파일 위치는 intake 시점에 미확인.
