---
id: launcher-auto-repair
type: full
priority: P0
domain: launcher
trigger: last_touch
delegate_to: none
entry_points:
  - cli-run
involved_globs:
  - run.py
  - requirements.txt
  - requirements.lock
  - .github/workflows/cross-platform.yml
last_change:
  date: 2026-07-27
  task: bootstrap
  ref: changelog/launcher.md#launcher-auto-repair-2026-07-27
---

# launcher-auto-repair: 비개발자 클론 후 바로 실행

> Change history: [launcher changelog](../../changelog/launcher.md#launcher-auto-repair)

이 레포의 제품 약속 하나가 "비개발자가 클론한 직후 런처만 실행하면 된다"이다.
`run.py` 는 표준 라이브러리만 써서 venv 와 `.env` 를 자동 복구한다. 외부 서비스를
필수 의존으로 만드는 설계는 이 약속을 깨므로, 스토어·인프라 선택의 1차 판단 기준이다.

`run.py` 의 검사 항목은 4개다: Python 버전 / 가상환경(.venv) / 의존성 패키지 / 설정 파일(.env).

## 로컬 명령의 한계 (중요)

아래 명령은 **현재 트리가 준비 상태인지**를 확인할 뿐, 진짜 신규 클론 자동복구를
재현하지 않는다. CI 의 "런처 자동 복구" 스텝은 venv 도 `.env` 도 없는 상태를 전제로
`assert any(not r.ok for r in before)` 를 먼저 걸기 때문에, `.venv` 가 이미 있는
개발 트리에서 그대로 돌리면 그 단정에서 실패한다.

신규 상태 자동복구의 진짜 증명은 `.github/workflows/cross-platform.yml` 의
windows/ubuntu/macos × py3.11/3.13 매트릭스다. 그래서 그 워크플로 파일을
`involved_globs` 에 포함했다 — 그 파일이 바뀌면 이 시나리오의 실제 가드가 바뀐다.

## commands

```bash
.venv/bin/python -m pytest tests/test_dependencies.py -q
.venv/bin/python -c "
import run
rs = run.check_environment()
for r in rs:
    print(f'{r.name}: {\"ok\" if r.ok else r.detail}')
raise SystemExit(0 if all(r.ok for r in rs) else 1)
"
```

## scenarios

## Related Scenarios

- [chat-korean-roundtrip](../chat/chat-korean-roundtrip.md) — 런처가 띄운 서버 위에서 도는 왕복.
