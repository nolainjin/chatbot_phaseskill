---
project: lmwiki-chatbot
last_scanned: 2026-07-27
project_type: mixed
---

# Entry Points — lmwiki-chatbot

> Generated automatically by phase-e2e-init entry point matchers. Humans only verify and supplement.
> Used as the delta comparison baseline during refresh.
> Matchers by project_type: `$PHASE_SKILLS_DIR/phase-e2e-init/docs/entry-point-patterns.md`

`project_type: mixed` — `requirements.txt` 에 `fastapi` 가 있어 `fastapi` 매처가 걸리고,
`run.py` 와 `scripts/` 의 argparse 사용으로 `cli-python` 매처가 함께 걸린다.

## Entry Points

### <a id="api-chat"></a> api-chat
- type: api
- pattern: fastapi-route
- file: app/main.py
- method: POST
- path: /api/chat
- discovered: 2026-07-27
- referenced_by_scenarios: [chat-korean-roundtrip, chat-session-auth, chat-injection-guardrail, chat-intake-slot-flow, ratelimit-new-session-cap]

### <a id="api-config"></a> api-config
- type: api
- pattern: fastapi-route
- file: app/main.py
- method: GET
- path: /api/config
- discovered: 2026-07-27
- referenced_by_scenarios: [chat-intake-slot-flow]

### <a id="api-stats"></a> api-stats
- type: api
- pattern: fastapi-route
- file: app/main.py
- method: GET
- path: /api/stats
- discovered: 2026-07-27
- referenced_by_scenarios: []

### <a id="ui-chat"></a> ui-chat
- type: page
- pattern: fastapi-staticfiles-mount
- file: static/index.html
- discovered: 2026-07-27
- referenced_by_scenarios: [chat-korean-roundtrip]

`app/main.py:97` 이 `app.mount("/", StaticFiles(directory="static", html=True))` 로
마운트하므로 `/` 요청이 `static/index.html` 을 서빙한다. 마운트는 디렉터리가 존재할
때만 조건부로 실행된다.

### <a id="ui-stats"></a> ui-stats
- type: page
- pattern: fastapi-staticfiles-mount
- file: static/stats.html
- discovered: 2026-07-27
- referenced_by_scenarios: []

### <a id="cli-run"></a> cli-run
- type: cli
- pattern: cli-argparse
- file: run.py
- discovered: 2026-07-27
- referenced_by_scenarios: [launcher-auto-repair]

비개발자용 런처. 표준 라이브러리만 사용하며 venv 와 `.env` 를 자동 복구한다.

### <a id="cli-load-to-sqlite"></a> cli-load-to-sqlite
- type: cli
- pattern: cli-argparse
- file: scripts/load_to_sqlite.py
- discovered: 2026-07-27
- referenced_by_scenarios: []

### <a id="cli-generate-demo-population"></a> cli-generate-demo-population
- type: cli
- pattern: cli-argparse
- file: scripts/generate_demo_population.py
- discovered: 2026-07-27
- referenced_by_scenarios: []

### <a id="cli-collect-usage"></a> cli-collect-usage
- type: cli
- pattern: cli-argparse
- file: receipts/collect_usage.py
- discovered: 2026-07-27
- referenced_by_scenarios: []

### <a id="cli-tone-eval"></a> cli-tone-eval
- type: cli
- pattern: cli-argparse
- file: scripts/tone_eval.py
- discovered: 2026-07-27
- referenced_by_scenarios: []

### <a id="cli-persona-eval"></a> cli-persona-eval
- type: cli
- pattern: cli-argparse
- file: scripts/persona_eval.py
- discovered: 2026-07-27
- referenced_by_scenarios: []

### <a id="cli-math-student-eval"></a> cli-math-student-eval
- type: cli
- pattern: cli-argparse
- file: scripts/math_student_eval.py
- discovered: 2026-07-27
- referenced_by_scenarios: []

### <a id="cli-validate-knowledge-pack"></a> cli-validate-knowledge-pack
- type: cli
- pattern: cli-argparse
- file: scripts/validate_knowledge_pack.py
- discovered: 2026-07-27
- referenced_by_scenarios: []

### <a id="cli-red-team-prompt-injection"></a> cli-red-team-prompt-injection
- type: cli
- pattern: cli-main-guard
- file: scripts/red_team_prompt_injection.py
- discovered: 2026-07-27
- referenced_by_scenarios: []

### <a id="cli-build-keynote-deck"></a> cli-build-keynote-deck
- type: cli
- pattern: cli-main-guard
- file: scripts/build_keynote_deck.py
- discovered: 2026-07-27
- referenced_by_scenarios: []

### <a id="cli-check-dependencies"></a> cli-check-dependencies
- type: cli
- pattern: cli-main-guard
- file: scripts/check_dependencies.py
- discovered: 2026-07-27
- referenced_by_scenarios: []

## Undetected Regions

`scripts/gui-smoke/` 는 매처가 진입점으로 잡지 않았다. 2026-07-27 bootstrap 세션에서
사용자 인터뷰로 확인하지 않은 영역이므로, refresh 때 진입점 여부를 판정 대상으로 남긴다.

`scripts/smoke_local.sh` 는 `.py` 매처 대상이 아니라 자동 검출되지 않았으나,
`chat-korean-roundtrip` 시나리오의 실행 수단으로 쓰인다. 진입점이 아니라 검증 도구로 분류한다.
