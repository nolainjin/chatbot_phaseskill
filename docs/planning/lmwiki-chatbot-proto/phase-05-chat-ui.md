---
phase: 5
title: 채팅 웹 UI
status: pending
depends_on: [2]
scope:
  - static/index.html
  - static/app.js
  - static/style.css
  - tests/test_ui_serving.py
intervention_likely: false
intervention_reason: ""
executor: sonnet
load_bearing: ""
e2e_refs: []
e2e_triggers: []
phase_context:
  baseline: "missing"
  adoption: "bootstrap"
  coverage: "standard"
  enforcement_during_run: "warn"
  materialize_at: "finalization"
---

# Phase 5: 채팅 웹 UI

> **범위**: Frontend
> **난이도**: S
> **의존성**: Phase 2
> **영향 파일**: `static/index.html` (신규), `static/app.js` (신규)

## 배경

1차 버전은 텍스트 채팅 중심(origin §2). 바닐라 HTML/JS 정적 페이지 1장이면 충분하다(D03). static/ 마운트는 Phase 2에서 이미 걸려 있어 이 phase는 정적 파일만 추가한다 — Phase 3/4와 파일이 겹치지 않아 병렬 실행 가능. 대화 내역이 저장된다는 고지 문구는 개인정보 리스크(FP8)를 닫는 항목이라 빼면 안 된다.

## 심볼 인벤토리

- `static/app.js sendMessage`
  - [NEW]

## 설계

```
index.html: 메시지 목록 영역 + 입력창 + 전송 버튼 + 고지 문구 한 줄
app.js:
    session_id = sessionStorage에 없으면 crypto.randomUUID()로 생성
    전송 → fetch POST /api/chat → 응답을 목록에 추가, 턴 카운터 갱신 (예: 3/10)
    HTTP 429 → "이용 한도" 안내 표시
    limit_reached → 입력창 비활성화 + 안내
    네트워크 오류 → 재시도 안내
```

프레임워크·빌드 도구 없음. 모바일 뷰포트 meta와 기본 접근성(라벨, 키보드 전송)은 지킨다.

## 체크리스트

- [ ] static/index.html: 채팅 화면(메시지 목록·입력창·전송 버튼)
- [ ] static/app.js: /api/chat 호출, session_id 생성·sessionStorage 유지, 턴 카운터 표시
- [ ] 오류·429(rate limit)·턴 초과 상태를 사용자에게 표시
- [ ] 대화 내용이 저장됩니다 고지 문구 표시
- [ ] tests/test_ui_serving.py: / 접근 시 index.html 200 서빙 확인

## 영향 범위

정적 파일만 추가 — 백엔드 영향 없음. Phase 6 스모크가 이 UI 경로(/)의 서빙을 확인한다. 롤백 = 파일 삭제.

## 검증

```bash
.venv/bin/python -m pytest tests/test_ui_serving.py -q
```
