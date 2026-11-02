---
id: chat-intake-slot-flow
type: partial
priority: P0
domain: chat
trigger: last_touch
delegate_to: none
entry_points:
  - api-chat
  - api-config
involved_globs:
  - app/intake.py
  - app/chat.py
  - app/knowledge.py
  - knowledge/**
last_change:
  date: 2026-07-27
  task: bootstrap
  ref: changelog/chat.md#chat-intake-slot-flow-2026-07-27
---

# chat-intake-slot-flow: 접수 슬롯 채움과 10턴 캡

> Change history: [chat changelog](../../changelog/chat.md#chat-intake-slot-flow)

상담 접수의 본류다. 발화에서 슬롯(`track`, `chief_complaint`, `addiction_severity` 등)이
채워지고, 우선순위대로 다음 질문이 정해지며, `MAX_TURNS = 10` (`app/chat.py:15`)에
도달하면 접수 요약이 생성되고 이후 발화는 거절된다.

이 시나리오는 세션 상태 자체를 검사한다. 테스트 다수가 `chat._sessions[session_id].slots`
로 프로세스 메모리 dict 를 직접 들여다보므로, 세션 스토어를 교체하면 **이 시나리오가
가장 광범위하게 깨진다** — `tests/test_slot_e2e.py` 한 파일에만 직접 접근이 14곳 있다.
스토어 이행 계획의 회귀 방어선으로 쓴다.

`api-config` 를 진입점에 포함한 이유는 스키마 존재 여부가 `mode`(intake/coaching)를
가르고, 그 분기가 슬롯 흐름 전체를 좌우하기 때문이다.

## commands

```bash
.venv/bin/python -m pytest tests/test_slot_e2e.py tests/test_chat.py tests/test_intake.py -q
```

## scenarios

## Related Scenarios

- [chat-injection-guardrail](./chat-injection-guardrail.md) — 위기 트랙 판정을 공유한다.
- [chat-korean-roundtrip](./chat-korean-roundtrip.md) — 같은 왕복 경로.
