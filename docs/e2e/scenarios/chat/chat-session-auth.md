---
id: chat-session-auth
type: partial
priority: P0
domain: chat
trigger: last_touch
delegate_to: none
entry_points:
  - api-chat
involved_globs:
  - app/main.py
  - app/chat.py
  - app/storage.py
last_change:
  date: 2026-07-27
  task: bootstrap
  ref: changelog/chat.md#chat-session-auth-2026-07-27
---

# chat-session-auth: 세션 토큰 인증과 401 경계

> Change history: [chat changelog](../../changelog/chat.md#chat-session-auth)

`app/main.py:43-48` 의 세 갈래 분기를 지킨다.

- 이미 아는 세션인데 토큰이 안 맞으면 `401 "세션 인증이 필요합니다."`
- 모르는 세션인데 디스크에 대화 JSON 이 있으면 `401 "만료된 세션입니다."`
- 그 외에는 통과하고 신규 세션이면 응답에 `session_token` 을 실어 보낸다

세션 상태가 프로세스 메모리(`app/chat.py:57` `_sessions`)에 있는 한 이 분기는 워커 수에
종속적이다. 세션 스토어를 분리하는 작업이 이 시나리오를 가장 먼저 깨뜨릴 수 있으므로
P0 로 둔다. `owns_session` 이 `secrets.compare_digest` 를 쓰는 것도 이 경계의 일부다.

`app/storage.py` 의 `conversation_exists()` 는 **오늘 날짜 디렉터리만** 보므로, 위 두
번째 분기는 이미 날짜 스코프가 걸려 있다. 스토어 교체 시 이 성질이 바뀌면 여기서 잡힌다.

## commands

```bash
.venv/bin/python -m pytest tests/test_security.py -q
```

## scenarios

## Related Scenarios

- [chat-korean-roundtrip](./chat-korean-roundtrip.md) — 같은 `api-chat` 진입점.
- [ratelimit-new-session-cap](../ratelimit/ratelimit-new-session-cap.md) — 신규 세션 판정을 공유한다.
