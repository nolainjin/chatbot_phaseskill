# batch Domain — Unwritten Scenarios

> Placeholder for domains where phase-e2e-init detected entry points but scenarios have not been written yet.
> Recommended follow-up: phase-e2e-init refresh or phase-init can add scenarios later.

## Detected Entry Points

- [cli-load-to-sqlite](../../entry-points.md#cli-load-to-sqlite) — `scripts/load_to_sqlite.py`
- [cli-generate-demo-population](../../entry-points.md#cli-generate-demo-population) — `scripts/generate_demo_population.py`
- [cli-collect-usage](../../entry-points.md#cli-collect-usage) — `receipts/collect_usage.py`

## Notes

2026-07-27 bootstrap 에서 P1 로 판정해 미룸. 사용자 선택은 "P0 6건만 지금 작성".

후보 시나리오는 `batch-sqlite-load` (P1, partial). 검증 명령 후보 (실존 확인 완료):

```bash
.venv/bin/python -m pytest tests/test_storage_batch.py -q
```

**세션 스토어 작업과의 연결**: `tests/test_storage_batch.py:99`
`test_load_to_sqlite_keeps_same_session_id_on_different_dates` 가 대화 JSON 의 날짜
파티션 구조를 직접 가드한다. `app/storage.py` 의 `append_turn` 은
`data/conversations/<YYYY-MM-DD>/<session_id>.json` 에 쓰고 `seq` 는 날짜 파일마다
0부터 다시 시작하며, `scripts/load_to_sqlite.py` 의 테이블 기본키가
`conversations(date, session_id)` 복합키다. 대화 JSON 포맷이나 적재 경로를 바꾸는
설계는 이 도메인 시나리오를 먼저 작성한 뒤 진행하는 편이 안전하다.

involved_globs 후보: `scripts/load_to_sqlite.py`, `scripts/generate_demo_population.py`,
`app/storage.py`.
