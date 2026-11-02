# eval Domain — Unwritten Scenarios

> Placeholder for domains where phase-e2e-init detected entry points but scenarios have not been written yet.
> Recommended follow-up: phase-e2e-init refresh or phase-init can add scenarios later.

## Detected Entry Points

- [cli-tone-eval](../../entry-points.md#cli-tone-eval) — `scripts/tone_eval.py`
- [cli-persona-eval](../../entry-points.md#cli-persona-eval) — `scripts/persona_eval.py`
- [cli-math-student-eval](../../entry-points.md#cli-math-student-eval) — `scripts/math_student_eval.py`
- [cli-validate-knowledge-pack](../../entry-points.md#cli-validate-knowledge-pack) — `scripts/validate_knowledge_pack.py`
- [cli-red-team-prompt-injection](../../entry-points.md#cli-red-team-prompt-injection) — `scripts/red_team_prompt_injection.py`

## Notes

2026-07-27 bootstrap 에서 P2 로 판정해 미룸.

이 도메인은 제품 사용자 플로우가 아니라 **품질 평가 하니스**다. 사용자가 겪는 경로가
아니므로 E2E 시나리오로서의 우선순위가 가장 낮다. 다만 세 스크립트
(`tone_eval.py:118,134`, `red_team_prompt_injection.py:46`,
`generate_demo_population.py:265`)가 `chat._sessions.clear()` 로 세션 dict 에 직접
접근하므로, 세션 스토어 교체 시 **함께 수정해야 하는 대상**이다. 시나리오가 없다고
이행 범위에서 빠뜨리면 안 된다.

기존 테스트는 있다: `tests/test_tone_profile.py`, `tests/test_persona_eval.py`,
`tests/test_math_student_eval.py`, `tests/test_knowledge_pack_validator.py`.
