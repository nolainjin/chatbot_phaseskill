# admin Domain — Unwritten Scenarios

> Placeholder for domains where phase-e2e-init detected entry points but scenarios have not been written yet.
> Recommended follow-up: phase-e2e-init refresh or phase-init can add scenarios later.

## Detected Entry Points

- [api-stats](../../entry-points.md#api-stats) — `app/main.py:75` `GET /api/stats`
- [ui-stats](../../entry-points.md#ui-stats) — `static/stats.html`

## Notes

2026-07-27 bootstrap 에서 P1 로 판정해 미룸. 사용자 선택은 "P0 6건만 지금 작성".

작성할 때의 후보 시나리오는 `admin-stats-token-boundary` (P1, partial) 하나다.
지킬 불변식은 세 갈래다.

- `settings.stats_api_token` 미구성이면 `503`
- 토큰 불일치·누락이면 `401` (`secrets.compare_digest` 사용)
- 일치하면 대시보드 JSON 반환

검증 명령 후보 (실존 확인 완료):

```bash
.venv/bin/python -m pytest tests/test_stats.py tests/test_ui_serving.py -q
```

관련 테스트: `test_api_stats_rejects_anonymous_requests`, `test_api_stats_returns_json`,
`test_csv_cell_neutralizes_formula_markers`,
`test_stats_serves_csv_formula_neutralizer_before_dashboard_script`.

involved_globs 후보: `app/stats.py`, `static/stats.html`, `static/stats.js`, `static/csv.js`.
