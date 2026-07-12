---
phase: 4
title: 퀵리플라이 칩 (첫 턴)
status: completed
depends_on: [3]
scope:
  - static/index.html
  - static/style.css
  - static/app.js
intervention_likely: false
intervention_reason: ""
executor: sonnet
load_bearing: "static/index.html의 data-send 문장 4개(스키마 신호어 매칭)가 core — 칩 스타일은 cosmetic"
e2e_refs: []
e2e_triggers: []
phase_context:
  baseline: "missing"
  adoption: "bootstrap"
  coverage: "standard"
  enforcement_during_run: "warn"
  materialize_at: "finalization"
---

# Phase 4: 퀵리플라이 칩 (첫 턴)

> **범위**: Frontend
> **난이도**: S
> **의존성**: Phase 3(intakeSchemaActive 공유 플래그·스테퍼 레이아웃)
> **영향 파일**: static/index.html, static/app.js

<!-- E2E 카탈로그(docs/e2e) 부재 — 카탈로그 갱신 전까지 E2E 비활성. Phase 5 로컬 브라우저 스모크가 대체. -->

## 배경

첫 턴에 불안/우울/수면/관계 칩 4종을 노출하고, 누르면 해당 문장을 대신 전송한다
(엔진 무수정 절충안 — 복수선택 폼 아님). 문장은 knowledge/_intake_schema.md의 track
신호어에 매칭되도록 고정해 fake/실모드 모두에서 track 슬롯이 채워지게 한다.

## 심볼 인벤토리

- `sendMessage` (칩 클릭 시 재사용할 전송 함수)
  - 근거: static/app.js:107
- `intake.extract_fake` (edge 검증에 사용 — 신호어 매칭 판정기)
  - 근거: app/intake.py:83
- track 신호어 사전 (정서: 불안·우울·잠 / 관계: 대인)
  - 근거: knowledge/_intake_schema.md:42
- `#chips` 칩 행 마크업(data-send), 칩 클릭 핸들러
  - [NEW]

## 설계

1. **마크업**: index.html에 `id="chips"` 칩 행을 `hidden` 기본값으로 추가 — 버튼
   4종, 각 버튼에 `data-send` 문장(신호어 1개씩 포함, 매칭 트랙 표기):

   | 칩 | data-send 문장 | 신호어 → 트랙 |
   |---|---|---|
   | 불안 | 요즘 마음이 자주 불안해요. | 불안 → 정서 |
   | 우울 | 우울한 기분이 계속돼요. | 우울 → 정서 |
   | 수면 | 밤에 잠을 잘 못 자요. | 잠 → 정서 |
   | 관계 | 대인관계 때문에 힘들어요. | 대인 → 관계 |

2. **노출 조건**: `intakeSchemaActive`(Phase 3 정의, 기본 false — config fetch 실패
   시 자동 fail-closed·undefined 접근 없음) && 사용자 발화 0회. knowledge-alt에서는
   플래그가 false라 미노출(스왑 회귀).
3. **수명주기**: 칩 클릭 → `sendMessage(data-send 문장)` 재사용 → 칩 행 제거. 직접
   타이핑 첫 전송 시에도 제거. limit_reached·오류 상태에서는 노출되지 않음.
4. 칩 라벨·문장은 GUI 소유 텍스트 — 봇 말투(_persona.md)와 무관.

## 체크리스트

- [x] index.html에 id="chips" 칩 행 추가 — 4종 data-send 문장, hidden 기본값
- [x] intakeSchemaActive && 사용자 발화 0회에만 노출
- [x] 첫 전송(칩/타이핑 불문) 후 칩 행이 제거되고 limit·오류 상태에서 칩이 노출되지 않는다
- [x] config fetch 실패 시 칩도 미노출 유지(fail-closed)되고 undefined config 접근 예외가 발생하지 않는다 — intakeSchemaActive 공유 플래그 게이트
- [x] 칩 문장 신호어 기계 검증(edge) 통과 — 4문장 전부 extract_fake가 track을 채움
- [x] .venv/bin/python -m pytest -q 통과

## 영향 범위

- static/ 3파일만 — 엔진 무수정(칩은 문장을 대신 전송할 뿐, /api/chat 계약 그대로).
- 칩 문장 변경 시 신호어 매칭이 깨질 수 있음 — edge 검증이 표류를 차단.
- 롤백: git checkout static/ 으로 복원.

## 검증

```bash
cd /Volumes/부부공용/worknote/lmwiki-chatbot
.venv/bin/python -m pytest -q
# edge: 칩 기본 미노출(스왑 회귀 정적 단언)
grep -Eq '<[a-z]+[^>]*id="chips"[^>]*hidden' static/index.html && echo "chips hidden ok"
# edge: 칩 문장-신호어 표류 차단 — data-send 4문장이 fake 추출기에서 track을 못 채우는 실패 경로 단언
.venv/bin/python - << 'PY'
import re
from app import intake
schema = intake.load_schema("knowledge")
assert schema is not None, "knowledge 스키마 로드 실패"
html = open("static/index.html", encoding="utf-8").read()
sentences = re.findall(r'data-send="([^"]+)"', html)
assert len(sentences) == 4, f"칩 4개 기대, {len(sentences)}개 발견"
for s in sentences:
    fills = intake.extract_fake(s, schema, {})
    assert "track" in fills, f"track 미채움: {s!r} -> {fills}"
print("chips edge ok")
PY
```

## 실행 결과

### 1회차 (2026-07-12 17:19 KST) — completed
**상태**: completed
**소요 시간**: 약 15분
**진행 모델**: Claude `sonnet`

#### 요약
index.html에 hidden 기본값의 `#chips` 칩 행(불안/우울/수면/관계 4종, data-send 문장 포함)을 추가하고,
app.js에 `userHasSpoken` 플래그와 `hideChips`/`maybeShowChips`를 도입해 `intakeSchemaActive && 발화 0회`
조건에서만 노출되도록 게이트했다. `sendMessage` 진입부에서 무조건 `userHasSpoken = true; hideChips();`를
실행해 칩 클릭·직접 타이핑 어느 경로로 첫 전송이 일어나도 칩 행이 사라지고, 이후 config fetch가 늦게
성공해도(`maybeShowChips`가 `!userHasSpoken`을 재확인) 다시 노출되지 않는다. config fetch 실패 시에는
`maybeShowChips` 자체가 호출되지 않아 HTML의 `hidden` 기본값 그대로 fail-closed 유지된다. style.css에
`.chips`/`.chip` cosmetic 스타일만 추가했다(엔진·계약 무수정).

#### 변경 파일
- `static/index.html` (modified, +7/-0 lines)
- `static/app.js` (modified, +24/-0 lines)
- `static/style.css` (modified, +28/-0 lines)

#### 검증 결과
- [x] pytest 전체: `.venv/bin/python -m pytest -q` -> pass (81 passed)
- [x] 칩 hidden 기본값 정적 단언: `grep -Eq '<[a-z]+[^>]*id="chips"[^>]*hidden' static/index.html` -> pass ("chips hidden ok")
- [x] 칩 문장-신호어 표류 차단(edge): 4문장 전부 `intake.extract_fake`가 track을 채움 -> pass ("chips edge ok")
- [x] app.js 문법 스모크: `node --check static/app.js` -> pass (오류 출력 없음)

#### 추가 발견사항
없음

#### 질문 / 결정 사항
없음
