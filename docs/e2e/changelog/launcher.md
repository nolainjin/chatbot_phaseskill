# launcher Domain — E2E Changelog

> Reverse chronological by scenario. Each entry is task-scoped.
> Scenario bodies contain no history; all change history accumulates here.

## launcher-auto-repair

→ Scenario: [scenarios/launcher/launcher-auto-repair.md](../scenarios/launcher/launcher-auto-repair.md)
→ Entry points affected: [cli-run](../entry-points.md#cli-run)

### <a id="launcher-auto-repair-2026-07-27"></a> 2026-07-27 — task: bootstrap
- new scenario
- initial type `full`, priority `P0`, trigger `last_touch`, delegate_to `none`
- involved_globs: `run.py`, `requirements.txt`, `requirements.lock`, `.github/workflows/cross-platform.yml`
- reason: "비개발자가 클론 후 바로 실행"이 이 레포의 제품 약속이고, 외부 서비스를 필수 의존으로 만드는 설계가 이를 깨뜨린다. 스토어 선택의 1차 판단 기준이라 P0 로 등록한다.
- 기록해 둘 한계: 로컬 명령은 현재 트리의 준비 상태만 확인한다. 신규 클론 자동복구의 진짜 증명은 `.github/workflows/cross-platform.yml` 매트릭스이며, 그래서 그 워크플로 파일을 involved_globs 에 포함했다.
