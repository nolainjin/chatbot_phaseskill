---
phase: 2
title: 채팅 API + Claude 연동 + 10턴 제한
status: completed
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

- [x] app/llm.py: anthropic Python SDK, 키는 ANTHROPIC_API_KEY env, 모델은 MODEL env(기본 claude-haiku-4-5 — 사용자 확정 2026-07-11, D07), MODEL=fake 시 오프라인 스텁 응답(테스트·스모크용)
- [x] 시스템 프롬프트에 검색된 지식 문서 컨텍스트 주입 (지식/로직 분리 유지 — 프롬프트에 도메인 하드코딩 금지)
- [x] app/chat.py: 세션별 대화 상태, 사용자 발화 10턴 캡(턴 = 사용자 발화 기준, 사용자 확정 2026-07-11) — 초과 시 거부+안내 (11번째 발화 차단)
- [x] app/main.py: FastAPI, POST /api/chat {session_id, message} → {reply, turn, limit_reached}; static/ 마운트; 메시지 2,000자 상한·잘못된 입력 400
- [x] tests/test_chat.py: LLM mock으로 대화 루프·11번째 발화 거부·입력 검증 테스트 통과

## 영향 범위

Phase 3(저장 훅), 4(rate limit 미들웨어), 5(UI), 6(e2e)이 전부 이 API 계약 {reply, turn, limit_reached}에 의존한다. 계약 변경 시 후속 phase 스펙도 갱신 필요. 롤백 = 파일 삭제 (Phase 1은 독립적으로 유효).

## 검증

```bash
.venv/bin/python -m pytest tests/test_chat.py -q
```

> 참고: 1회차 실행 결과(2026-07-11, 커밋 9d9c0c4)는 사용자 요청으로 폐기 — intake open questions 답변 반영 후 재실행 예정.

## 실행 결과

### 2회차 (2026-07-11 13:46 KST) — completed

**상태**: completed
**소요 시간**: 약 20분
**진행 모델**: Claude sonnet

#### 요약
app/llm.py(Claude 연동 + MODEL=fake 스텁), app/chat.py(세션별 10턴 캡), app/main.py(FastAPI /api/chat + static 마운트)를 구현하고 tests/test_chat.py 8건으로 검증했다. 1회차 코드는 참고만 하고 현재 스펙 기준으로 새로 작성했으며, 1회차 테스트가 상담 도메인과 무관한 "비밀번호" 예시를 써서 실제로는 매칭되지 않던 문제를 발견해 도메인에 맞는 질의("라포 형성")로 교체했다.

#### 변경 파일
- `app/llm.py` (new, +37/-0)
- `app/chat.py` (new, +64/-0)
- `app/main.py` (new, +36/-0)
- `tests/test_chat.py` (new, +84/-0)

#### 검증 결과
- [x] 대화 루프 + 11번째 발화 거부 + 입력 검증: `.venv/bin/python -m pytest tests/test_chat.py -q` -> pass (8 passed)
- [x] 회귀 확인(Phase 1 포함 전체): `.venv/bin/python -m pytest -q` -> pass (13 passed)
- [x] static/ 미존재 상태 부팅 스모크: `python -c "from app.main import app; ..."` -> pass (라우트에 /api/chat 정상 등록, static 마운트 스킵)

starlette(1.3.1)+httpx(0.28.1) TestClient deprecation 경고는 cross-phase 메모대로 여전히 발생하나 테스트는 통과했다(실패 아님).

#### 추가 발견사항
1회차 test_chat.py는 "비밀번호를 잊어버렸어요"를 예시 질의로 썼는데, knowledge/ 디렉토리(상담 초기 면담 지식셋)에는 "비밀번호"라는 단어가 전혀 없어 검색이 항상 빈 결과를 반환하고 있었다(직접 재현 확인). 즉 그 assertion은 우연히 통과할 수 없는 상태였다 — 이번 재작성에서는 실제 지식셋에 있는 "라포 형성" 질의로 교체해 검색-인용 경로가 실제로 동작함을 검증했다.

#### 질문 / 결정 사항
없음
