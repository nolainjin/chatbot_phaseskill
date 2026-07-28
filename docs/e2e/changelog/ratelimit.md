# ratelimit Domain — E2E Changelog

> Reverse chronological by scenario. Each entry is task-scoped.
> Scenario bodies contain no history; all change history accumulates here.

## ratelimit-new-session-cap

→ Scenario: [scenarios/ratelimit/ratelimit-new-session-cap.md](../scenarios/ratelimit/ratelimit-new-session-cap.md)
→ Entry points affected: [api-chat](../entry-points.md#api-chat)

### <a id="ratelimit-new-session-cap-2026-07-27"></a> 2026-07-27 — task: bootstrap
- new scenario
- initial type `partial`, priority `P0`, trigger `last_touch`, delegate_to `none`
- involved_globs: `app/ratelimit.py`, `app/main.py`
- reason: `app/ratelimit.py:66-68` 주석에 단일 워커 전제가 이미 명시돼 있다. IP당 상한과 일일 캡이라는 서로 다른 두 카운터가 워커 수만큼 느슨해지는 것이 다중 워커 전환의 명시된 블로커 중 하나라 P0 로 등록한다.
- other scenarios affected: [chat-session-auth](./chat.md#chat-session-auth-2026-07-27) — 신규 세션 판정을 공유한다.
