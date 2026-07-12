---
phase: 1
title: 스키마 프로브 GET /api/config
status: completed
depends_on: []
scope:
  - app/main.py
  - tests/test_config.py
intervention_likely: false
intervention_reason: ""
executor: haiku
load_bearing: "app/main.py의 GET /api/config 라우트 추가가 core — static 마운트보다 위에 선언해야 경로 우선순위가 성립"
e2e_refs: []
e2e_triggers: []
phase_context:
  baseline: "missing"
  adoption: "bootstrap"
  coverage: "standard"
  enforcement_during_run: "warn"
  materialize_at: "finalization"
---

# Phase 1: 스키마 프로브 GET /api/config

> **범위**: Backend
> **난이도**: S
> **의존성**: 없음
> **영향 파일**: app/main.py, tests/test_config.py [NEW]

<!-- E2E 카탈로그(docs/e2e) 부재 — 카탈로그 갱신 전까지 E2E 비활성. Phase 5 로컬 브라우저 스모크가 대체. -->

## 배경

첫 턴 칩과 스테퍼는 페이지 로드 시점에 노출 여부를 결정해야 하는데, 스키마 유무는
지금 첫 `/api/chat` 응답의 intake 키로만 알 수 있다. knowledge-alt(스키마 없는
지식셋) 미노출 회귀 제약과 첫 턴 칩 노출을 동시에 지키려면 로드 시점 읽기 전용
프로브가 필요하다. 사용자 결정(2026-07-12): GET /api/config 추가 승인 — 엔진 수정은
이 엔드포인트 하나로 한정.

## 심볼 인벤토리

- `app.main.app` (FastAPI 인스턴스)
  - 근거: app/main.py:14
- `app.main.post_chat`
  - 근거: app/main.py:19
- `app.mount("/", StaticFiles(...))` (static 마운트 — 이보다 위에 선언)
  - 근거: app/main.py:46
- `intake.load_schema` (부재·오류 시 None 폴백)
  - 근거: app/intake.py:191
- `Settings.from_env` (KNOWLEDGE_DIR env 읽기)
  - 근거: app/config.py:16
- `get_config`
  - [NEW]
- `tests/test_config.py`
  - [NEW]

## 설계

app/main.py에 읽기 전용 엔드포인트 하나를 추가한다 (의사코드):

```
GET /api/config:
    settings = Settings.from_env()          # 매 요청 env 읽기 — post_chat과 동일 패턴
    return {"intake_schema": intake.load_schema(settings.knowledge_dir) is not None}
```

- 선언 위치: 파일 하단 `app.mount("/", ...)`(main.py:46)보다 위 — FastAPI 라우트가
  catch-all static 마운트보다 먼저 등록되도록.
- rate limit 미적용: 세션을 만들지 않는 읽기 전용 경로라 RateLimiter 경유 불필요.
- `/api/chat` 계약 {reply, turn, limit_reached}(+additive intake)는 무변경.

tests/test_config.py는 기존 TestClient 선례(tests/test_ui_serving.py)를 따라
monkeypatch로 KNOWLEDGE_DIR을 knowledge / knowledge-alt로 전환하며 양경로를 단언한다.

## 체크리스트

- [x] app/main.py에 GET /api/config 추가 — {"intake_schema": bool} 반환, static 마운트보다 위에 선언
- [x] tests/test_config.py 신규 — knowledge에서 intake_schema true, knowledge-alt에서 false 단언
- [x] /api/chat 계약 무변경 — 기존 pytest 전체 통과

## 영향 범위

- app/main.py 단일 파일 additive 변경 — 기존 라우트·마운트 무수정.
- 롤백: 엔드포인트 함수 + 테스트 파일 삭제로 완전 복원.
- 후속 Phase 3(스테퍼)·Phase 4(칩)가 이 엔드포인트를 게이트로 소비.

## 검증

```bash
cd /Volumes/부부공용/worknote/lmwiki-chatbot
.venv/bin/python -m pytest tests/test_config.py -q
.venv/bin/python -m pytest -q
# edge: 스키마 없는 지식셋(knowledge-alt)에서 intake_schema=false — 스왑 회귀 실패 경로 단언
KNOWLEDGE_DIR=knowledge-alt .venv/bin/python -c "from fastapi.testclient import TestClient; from app.main import app; r = TestClient(app).get('/api/config'); assert r.status_code == 200 and r.json() == {'intake_schema': False}, r.text; print('edge ok')"
```

## 실행 결과

### 1회차 (2026-07-12 16:45 KST) — completed
**상태**: completed
**소요 시간**: 약 5분
**진행 모델**: Claude Haiku 4.5

#### 요약
GET /api/config 엔드포인트를 app/main.py에 추가했다. knowledge 디렉토리에서는 intake_schema=true, knowledge-alt에서는 false를 반환한다. tests/test_config.py를 신규 작성하여 양 경로를 단언했고, 전체 pytest 81개가 통과했다.

#### 변경 파일
- `app/main.py` (modified, +9/-1)
- `tests/test_config.py` (new, +28/-0)

#### 검증 결과
- [x] tests/test_config.py: `pytest tests/test_config.py -q` → 2 passed
- [x] 전체 pytest: `pytest -q` → 81 passed
- [x] Edge case (knowledge-alt): `KNOWLEDGE_DIR=knowledge-alt python -c ...` → pass

#### 추가 발견사항
없음

#### 질문 / 결정 사항
없음
