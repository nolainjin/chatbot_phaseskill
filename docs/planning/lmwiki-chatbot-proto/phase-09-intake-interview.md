---
phase: 9
title: 접수 면담 모드 전환
status: completed
depends_on: [7]
scope:
  - app/chat.py
  - app/knowledge.py
  - app/llm.py
  - app/storage.py
  - knowledge/_persona.md
  - static/index.html
  - static/app.js
  - tests/test_intake.py
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

# Phase 9: 접수 면담 모드 전환

> **범위**: Both
> **난이도**: M
> **의존성**: Phase 7 — Phase 8이 아닌 7에 의존하는 이유: Phase 8 잔여 항목(실배포 검증)이 이 phase 산출물을 검증 대상으로 삼으므로, 8에 의존하면 교착된다. 실행 순서상 Phase 9 → Phase 8 잔여.
> **영향 파일**: `app/chat.py`, `app/knowledge.py`, `knowledge/_persona.md` (신규), `static/`, `tests/test_intake.py` (신규)

## 배경

checklist.md cross-phase 메모(2026-07-11): 첫 도메인 = **상담 초기 면담 챗봇**. 현재 봇의 정체성은 `chat._SYSTEM_PREAMBLE` 한 줄("지식 문서를 근거로 답하라")인 수동 Q&A다. Phase 8 잔여 항목(실배포 검증)의 "실제 대화" 확인이 접수 면담 형식이어야 하므로, 배포 전에 면담을 주도하는 봇으로 전환한다. 지식 6종(접수-면접-질문지-구성, 위기-상황-스크리닝, 라포-형성-기법 등)은 이미 접수면담 주제라 면담 가이드로 그대로 쓴다.

사용자 결정(2026-07-11, D08·D09): 페르소나는 `knowledge/_persona.md`에 두고 언더스코어 접두 파일은 지식 검색에서 제외, 부재 시 기존 프리앰블로 폴백(Phase 6 지식/로직 분리 invariant 보존). 면담 종료 시 접수 요약 구조화 저장 포함.

## 심볼 인벤토리

- `app/chat.py` — `_SYSTEM_PREAMBLE`, `handle_message()` (시스템 프롬프트 조립·10턴 캡)
- `app/knowledge.py` — `load_documents()` (현재 `*.md` 전부 로드 — `_` 제외 필요)
- `app/llm.py` — `ask()` (요약 생성에 재사용, `MODEL=fake` 스텁 경로 유지)
- `app/storage.py` — `append_turn()` (`{seq, role, text}` 스키마 — 요약은 새 role 값으로 추가)

## 설계

```
knowledge.load_documents:
    파일명이 "_"로 시작하는 .md는 Document 목록에서 제외   # 페르소나·메타 파일 예약

chat.handle_message:
    persona = knowledge_dir/_persona.md 있으면 그 내용, 없으면 _SYSTEM_PREAMBLE   # 스왑 폴백
    system = persona + "[진행: {turns+1}/{MAX_TURNS}턴]" + 검색된 지식 문서
    ... 기존 흐름(검색→llm.ask→저장→히스토리) 유지 ...
    if 이번 턴으로 MAX_TURNS 도달:
        summary = llm.ask(접수 요약 지시 + 전체 히스토리)   # fake 모드: "[fake] ..." 스텁
        storage.append_turn(session_id, "intake_summary", summary)
        # 요약 실패가 본 대화 저장을 깨지 않도록 별도 try — 실패 시 대화만 남는다

knowledge/_persona.md (신규):
    면담 주도 정책 — 인사 → 방문 이유 → 필요한 것 질문 → 위기 스크리닝(위기-상황-스크리닝.md 근거)
    → 10턴 안에 접수 요약으로 마무리. 요약 형식(방문 이유·주 호소·위기 신호·다음 단계) 명시.

static/: 첫 화면 인사말을 접수 면담용으로 교체
```

요약은 별도 스키마가 아닌 기존 turn 레코드(`role="intake_summary"`, `text`=구조화 JSON 문자열)로 저장 — SQLite 배치(`load_to_sqlite.py`)는 role 컬럼에 새 값이 들어올 뿐 무수정. API 계약 `{reply, turn, limit_reached}` 무변경.

<!-- ponytail: 요약 전용 테이블/사이드카 파일은 요약 조회 요구가 생길 때 -->

## 체크리스트

- [x] 페르소나 주입: `knowledge.load_documents`가 `_` 접두 `.md`를 검색에서 제외하고, `chat.handle_message`가 `_persona.md` 존재 시 시스템 프롬프트 선두에 결합·부재 시 기존 프리앰블 폴백 (tests/test_intake.py)
- [x] `knowledge/_persona.md` 작성 — 인사→방문 이유→필요한 것 질문→위기 스크리닝→10턴 내 접수 요약 마무리 면담 정책, 기존 지식 6종과 용어 정합
- [x] 턴 컨텍스트 주입: 시스템 프롬프트에 현재/최대 턴을 표기해 마무리를 유도 (tests/test_intake.py: 프롬프트 조립 검증)
- [x] 접수 요약 구조화 저장: MAX_TURNS 도달 시 요약 1회 생성 → `role="intake_summary"` 턴으로 저장, 요약 실패 시에도 본 대화 저장 유지, fake 모드 스텁 지원 (tests/test_intake.py)
- [x] `static/` 첫 인사말 접수 면담용 교체
- [x] 회귀 + 스왑 invariant: 전체 pytest 통과, knowledge-alt(`_persona.md` 없음) 스왑 시 Q&A 폴백 동작 확인 (tests/test_intake.py 또는 tests/test_swap_e2e.py 확장)

## 실패 경로

- `_persona.md`가 지식 검색에 섞여 문서로 인용됨 → `_` 제외 테스트 (test: tests/test_intake.py)
- 스왑 디렉토리에 `_persona.md` 부재 시 오류 → 폴백 테스트, Phase 6 invariant 회귀 방지 (test: tests/test_intake.py)
- 요약 생성 실패(LLM 오류)가 본 대화 저장까지 유실시킴 → 요약을 별도 try로 격리 (test: tests/test_intake.py)
- 실모델이 실제로 면담을 주도하는지(면담 품질)는 fake 모드로 검증 불가 → Phase 8 실배포 검증(deploy/checklist.md 수행) 시 사용자와 확인 (needs_user)

## 영향 범위

앱 코드 수정(chat/knowledge/storage 경유 로직 + 정적 UI 문구). 기존 API 계약·rate limit·SQLite 배치 무변경. Phase 8 잔여 항목(실배포)은 이 phase 완료 후 수행 권장 — 실배포 검증의 "실제 대화"가 접수 면담 형식이 된다.

## 검증

```bash
.venv/bin/python -m pytest -q
bash scripts/smoke_local.sh
```

## 실행 결과

### 1회차 (2026-07-11 21:08 KST) — completed

**상태**: completed
**소요 시간**: 약 25분
**진행 모델**: Claude `sonnet`

#### 요약
`_persona.md` 예약 파일 규칙(언더스코어 접두 제외)을 knowledge 로더에 추가하고, chat.handle_message가 페르소나 존재 시 결합·부재 시 기존 프리앰블로 폴백하도록 전환했다. 턴 진행 표기와 MAX_TURNS 도달 시 접수 요약 저장(실패 격리 포함)을 추가하고 static 첫 화면을 접수 면담용 인사말로 교체했다.

#### 변경 파일
- `app/knowledge.py` (modified, +7/-1 lines) — `load_documents`가 `_` 접두 `.md` 제외
- `app/chat.py` (modified, +36/-3 lines) — 페르소나 로드·폴백, 턴 진행 표기, 접수 요약 생성·저장(try 격리)
- `knowledge/_persona.md` (new, +24 lines) — 접수 면담 봇 페르소나(인사→방문 이유→위기 스크리닝→10턴 내 요약)
- `static/index.html` (modified, +5/-3 lines) — 타이틀/헤더/첫 메시지를 접수 면담용으로 교체
- `tests/test_intake.py` (new, +119 lines) — `_` 제외, 페르소나 주입/폴백, 턴 진행 표기, 접수 요약 저장·실패 격리 5개 테스트

#### 검증 결과
- [x] `.venv/bin/python -m pytest -q` → pass (42 passed, 기존 37 + 신규 5)
- [x] `bash scripts/smoke_local.sh` → pass ("OK: 로컬 통합 스모크 전 구간 통과", `_persona.md` 포함된 실제 knowledge/ 디렉토리로 서버 기동·API·SQLite 배치 확인)

#### 추가 발견사항
없음. `app/llm.py`, `app/storage.py`, `static/app.js`는 scope에 있었으나 기존 구현(fake 모드 doc_titles=[] 스텁, 스키마 없는 role 컬럼, 정적 첫 메시지는 서버 렌더 HTML만으로 충분)을 그대로 재사용할 수 있어 수정 없이 요구사항을 충족했다.

#### 질문 / 결정 사항
없음.

### 2회차 (2026-07-11 21:12 KST) — completed (fix_required 재작업)

**상태**: completed
**소요 시간**: 약 5분
**진행 모델**: Claude `sonnet`

#### 요약
리뷰 지적(재실행 비멱등) 수정. 접수 요약 테스트 2건이 상대경로 `data/conversations`에 고정 session_id로 기록해 pytest 재실행 시 이전 실행분이 누적되던 문제를 `monkeypatch.chdir(tmp_path)`로 격리했다. KNOWLEDGE_DIR는 절대경로(REPO_ROOT 기반)라 chdir 영향 없음을 확인.

#### 변경 파일
- `tests/test_intake.py` (modified, +4/-2 lines) — `test_intake_summary_recorded_once_at_max_turns`, `test_summary_failure_does_not_break_conversation_storage` 두 테스트에 `monkeypatch.chdir(tmp_path)` 추가 (파일 총 +123/-0 lines, untracked)

#### 검증 결과
- [x] `.venv/bin/python -m pytest -q` 1회차 → pass (42 passed)
- [x] `.venv/bin/python -m pytest -q` 2회차 연속 실행 → pass (42 passed, 멱등성 확인)
- [x] `bash scripts/smoke_local.sh` → pass ("OK: 로컬 통합 스모크 전 구간 통과")

#### 추가 발견사항
없음.

#### 질문 / 결정 사항
없음.

#### Commit
- `e5af60f` feat(intake): Phase 9 — 접수 면담 페르소나 주입 + 턴 진행 표기 + 요약 저장 (review pass 0 issues — 오케스트레이터 검증 재실행 1회차 2건 실패 → 테스트 격리 fix 재디스패치 → 2회 연속 멱등 pass, simplify 변경 0)
