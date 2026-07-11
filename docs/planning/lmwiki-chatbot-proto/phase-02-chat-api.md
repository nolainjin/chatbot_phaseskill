---
phase: 2
title: 채팅 API + Claude 연동 + 10턴 제한
status: pending
depends_on: [1]
scope:
  - app/main.py
  - app/llm.py
  - app/chat.py
  - tests/test_chat.py
intervention_likely: false
intervention_reason: ""
executor: sonnet
load_bearing: ""
e2e_refs: []
e2e_triggers: []
phase_context:
  baseline: "missing"
  adoption: "bootstrap"
  coverage: "standard"
  enforcement_during_run: "warn"
  materialize_at: "finalization"
---

# Phase 2: 채팅 API + Claude 연동 + 10턴 제한

> **범위**: Backend
> **난이도**: M
> **의존성**: Phase 1
> **영향 파일**: `app/main.py` (신규), `app/llm.py` (신규), `app/chat.py` (신규)

## 배경

챗봇의 대화 루프 자체를 만든다. 사용자 결정: LLM은 Anthropic Claude 단일 + 운영자 키 서버측 env(D02), 기본 모델은 claude-haiku-4-5(D07, MODEL env로 교체 가능). 한 사용자의 대화는 10턴 미만으로 제한하고(origin §2, CAP04), 11번째 발화는 실제로 거부되어야 한다 — 상수 선언만 하고 차단하지 않는 fake-satisfy가 capabilities.md 적대적 플래그에 올라 있다.

## 심볼 인벤토리

- `app.llm.ask`
  - [NEW]
- `app.chat.ChatSession`
  - [NEW]
- `app.chat.handle_message`
  - [NEW]
- `app.main.app`
  - [NEW]

## 설계

```
POST /api/chat {session_id, message}
    ratelimit 검사는 Phase 4에서 붙음 (이 phase에서는 자리만)
    입력 검증: message 2,000자 상한, 비문자열/빈값 400
    session = 세션 저장소[session_id]      # 메모리 dict
    if session.turns >= 10: return {limit_reached: true, 안내문}
    docs = knowledge.search(message)       # Phase 1 로더
    reply = llm.ask(system=지식 컨텍스트, history=session.history, user=message)
    session 기록, return {reply, turn, limit_reached: false}
```

- `app/llm.py`: anthropic SDK. `anthropic.Anthropic()`은 ANTHROPIC_API_KEY env를 자동 인식한다(claude-api 레퍼런스, E07). `client.messages.create(model=settings.MODEL, max_tokens=1024, system=..., messages=...)` 호출 후 `response.content`에서 type=="text" 블록을 꺼낸다.
- `MODEL=fake`면 API를 호출하지 않고 "검색된 문서 제목을 인용하는 스텁 응답"을 돌려준다. 테스트·스모크가 키 없이 돌기 위한 스위치다.
- 시스템 프롬프트는 "지식 문서 내용"만 주입하고 도메인 문구를 하드코딩하지 않는다 — Phase 6 스왑 검증이 이 규칙을 확인한다.
- static/ 마운트를 이 phase에서 미리 걸어 Phase 5가 main.py를 다시 수정하지 않게 한다 (병렬성 확보, P05-C1).
- 세션 상태는 메모리 dict. 재시작 시 소실은 프로토타입 수용 범위(대화 내역 영속은 Phase 3 JSON 저장이 담당).

## 체크리스트

- [ ] app/llm.py: anthropic Python SDK, 키는 ANTHROPIC_API_KEY env, 모델은 MODEL env(기본 claude-haiku-4-5 — 사용자 확정 2026-07-11, D07), MODEL=fake 시 오프라인 스텁 응답(테스트·스모크용)
- [ ] 시스템 프롬프트에 검색된 지식 문서 컨텍스트 주입 (지식/로직 분리 유지 — 프롬프트에 도메인 하드코딩 금지)
- [ ] app/chat.py: 세션별 대화 상태, 사용자 발화 10턴 캡 — 초과 시 거부+안내 (11번째 발화 차단)
- [ ] app/main.py: FastAPI, POST /api/chat {session_id, message} → {reply, turn, limit_reached}; static/ 마운트; 메시지 2,000자 상한·잘못된 입력 400
- [ ] tests/test_chat.py: LLM mock으로 대화 루프·11번째 발화 거부·입력 검증 테스트 통과

## 영향 범위

Phase 3(저장 훅), 4(rate limit 미들웨어), 5(UI), 6(e2e)이 전부 이 API 계약 {reply, turn, limit_reached}에 의존한다. 계약 변경 시 후속 phase 스펙도 갱신 필요. 롤백 = 파일 삭제 (Phase 1은 독립적으로 유효).

## 검증

```bash
.venv/bin/python -m pytest tests/test_chat.py -q
```
