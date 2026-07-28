---
project: lmwiki-chatbot
catalog_version: 1
last_refreshed: 2026-07-27
total_scenarios: 6
---

# E2E Catalog — lmwiki-chatbot

> Updated by phase-e2e-init during bootstrap / refresh. Mutated by phase-init per task.
> phase-run reads this catalog only for per-phase firing of e2e_refs scenarios.
> Detailed schema: `$PHASE_SKILLS_DIR/phase-run/docs/checklist-schema.md` §7

## Scenarios

| id | type | priority | domain | involved_globs | entry_points | file |
|----|------|----------|--------|----------------|--------------|------|
| chat-korean-roundtrip | full | P0 | chat | app/chat.py, app/main.py, app/storage.py, app/llm.py, app/prompting.py, static/index.html, static/app.js | api-chat, ui-chat | [scenarios/chat/chat-korean-roundtrip.md](scenarios/chat/chat-korean-roundtrip.md) |
| chat-session-auth | partial | P0 | chat | app/main.py, app/chat.py, app/storage.py | api-chat | [scenarios/chat/chat-session-auth.md](scenarios/chat/chat-session-auth.md) |
| chat-injection-guardrail | partial | P0 | chat | app/safety.py, app/chat.py, app/addiction.py | api-chat | [scenarios/chat/chat-injection-guardrail.md](scenarios/chat/chat-injection-guardrail.md) |
| chat-intake-slot-flow | partial | P0 | chat | app/intake.py, app/chat.py, app/knowledge.py, knowledge/** | api-chat, api-config | [scenarios/chat/chat-intake-slot-flow.md](scenarios/chat/chat-intake-slot-flow.md) |
| ratelimit-new-session-cap | partial | P0 | ratelimit | app/ratelimit.py, app/main.py | api-chat | [scenarios/ratelimit/ratelimit-new-session-cap.md](scenarios/ratelimit/ratelimit-new-session-cap.md) |
| launcher-auto-repair | full | P0 | launcher | run.py, requirements.txt, requirements.lock, .github/workflows/cross-platform.yml | cli-run | [scenarios/launcher/launcher-auto-repair.md](scenarios/launcher/launcher-auto-repair.md) |

## Domain Coverage

- chat: P0 4
- ratelimit: P0 1
- launcher: P0 1
- admin: unwritten — P1 후보 `admin-stats-token-boundary` 를 `scenarios/admin/_pending.md` 에 기록. phase-e2e-init refresh 필요
- batch: unwritten — P1 후보 `batch-sqlite-load` 를 `scenarios/batch/_pending.md` 에 기록. phase-e2e-init refresh 필요
- eval: unwritten — P2. 제품 사용자 플로우가 아니라 품질 평가 하니스라 우선순위 최하. `scenarios/eval/_pending.md` 참조

## Unassigned Entry Points

아래 진입점은 검출됐으나 아직 어떤 시나리오에도 매핑되지 않았다. 대응 도메인의
`_pending.md` 에 후보 시나리오와 검증 명령을 적어 두었다.

- [api-stats](entry-points.md#api-stats) → admin
- [ui-stats](entry-points.md#ui-stats) → admin
- [cli-load-to-sqlite](entry-points.md#cli-load-to-sqlite) → batch
- [cli-generate-demo-population](entry-points.md#cli-generate-demo-population) → batch
- [cli-collect-usage](entry-points.md#cli-collect-usage) → batch
- [cli-tone-eval](entry-points.md#cli-tone-eval) → eval
- [cli-persona-eval](entry-points.md#cli-persona-eval) → eval
- [cli-math-student-eval](entry-points.md#cli-math-student-eval) → eval
- [cli-validate-knowledge-pack](entry-points.md#cli-validate-knowledge-pack) → eval
- [cli-red-team-prompt-injection](entry-points.md#cli-red-team-prompt-injection) → eval
- [cli-build-keynote-deck](entry-points.md#cli-build-keynote-deck) → 도메인 미배정. 슬라이드 생성 도구라 제품 플로우가 아니다
- [cli-check-dependencies](entry-points.md#cli-check-dependencies) → launcher 후보. `tests/test_dependencies.py` 가 이미 `launcher-auto-repair` 명령에 포함돼 있어 별도 시나리오는 두지 않았다
