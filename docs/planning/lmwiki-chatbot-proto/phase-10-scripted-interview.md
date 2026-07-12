---
phase: 10
title: 단계 스크립트 순차 면담
status: pending
depends_on: [9]
scope:
  - app/chat.py
  - app/llm.py
  - knowledge/_script.md
  - knowledge/_persona.md
  - tests/test_script.py
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

# Phase 10: 단계 스크립트 순차 면담

> **범위**: Backend (프롬프트 정책 + 스크립트 파일)
> **난이도**: M
> **의존성**: Phase 9 (페르소나 주입·언더스코어 파일 예약 규칙 위에서 동작)
> **영향 파일**: `app/chat.py`, `app/llm.py`, `knowledge/_script.md` (신규), `knowledge/_persona.md` (정합 수정), `tests/test_script.py` (신규)

## 배경

사용자 요청(2026-07-11): 10턴 면담이면 각 단계별 질문을 초기에 정의해두고 순차 진행하는 방식이 좋겠다. 현재는 `_persona.md`의 산문 정책만 보고 봇이 매 턴 알아서 진행해, 단계 누락·순서 뒤섞임을 막을 장치가 없다.

사용자 결정(D10): **대화형 순차 진행** — 단계 스크립트를 미리 정의하고 매 턴 해당 단계 지시를 봇에게 주입하되, 봇은 공감+단계 질문을 자연스러운 대화로 수행한다(설문형 UI 아님, UI 단계 라벨 없음).

부수 효과: 스크립트가 있으면 fake 모드가 해당 단계의 예시 질문을 반환하게 만들어, API 키 없이 면담 흐름 전체를 시연할 수 있다(현재는 "[fake] 참고 문서..." 스텁뿐).

## 심볼 인벤토리

- `app/chat.py` — `handle_message()`, `_load_persona()` (Phase 9), `MAX_TURNS`, 진행 표기 `[진행: n/10턴]`
- `app/llm.py` — `ask()` fake 스텁 경로 (`settings.model == "fake"`)
- `knowledge/_persona.md` — "## 면담 순서" 섹션 (스크립트와 소유권 정리 필요)
- `knowledge/접수-면접-질문지-구성.md` — 단계 스크립트 내용의 근거 문서 (읽기 전용)

## 설계

```
knowledge/_script.md (신규) — 사람이 읽고 고칠 수 있는 단순 형식:
    1-2: 방문 이유 | 오늘 상담을 받으러 오신 이유를 개방형으로 묻고 경청 | 예시: "오늘 어떤 일로..."
    3-4: 구체화 | 주 호소를 구체화(시기·계기·일상 영향) | 예시: "언제부터 그러셨나요?"
    5-6: 대처·지지체계 | 스스로 해본 대처, 주변 지지체계 확인 | 예시: "지금까지 어떻게 견뎌오셨어요?"
    7-8: 위기 스크리닝 | 자·타해 생각, 계획·수단, 약물 확인 — 위험 시 위기개입 안내 | 예시: ...
    9: 상담 기대 | 상담을 통해 기대하는 것 | 예시: ...
    10: 접수 요약 | 네 항목(방문 이유·주 호소·위기 신호·다음 단계)으로 정리하며 마무리 | 예시: ...

chat.py:
    script = knowledge_dir/_script.md 있으면 파싱, 없거나 형식 오류면 None   # 스왑 폴백
    step = script에서 현재 턴(turns+1)이 속한 단계
    system = persona + [진행: n/10턴] + (step 있으면 "[현재 단계: {라벨} — {지시}]") + 지식 문서
    llm.ask(..., fake_hint=step.예시질문 if step else None)

llm.py:
    ask(..., fake_hint=None)   # optional 파라미터, 기본값 None — 기존 호출부 무수정
    fake 모드: fake_hint 있으면 "[fake·면담] {예시질문}" 반환, 없으면 기존 스텁 유지

knowledge/_persona.md:
    "## 면담 순서" 섹션을 스크립트 참조로 축약 — 순서의 소유권은 _script.md로 일원화,
    페르소나는 태도·비밀보장·요약 형식만 소유 (중복 지시 충돌 방지)
```

파서는 정규식 한 줄 수준(`^(\d+)(?:-(\d+))?:` + `|` 구분)으로 유지 — 형식이 어긋난 줄은 건너뛰고, 전체 파싱 실패 시 스크립트 없이 진행한다. 실모델 경로 계약(`llm.ask` 시그니처의 기존 인자, API 계약 `{reply, turn, limit_reached}`, Phase 9 요약 저장)은 무변경.

<!-- ponytail: 스크립트 캐싱·조건 분기(위기 감지 시 단계 점프)는 실사용 피드백 후 -->

## 체크리스트

- [ ] `knowledge/_script.md` 작성 — 10턴 단계 스크립트(턴범위 | 라벨 | 지시 | 예시 질문), `접수-면접-질문지-구성.md`·`위기-상황-스크리닝.md`와 내용 정합, `_persona.md` 면담 순서 섹션은 스크립트 참조로 축약
- [ ] 스크립트 파서: `_script.md` 파싱해 현재 턴의 단계 결정 — 파일 부재·형식 오류 시 스크립트 없이 기존 동작으로 폴백 (tests/test_script.py)
- [ ] 단계 주입: 시스템 프롬프트에 `[현재 단계: 라벨 — 지시]` 결합, 기존 `[진행: n/10턴]`·페르소나·지식 문서 결합 순서 유지 (tests/test_script.py: 프롬프트 조립 검증)
- [ ] fake 모드 데모: `llm.ask`에 optional `fake_hint` 추가(기본 None, 기존 호출 무수정) — 스크립트 있으면 fake 응답이 해당 단계 예시 질문, 없으면 기존 스텁 (tests/test_script.py)
- [ ] 회귀 + 스왑 invariant: 전체 pytest 통과, knowledge-alt(`_script.md` 없음) 스왑 시 기존 Q&A/자유 진행 폴백 (tests/test_script.py)

## 실패 경로

- 스크립트 형식 오류(오타·빈 줄·범위 겹침)로 런타임 오류 → 줄 단위 skip + 전체 실패 시 None 폴백 (test: tests/test_script.py)
- 스왑 디렉토리에 `_script.md` 부재 → 폴백 테스트, Phase 6 invariant 회귀 방지 (test: tests/test_script.py)
- `_persona.md` 면담 순서와 `_script.md` 단계가 서로 다른 지시로 충돌 → 순서 소유권을 스크립트로 일원화하는 체크리스트 1번으로 봉합 (test: 페르소나에 단계 중복 지시 부재 확인은 코드 리뷰로 갈음, accepted_risk: 산문 충돌의 완전 자동 검출은 불가)
- 실모델이 단계 지시를 실제로 따르는지(진행 품질)는 fake 모드로 검증 불가 → Phase 8 실배포 검증 시 사용자와 확인 (needs_user)

## 영향 범위

프롬프트 조립 정책 + fake 스텁 경로 확장. API 계약·rate limit·저장 스키마·Phase 9 요약 로직 무변경. `llm.ask` 시그니처는 기본값 있는 파라미터 추가라 기존 테스트 무영향. UI 무변경(사용자 결정: 단계 라벨 미표시).

## 검증

```bash
.venv/bin/python -m pytest -q
bash scripts/smoke_local.sh
```
