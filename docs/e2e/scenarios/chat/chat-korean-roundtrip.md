---
id: chat-korean-roundtrip
type: full
priority: P0
domain: chat
trigger: last_touch
delegate_to: none
entry_points:
  - api-chat
  - ui-chat
involved_globs:
  - app/chat.py
  - app/main.py
  - app/storage.py
  - app/llm.py
  - app/prompting.py
  - static/index.html
  - static/app.js
last_change:
  date: 2026-07-27
  task: bootstrap
  ref: changelog/chat.md#chat-korean-roundtrip-2026-07-27
---

# chat-korean-roundtrip: 서버 기동 후 한글 1턴 왕복 + 저장 JSON 대조

> Change history: [chat changelog](../../changelog/chat.md#chat-korean-roundtrip)

이 레포에서 가장 비싸게 고쳐진 실패 유형을 정면으로 겨냥한다. 한국어 Windows 콘솔
기본 코드페이지가 cp949 라서, 깨지는 지점은 "임포트"가 아니라 **한글이 실제로 파이프와
파일을 왕복할 때**다. 그래서 부팅 확인에 그치지 않고 한글 메시지를 보내 저장된 대화
JSON 까지 읽어 대조한다.

`.github/workflows/cross-platform.yml` 의 "서버 기동 + 대화 1턴 (한글 왕복)" 스텝이
3-OS × 2-파이썬 매트릭스에서 같은 불변식을 지킨다. 이 시나리오는 그 CI 스텝의 로컬 대응물이다.

## commands

```bash
bash scripts/smoke_local.sh
```

## scenarios

## Related Scenarios

- [chat-session-auth](./chat-session-auth.md) — 같은 `api-chat` 진입점. 세션 토큰 경계.
- [chat-intake-slot-flow](./chat-intake-slot-flow.md) — 같은 왕복 경로 위의 접수 슬롯 상태.
