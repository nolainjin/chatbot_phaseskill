# chat Domain — E2E Changelog

> Reverse chronological by scenario. Each entry is task-scoped.
> Scenario bodies contain no history; all change history accumulates here.

## chat-korean-roundtrip

→ Scenario: [scenarios/chat/chat-korean-roundtrip.md](../scenarios/chat/chat-korean-roundtrip.md)
→ Entry points affected: [api-chat](../entry-points.md#api-chat), [ui-chat](../entry-points.md#ui-chat)

### <a id="chat-korean-roundtrip-2026-07-27"></a> 2026-07-27 — task: bootstrap
- new scenario
- initial type `full`, priority `P0`, trigger `last_touch`, delegate_to `none`
- involved_globs: `app/chat.py`, `app/main.py`, `app/storage.py`, `app/llm.py`, `app/prompting.py`, `static/index.html`, `static/app.js`
- reason: 한국어 Windows cp949 로 인한 한글 왕복 실패가 이 레포에서 실제로 두 번 발생했고, `.github/workflows/cross-platform.yml` 이 이미 같은 불변식을 3-OS 로 지키고 있다. 그 CI 스텝의 로컬 대응물로 등록한다.

## chat-session-auth

→ Scenario: [scenarios/chat/chat-session-auth.md](../scenarios/chat/chat-session-auth.md)
→ Entry points affected: [api-chat](../entry-points.md#api-chat)

### <a id="chat-session-auth-2026-07-27"></a> 2026-07-27 — task: bootstrap
- new scenario
- initial type `partial`, priority `P0`, trigger `last_touch`, delegate_to `none`
- involved_globs: `app/main.py`, `app/chat.py`, `app/storage.py`
- reason: `app/main.py:43-48` 의 401 분기가 프로세스 메모리 세션 dict 에 종속적이다. 세션 스토어 분리 작업이 가장 먼저 깨뜨릴 수 있는 경계라 P0 로 등록한다.

## chat-injection-guardrail

→ Scenario: [scenarios/chat/chat-injection-guardrail.md](../scenarios/chat/chat-injection-guardrail.md)
→ Entry points affected: [api-chat](../entry-points.md#api-chat)

### <a id="chat-injection-guardrail-2026-07-27"></a> 2026-07-27 — task: bootstrap
- new scenario
- initial type `partial`, priority `P0`, trigger `last_touch`, delegate_to `none`
- involved_globs: `app/safety.py`, `app/chat.py`, `app/addiction.py`
- reason: 차단한 인젝션 발화가 이후 모델 컨텍스트에 재유입되지 않아야 한다는 불변식을 `tests/test_safety.py:162` 가 이미 가드하고 있다. `history` 를 대화 JSON 에서 복원하는 설계가 이 가드를 우회할 수 있어 P0 로 등록한다.

## chat-intake-slot-flow

→ Scenario: [scenarios/chat/chat-intake-slot-flow.md](../scenarios/chat/chat-intake-slot-flow.md)
→ Entry points affected: [api-chat](../entry-points.md#api-chat), [api-config](../entry-points.md#api-config)

### <a id="chat-intake-slot-flow-2026-07-27"></a> 2026-07-27 — task: bootstrap
- new scenario
- initial type `partial`, priority `P0`, trigger `last_touch`, delegate_to `none`
- involved_globs: `app/intake.py`, `app/chat.py`, `app/knowledge.py`, `knowledge/**`
- reason: 상담 접수 본류이면서, 세션 dict 직접 접근이 가장 많은 영역이다(`tests/test_slot_e2e.py` 한 파일에 14곳). 스토어 이행의 회귀 방어선으로 등록한다.
