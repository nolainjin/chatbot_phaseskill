# Draft: math-150-student-intake-eval

status: approved-plan-written
pending_action: none
mode: omo:ulw-plan
created_at: 2026-07-16
approved_at: 2026-07-16
plan_path: .omo/plans/math-150-student-intake-eval.md

## 사용자 목표

`knowledge-math` 수학학원 챗봇에 대해 초등/중등/고등/N수·재수생 총 150명의 합성 학생 페르소나를 만들고, 수학을 잘하는 학생부터 매우 어려워하는 학생까지 다양한 초기 면담 입력을 돌려 결과를 검증할 수 있는 계획을 수립한다.

## 범위 분류

HEAVY.

근거:

- 새 synthetic data set 150명 생성이 필요하다.
- 평가 하네스/결과 리포트/테스트/문서/증거 산출까지 3개 이상 표면을 건드릴 가능성이 높다.
- 기존 상담용 `scripts/persona_eval.py`와 demo seeding용 `scripts/generate_demo_population.py`가 있으나 수학팩과 목적이 다르다.
- 사용자 요청이 “데이터도 만들고 결과테스트 검증도 같이”라서 구현 계획과 QA 계획이 모두 필요하다.

## 탐색 사실

### 기존 평가/생성 표면

- `scripts/persona_eval.py`는 상담 도메인 페르소나 평가 하네스다. `PERSONAS`, `_scripted_patient`, `_ask_patient_codex`, `run_one`, `summarize`, CLI 옵션 `--runs`, `--workers`, `--out`, `--patient-mode`, `--bot-model`을 가진다.
- `scripts/persona_eval.py`의 출력은 `data/eval/eval-<timestamp>.json`과 `.txt`이다.
- `tests/test_persona_eval.py`는 usage-limit 감지, scripted patient 진행, Codex patient output 추출, hidden crisis 1개 회귀를 검증한다.
- `scripts/generate_demo_population.py`는 100명 상담 demo 생성/SQLite 적재용이다. 평가기가 아니라 demo seeding 도구다.
- `scripts/load_to_sqlite.py`는 날짜별 JSON 대화를 SQLite에 UPSERT한다.

### knowledge-math 흐름

- `knowledge-math/_intake_schema.md`는 트랙 `개념 / 문제풀이 / 학습습관`을 선언한다.
- 주요 슬롯:
  - `track`
  - `chief_complaint`
  - `grade_level`
  - `math_topic`
  - `stuck_point` when `track=문제풀이`
  - `concept_gap` when `track=개념`
  - `habit_context` when `track=학습습관`
  - `study_method`
  - `feedback_habit`
  - `expectation`
- `app/chat.py::handle_message()`가 `intake.extract_fake()`와 `schema.unfilled_by_priority()`로 슬롯을 채우고 다음 질문을 정한다.
- `app/intake.py::build_summary_json()`은 `track`, `slots`, `unfilled`, `red_flags`를 저장한다.
- `tests/test_math_pack.py`는 현재 한 개의 문제풀이 경로, UI 문구, 상담형 위기 고지 미노출을 검증한다.
- `tests/test_config.py`는 `/api/config`에서 `knowledge-math` UI가 내려오는지 검증한다.

### 현재 작업트리 보호

- 기존 dirty 파일: `docs/slides/chatbot_development_story_keynote.html`
- 계획 실행 시 이 파일은 scope out으로 기록하고 건드리지 않는다.

## 채택한 기본값

### 데이터 구성

권장 기본 분포:

- 초등: 30명
- 중등: 40명
- 고등: 60명
- N수·재수생: 20명

이유: 수학학원 초기 상담에서 고등/수능/N수 비중이 평가 난도가 높고, 학습 주제/시험/오답/시간 부족 다양성이 커진다.

능력대 기본 분포:

- 상위권: 30명
- 중상위권: 30명
- 중위권: 30명
- 하위권: 30명
- 기초 부족: 30명

트랙 기본 목표:

- 개념: 약 50명
- 문제풀이: 약 60명
- 학습습관: 약 40명

각 학생은 실제 개인정보 없이 `math-student-###`, `math-session-###`만 사용한다.

### 평가 모드

1차 필수:

- `MODEL=fake`
- deterministic scripted student messages
- 150명 전수 실행
- 실패/불일치/미충족 슬롯 JSON 리포트 생성

2차 선택:

- `MODEL=auto` 또는 `codex-cli:gpt-5.4`로 소수 샘플 12~20명만 실제 모델 smoke
- 비용/한도 리스크가 있으므로 필수 게이트는 아니다.

### 테스트 전략

TDD 권장.

먼저 실패하는 테스트:

- 150명 builder가 정확히 150명을 만들고 no-PII ID만 쓰는지
- 학년/능력/트랙 분포가 기대값과 맞는지
- fake 평가기가 모든 학생을 실행하고 JSON/TXT 결과를 남기는지
- 결과 요약이 track accuracy, required-slot coverage, unfilled counts, per-grade/per-ability breakdown을 포함하는지

그 다음 구현.

## 계획할 접근

계획 파일에는 다음 실행 단위를 넣는다.

1. 새 수학 학생 데이터 모델과 150명 builder 설계
2. scripted student 발화 생성 규칙 작성
3. `scripts/math_persona_eval.py` 신규 평가기 작성
4. 결과 JSON/TXT schema 고정
5. no-PII/분포/슬롯 커버리지 단위 테스트 작성
6. 150명 fake 전수 평가 smoke
7. 실패 케이스 리포트와 evidence 저장
8. 선택적 소수 `MODEL=auto` smoke
9. README 또는 docs에 실행법 추가
10. 기존 dirty 파일 보호 확인

## 범위 밖

- 실제 학생 개인정보 사용
- 외부 수학학원 DB 연동
- 통계 화면의 상담 도메인 문구 전체 교체
- `docs/slides/chatbot_development_story_keynote.html` 수정
- 대규모 실제 모델 150명 전수 호출을 필수 게이트로 설정
- `knowledge-math`에 위기/보호자/전문기관 공유 고지 재도입

## 남은 사용자 승인 사항

아래 기본값으로 계획 파일을 작성할지 승인 필요.

1. 분포: 초 30 / 중 40 / 고 60 / N수·재수 20
2. 능력대: 5단계 균등 30명씩
3. 필수 검증: `MODEL=fake` 150명 deterministic 전수 평가
4. 선택 검증: `MODEL=auto` 소수 샘플 smoke만 계획에 포함
5. 테스트 전략: TDD

## 승인 후 작업

사용자가 승인했고 다음을 수행했다.

1. Metis gap analysis를 수행했다.
2. `.omo/plans/math-150-student-intake-eval.md` 하나만 작성했다.
3. 계획 요약을 제시하고 “바로 실행할지 / Momus 고정밀 계획 리뷰를 먼저 할지” 한 가지 질문만 한다.
