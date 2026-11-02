---
id: chat-injection-guardrail
type: partial
priority: P0
domain: chat
trigger: last_touch
delegate_to: none
entry_points:
  - api-chat
involved_globs:
  - app/safety.py
  - app/chat.py
  - app/addiction.py
last_change:
  date: 2026-07-27
  task: bootstrap
  ref: changelog/chat.md#chat-injection-guardrail-2026-07-27
---

# chat-injection-guardrail: 프롬프트 인젝션 차단과 컨텍스트 격리

> Change history: [chat changelog](../../changelog/chat.md#chat-injection-guardrail)

인젝션성 발화는 LLM 에 넘기지 않는다. 그런데 이 시나리오가 지키는 진짜 불변식은
"차단"이 아니라 **차단한 발화가 이후 모델 컨텍스트에 다시 들어가지 않는 것**이다.

`app/chat.py:405-407` 이 그 지점이다. 인젝션 차단 분기에서 `storage.append_turn` 은
user 턴과 assistant 턴을 **둘 다** 대화 JSON 에 쓰지만, `session.history.append` 는
**assistant 턴만** 추가한다. 차단된 user 발화를 의도적으로 LLM 컨텍스트 밖에 두는
비대칭이다.

따라서 `history` 를 대화 JSON 에서 복원하는 설계는 이 비대칭을 반드시 재현해야 한다.
저장된 턴을 순진하게 되읽으면 차단했던 인젝션 발화가 컨텍스트로 되살아나 가드가
무력화된다. 그 회귀를 잡는 것이 아래 두 테스트다.

- `test_blocked_prompt_injection_is_not_replayed_into_later_model_history` (`tests/test_safety.py:162`)
- `test_blocked_addiction_prompt_is_excluded_from_model_context` (`tests/test_safety.py:185`)

위기 신호가 인젝션과 함께 올 때 안전 확인이 접수 흐름보다 우선한다는 규칙도 같은
스위트가 지킨다 (`test_crisis_signal_still_wins_when_injection_is_present`).

## commands

```bash
.venv/bin/python -m pytest tests/test_safety.py -q
```

## scenarios

## Related Scenarios

- [chat-session-auth](./chat-session-auth.md) — 같은 `api-chat` 진입점.
- [chat-intake-slot-flow](./chat-intake-slot-flow.md) — 위기 트랙 판정을 공유한다.
