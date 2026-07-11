---
phase: 5
title: 채팅 웹 UI
status: completed
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

- [x] static/index.html: 채팅 화면(메시지 목록·입력창·전송 버튼)
- [x] static/app.js: /api/chat 호출, session_id 생성·sessionStorage 유지, 턴 카운터 표시
- [x] 오류·429(rate limit)·턴 초과 상태를 사용자에게 표시
- [x] 대화 내용이 저장됩니다 고지 문구 표시
- [x] tests/test_ui_serving.py: / 접근 시 index.html 200 서빙 확인

## 영향 범위

정적 파일만 추가 — 백엔드 영향 없음. Phase 6 스모크가 이 UI 경로(/)의 서빙을 확인한다. 롤백 = 파일 삭제.

## 검증

```bash
.venv/bin/python -m pytest tests/test_ui_serving.py -q
```

## 실행 결과

### 1회차 (2026-07-11 13:54 KST) — completed

**상태**: completed
**소요 시간**: 약 15분
**진행 모델**: Claude sonnet

#### 요약

바닐라 HTML/CSS/JS로 채팅 화면 1장을 구성했다. `static/index.html`은 메시지 목록·입력창·전송 버튼·저장 고지 문구를 담고, `static/app.js`가 `session_id`를 `sessionStorage`(없으면 `crypto.randomUUID()`)로 관리하며 `POST /api/chat`을 호출해 `{reply, turn, limit_reached}` 계약대로 응답을 반영한다. 429(rate limit), 기타 HTTP 오류, `limit_reached`(입력창 비활성화), 네트워크 오류 네 갈래를 각각 다른 안내 문구로 표시한다. 접근성은 `<label>` + `input[type=text]`로 처리해 별도 JS 없이 Enter 키 전송이 네이티브로 동작한다(ponytail: textarea+keydown 핸들러 대신 input 기본 submit 활용).

#### 변경 파일

- `static/index.html` (신규, +35)
- `static/style.css` (신규, +105)
- `static/app.js` (신규, +96)
- `tests/test_ui_serving.py` (신규, +18)

#### 검증 결과

- `.venv/bin/python -m pytest tests/test_ui_serving.py -q` → 2 passed
- `.venv/bin/python -m pytest -q` (전체) → 19 passed (Phase 1/2 기존 테스트 포함, 회귀 없음)
- `app/main.py` 읽어서 확인: static 디렉터리 존재 시 `/`에 `StaticFiles(html=True)`로 마운트, `/api/chat`은 그보다 먼저 등록된 명시적 라우트라 경로 충돌 없음. 코드 미수정.

#### 추가 발견사항

없음. Phase 4(app/ratelimit.py, app/main.py)와 Phase 3(app/storage.py 등) 파일에는 손대지 않았다.

#### 질문 / 결정 사항

없음.

#### Commit
- `792b84b` feat(chat-ui): Phase 5 — 바닐라 채팅 웹 UI + /api/chat 연동 (review pass, simplify 429 분기 중복 제거, 검증 재실행 pass)
