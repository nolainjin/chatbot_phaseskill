---
id: ratelimit-new-session-cap
type: partial
priority: P0
domain: ratelimit
trigger: last_touch
delegate_to: none
entry_points:
  - api-chat
involved_globs:
  - app/ratelimit.py
  - app/main.py
last_change:
  date: 2026-07-27
  task: bootstrap
  ref: changelog/ratelimit.md#ratelimit-new-session-cap-2026-07-27
---

# ratelimit-new-session-cap: IP당 신규 세션 상한과 일일 캡

> Change history: [ratelimit changelog](../../changelog/ratelimit.md#ratelimit-new-session-cap)

두 개의 서로 다른 카운터를 지킨다. 하나로 묶어 보면 안 된다.

- **IP당 슬라이딩 윈도우**: 같은 IP 에서 윈도우 안에 신규 세션 5개까지. 6번째는 `429`.
- **전역 일일 캡**: 날짜가 바뀌면 리셋되는 전체 요청 상한.

이미 아는 `session_id` 의 후속 발화는 카운트하지 않는다는 규칙도 함께 지킨다
(`test_existing_session_followups_are_not_counted`). 이게 깨지면 정상 대화가 중간에
429 로 끊긴다.

`app/ratelimit.py:66-68` 주석에 **단일 워커 전제가 이미 명시돼 있다** — `threading.Lock`
은 프로세스 안에서만 유효하고 `data/ratelimit.json` 은 read-modify-write 다. 워커를
늘리면 두 카운터가 워커 수만큼 느슨해진다. 그래서 이 시나리오는 세션 스토어 작업의
정확성 판정 기준이 된다: 두 상한이 워커 수와 무관하게 **정확히** 유지돼야 한다.

XFF 스푸핑에 대한 `client_ip` 홉 계산도 같은 스위트가 지킨다.

## commands

```bash
.venv/bin/python -m pytest tests/test_ratelimit.py -q
```

## scenarios

## Related Scenarios

- [chat-session-auth](../chat/chat-session-auth.md) — 신규 세션 판정을 공유한다.
