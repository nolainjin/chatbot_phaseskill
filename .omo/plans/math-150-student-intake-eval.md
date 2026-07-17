# 수학학원 150명 합성 학생 초기면담 평가 계획

## TL;DR
> Summary:      `knowledge-math` 챗봇을 초등/중등/고등/N수·재수생 150명 synthetic 학생으로 검증하는 데이터 생성기와 평가 하네스를 추가한다. 필수 게이트는 `MODEL=fake` deterministic 전수 평가이며, 실제 모델은 소수 샘플 smoke로만 둔다.
> Deliverables:
> - 150명 synthetic 학생 데이터 생성/검증 CLI
> - `knowledge-math` 전용 초기면담 평가 CLI
> - JSON/TXT/Markdown 결과 산출물
> - no-PII, 분포, 슬롯 커버리지, 리포트 schema 테스트
> - 150명 전수 fake 평가 evidence
> Effort:       Medium
> Risk:         Medium - 150개 synthetic 케이스가 슬롯 신호어와 조건부 슬롯을 충분히 때려야 하며, 기존 상담 평가기와 섞이면 도메인 오염이 생긴다.

## Scope

### Must have

- `knowledge-math` 전용 150명 합성 학생 페르소나를 만든다.
- 학생 분포:
  - 초등 30명
  - 중등 40명
  - 고등 60명
  - N수·재수생 20명
- 스키마에 저장되는 `grade_level` 값은 `knowledge-math/_intake_schema.md`의 허용값에 맞춰 `N수·성인`으로 정규화한다. 화면/리포트 표시 라벨만 `N수·재수생`을 쓸 수 있다.
- 실력 분포:
  - 상위권 30명
  - 중상위권 30명
  - 중위권 30명
  - 하위권 30명
  - 기초 부족 30명
- 트랙 목표:
  - 개념 50명
  - 문제풀이 60명
  - 학습습관 40명
- 각 학생은 `math-student-###`, `math-session-###`만 사용한다.
- 모든 데이터는 synthetic, no-PII, localhost-only, non-production 교육용으로 표시한다.
- 150명 평가에서 다음을 검증한다.
  - 기대 `track`과 실제 `track`
  - `chief_complaint` 채움
  - `grade_level` 채움
  - track별 조건부 슬롯:
    - `개념` -> `concept_gap`
    - `문제풀이` -> `stuck_point`
    - `학습습관` -> `habit_context`
  - `math_topic`, `study_method`, `feedback_habit`, `expectation` coverage
  - 상담형 위기/보호자/전문기관 공유 문구 미노출 유지
- 150명 fake 평가의 필수 pass/fail 게이트:
  - 150 rows produced
  - 0 errors
  - 0 usage-limited
  - `track_accuracy = 150/150`
  - `track` and `chief_complaint` filled for 150/150
  - every persona’s declared track-specific slot filled
  - generated IDs all match `math-student-###` / `math-session-###`
  - JSON/TXT outputs exist
  - no PII scan findings
- 150명 평가 결과는 사람이 읽는 TXT와 기계 검증용 JSON을 모두 남긴다.
- `.omo/evidence`에 검증 증거를 남긴다.

### Must NOT have

- 실제 학생 이름, 학교명, 연락처, 상담 내용, 성적표, 학원 DB를 사용하지 않는다.
- `knowledge-math`에 보호자/전문기관 공유 고지, 자해·자살/위기 접수 슬롯, 안전 위기 칩을 되돌리지 않는다.
- 기존 상담용 `scripts/persona_eval.py`를 수학 전용 로직으로 오염시키지 않는다.
- 기존 demo seeding용 `scripts/generate_demo_population.py`를 수학 평가기로 확장하지 않는다.
- 기존 dirty 파일 `docs/slides/chatbot_development_story_keynote.html`을 건드리지 않는다.
- 승인 draft `.omo/drafts/math-150-student-intake-eval.md`를 삭제하거나 다시 쓰지 않는다.
- `data/` 아래 산출물을 커밋 대상으로 삼지 않는다. `data/`는 `.gitignore` 대상이다.
- 150명 전체 실제 모델 호출을 필수 게이트로 두지 않는다.
- 새 외부 의존성을 추가하지 않는다.

## Verification strategy

> Zero human intervention - all verification is agent-executed.

- Test decision: TDD + pytest
- QA policy: every todo has agent-executed scenarios
- Evidence: `.omo/evidence/task-<N>-math-150-student-intake-eval.<ext>`
- Required final commands:
  - `.venv/bin/python -m pytest -q`
  - `KNOWLEDGE_DIR=knowledge-math MODEL=fake .venv/bin/python scripts/math_student_eval.py --count 150 --workers 1 --out .omo/evidence/math-150-eval --write-profiles .omo/evidence/math-150-students.md`
  - `PORT=8960 bash scripts/smoke_local.sh --pack knowledge-math`
  - Browser/API check against a live `knowledge-math` server confirming title, chip count, and forbidden-copy absence.

## Execution strategy

### Parallel execution waves

> Target 5-8 todos per wave. < 3 per wave (except the final) = under-splitting.

Wave 1 (no deps):

- T1. Confirm current baselines and dirty-worktree guard
- T2. Add failing tests for 150-student dataset distribution and no-PII
- T3. Add failing tests for one/eval-row and report schema
- T4. Add failing tests for math slot coverage and forbidden-copy guard

Wave 2 (after Wave 1):

- T5. Implement deterministic 150-student builder
- T6. Implement math scripted message generation
- T7. Implement math evaluation runner and summary metrics
- T8. Implement CLI output writing

Wave 3 (after Wave 2):

- T9. Add docs/README usage notes
- T10. Run 150-student fake full evaluation and capture evidence
- T11. Run optional small `MODEL=auto` smoke if local model CLIs are available
- T11b. Optional parallel repeatability smoke after deterministic serial gate
- T12. Run local shell/browser smoke for `knowledge-math`

Critical path: T1 -> T2/T3/T4 -> T5/T6/T7/T8 -> T10 -> F1-F4.

### Dependency matrix

| Todo | Depends on | Blocks | Can parallelize with |
|---|---|---|---|
| T1 | none | all | none |
| T2 | T1 | T5 | T3, T4 |
| T3 | T1 | T7, T8 | T2, T4 |
| T4 | T1 | T6, T7 | T2, T3 |
| T5 | T2 | T6, T7 | T8 after interface agreed |
| T6 | T4, T5 | T7 | T8 |
| T7 | T3, T5, T6 | T10 | T8 |
| T8 | T3, T7 | T10 | docs after CLI stable |
| T9 | T8 | F4 | T10, T12 |
| T10 | T5-T8 | F1-F4 | T12 |
| T11 | T8 | F3 risk evidence | T12 |
| T11b | T10 | F2 risk evidence | T12 |
| T12 | T8 | F3 | T10, T11 |

## Todos

> Implementation + Test = ONE todo. Never separate.

- [ ] T1. Baseline and dirty-worktree guard
  What to do / Must NOT do:
  - Record `git status --short`, branch, upstream, and current dirty paths.
  - Confirm `docs/slides/chatbot_development_story_keynote.html` remains untouched.
  - Confirm `.omo/drafts/math-150-student-intake-eval.md` exists and remains untouched after plan execution begins.
  - Confirm `knowledge-math` current smoke still passes before adding eval code.
  - Must NOT reset, checkout, stash, amend, touch the dirty slide file, or rewrite the draft file.
  Parallelization: Can parallel N | Wave 1 | Blocks all / Blocked by none
  References:
  - `.gitignore`
  - `knowledge-math/_intake_schema.md`
  - `tests/test_math_pack.py`
  Acceptance criteria:
  - Evidence file `.omo/evidence/task-1-baseline-math-150-student-intake-eval.txt` contains status, branch, upstream, and smoke command result.
  QA scenarios:
  - Shell: `git status --short`
  - Shell: `PORT=8959 bash scripts/smoke_local.sh --pack knowledge-math`
  Commit: N | none | Files: `.omo/evidence/*`

- [ ] T2. Dataset distribution and no-PII tests
  What to do / Must NOT do:
  - Add failing tests for a deterministic 150-student builder.
  - Assert exact counts: grade distribution 30/40/60/20 and ability distribution 30 each.
  - Assert exact track counts: `개념=50`, `문제풀이=60`, `학습습관=40`.
  - Assert N수·재수 display personas normalize to schema value `N수·성인`.
  - Assert IDs use `math-student-###` and `math-session-###`.
  - Assert generated messages contain no phone-number-like pattern, school names, real names, or email-like strings.
  - Must NOT hardcode all 150 personas directly in test assertions; assert distribution and representative rows.
  Parallelization: Can parallel Y | Wave 1 | Blocks T5 | Blocked by T1
  References:
  - `tests/test_persona_eval.py`
  - `tests/test_math_pack.py`
  - `scripts/generate_demo_population.py`
  Acceptance criteria:
  - New pytest fails before implementation because the math builder does not exist.
  - After implementation, `.venv/bin/python -m pytest -q tests/test_math_student_eval.py` passes.
  QA scenarios:
  - Pytest: `.venv/bin/python -m pytest -q tests/test_math_student_eval.py -k 'distribution or no_pii'`
  - Evidence: `.omo/evidence/task-2-dataset-tests-math-150-student-intake-eval.txt`
  Commit: Y | test(math-eval): add 150-student dataset contract | Files: `tests/test_math_student_eval.py`

- [ ] T3. Evaluation row and report schema tests
  What to do / Must NOT do:
  - Add failing tests for a single synthetic student run result shape.
  - Required row fields:
    - `student_id`
    - `session_id`
    - `grade_band`
    - `ability_band`
    - `expected_track`
    - `actual_track`
    - `track_match`
    - `filled_ids`
    - `missing_expected_ids`
    - `turns`
    - `error`
    - `transcript`
  - Required report metrics:
    - `total`
    - `success`
    - `errors`
    - `usage_limited`
    - `track_accuracy`
    - `required_slot_coverage`
    - `by_grade`
    - `by_ability`
    - `by_track`
    - `failures`
  - Must NOT make assertions on exact free-text bot phrasing.
  Parallelization: Can parallel Y | Wave 1 | Blocks T7, T8 | Blocked by T1
  References:
  - `scripts/persona_eval.py:run_one`
  - `scripts/persona_eval.py:summarize`
  - `app/intake.py:build_summary_json`
  Acceptance criteria:
  - New schema tests fail before implementation and pass after T7/T8.
  QA scenarios:
  - Pytest: `.venv/bin/python -m pytest -q tests/test_math_student_eval.py -k 'row_schema or report_schema'`
  - Evidence: `.omo/evidence/task-3-report-schema-math-150-student-intake-eval.txt`
  Commit: Y | test(math-eval): pin evaluation report schema | Files: `tests/test_math_student_eval.py`

- [ ] T4. Math slot coverage and forbidden-copy tests
  What to do / Must NOT do:
  - Add failing tests that representative generated students hit all three tracks and their conditional slots.
  - Assert `개념` scenarios fill `concept_gap`.
  - Assert `문제풀이` scenarios fill `stuck_point`.
  - Assert `학습습관` scenarios fill `habit_context`.
  - Assert each persona has `initial_message` plus deterministic follow-up answers keyed by expected slot/question intent.
  - Assert forbidden terms stay absent from UI replies and generated student scripts:
    - `보호자`
    - `전문기관`
    - `자신이나 타인`
    - `안전 위기`
    - `자해`
    - `자살`
  - Must NOT reintroduce crisis-specific math schema expectations.
  Parallelization: Can parallel Y | Wave 1 | Blocks T6, T7 | Blocked by T1
  References:
  - `knowledge-math/_intake_schema.md:72`
  - `knowledge-math/_intake_schema.md:115`
  - `knowledge-math/_intake_schema.md:127`
  - `knowledge-math/_intake_schema.md:135`
  - `tests/test_math_pack.py:86`
  Acceptance criteria:
  - New tests fail before implementation and pass after generated scripts cover each slot.
  QA scenarios:
  - Pytest: `.venv/bin/python -m pytest -q tests/test_math_student_eval.py -k 'slot_coverage or forbidden'`
  - Evidence: `.omo/evidence/task-4-slot-coverage-math-150-student-intake-eval.txt`
  Commit: Y | test(math-eval): cover math slot scenarios | Files: `tests/test_math_student_eval.py`

- [ ] T5. Deterministic 150-student builder
  What to do / Must NOT do:
  - Implement synthetic student data model and builder.
  - Keep code compact: use deterministic axes/tables, not 150 handwritten code records.
  - Required file: `scripts/math_student_eval.py`.
  - Required symbols:
    - `MathStudentPersona`
    - `build_math_student_personas(count: int = 150)`
    - `run_one(student, settings)`
    - `summarize(rows)`
  - If pure code lines approach 250, split into a sibling support module such as `scripts/math_student_data.py`.
  - Include grade display label, schema `grade_level`, ability, expected_track, math_topic, scenario_focus, expected_required_slots, `initial_message`, and follow-up messages.
  - Must NOT add dependencies.
  Parallelization: Can parallel Y | Wave 2 | Blocks T6, T7 | Blocked by T2
  References:
  - `scripts/generate_demo_population.py:28`
  - `scripts/generate_demo_population.py:256`
  - `knowledge-math/_intake_schema.md:90`
  Acceptance criteria:
  - `.venv/bin/python -m pytest -q tests/test_math_student_eval.py -k 'distribution or no_pii'` passes.
  - Builder returns exactly 150 unique students.
  QA scenarios:
  - Python CLI import check: `.venv/bin/python -m py_compile scripts/math_student_eval.py`
  - Evidence: `.omo/evidence/task-5-builder-math-150-student-intake-eval.txt`
  Commit: Y | feat(math-eval): build synthetic student cohort | Files: `scripts/math_student_eval.py`, optional `scripts/math_student_data.py`, `tests/test_math_student_eval.py`

- [ ] T6. Scripted student messages for math intake
  What to do / Must NOT do:
  - Implement message generation that answers the bot’s likely next slots over several turns.
  - Each student must include enough messages to cover:
    - first complaint
    - grade
    - topic
    - track-specific conditional slot
    - study method
    - feedback habit
    - expectation
  - Include performance variation:
    - top student: advanced topic, high accuracy but bottleneck in proof/time/strategy
    - mid student: mixed concept/problem gaps
    - struggling student: basics, avoidance, repeated mistakes
  - Must NOT use real school names or student names.
  Parallelization: Can parallel Y | Wave 2 | Blocks T7 | Blocked by T4, T5
  References:
  - `scripts/persona_eval.py:_scripted_patient`
  - `knowledge-math/_intake_schema.md:55`
  - `knowledge-math/_intake_schema.md:101`
  - `knowledge-math/_intake_schema.md:143`
  Acceptance criteria:
  - Slot coverage tests pass.
  - Representative generated messages visibly hit all expected signal groups.
  QA scenarios:
  - Pytest: `.venv/bin/python -m pytest -q tests/test_math_student_eval.py -k 'scripted_messages or slot_coverage'`
  - Evidence: `.omo/evidence/task-6-scripted-messages-math-150-student-intake-eval.txt`
  Commit: Y | feat(math-eval): script math intake student replies | Files: `scripts/math_student_eval.py`, optional `scripts/math_student_data.py`, `tests/test_math_student_eval.py`

- [ ] T7. Evaluation runner and metrics
  What to do / Must NOT do:
  - Implement `run_one(student, settings)` style evaluator using `app.chat.handle_message`.
  - Use `Settings(knowledge_dir="knowledge-math", model=<bot model>)`.
  - Clear `chat._sessions` at run start or use unique session IDs to avoid cross-test contamination.
  - Compute row-level:
    - expected vs actual track
    - filled ids
    - missing expected ids
    - transcript
    - error isolation
  - Compute aggregate summary by grade, ability, track.
  - Hard-code `knowledge_dir=REPO_ROOT / "knowledge-math"` for the evaluator default, while still allowing an explicit CLI override only if tests cover it.
  - In every documented command, also set `KNOWLEDGE_DIR=knowledge-math`.
  - Domain-specific summary must exclude counseling/crisis recall metrics.
  - Must NOT call HTTP for the batch evaluator; direct `handle_message` is faster and mirrors existing `persona_eval.py`.
  Parallelization: Can parallel Y | Wave 2 | Blocks T8, T10 | Blocked by T3, T5, T6
  References:
  - `scripts/persona_eval.py:386`
  - `app/chat.py:352`
  - `app/intake.py:252`
  Acceptance criteria:
  - Row/report schema tests pass.
  - One-student run fills expected track and required slot set.
  QA scenarios:
  - Pytest: `.venv/bin/python -m pytest -q tests/test_math_student_eval.py -k 'run_one or report_schema'`
  - Evidence: `.omo/evidence/task-7-runner-math-150-student-intake-eval.txt`
  Commit: Y | feat(math-eval): evaluate math intake cohort | Files: `scripts/math_student_eval.py`, optional support module, `tests/test_math_student_eval.py`

- [ ] T8. CLI output writing and generated profile catalog
  What to do / Must NOT do:
  - Add CLI flags:
    - `--count`
    - `--workers`
    - `--bot-model`
    - `--out`
    - `--write-profiles`
    - `--sample-auto`
    - optional `--knowledge-dir`, defaulting to `knowledge-math`
  - Default `--count 150`, `--bot-model fake`, `--out data/eval-math`.
  - When writing committed/evidence artifacts, use `.omo/evidence/...` from commands.
  - Write JSON rows and TXT summary.
  - Write Markdown profile catalog when `--write-profiles` is provided.
  - Must NOT require network/model access for default run.
  Parallelization: Can parallel Y | Wave 2 | Blocks T9, T10 | Blocked by T3, T7
  References:
  - `scripts/persona_eval.py:485`
  - `scripts/generate_demo_population.py:198`
  - `.gitignore`
  Acceptance criteria:
  - CLI dry run writes expected files to a temp directory in tests.
  - `--help` exits 0 and mentions key flags.
  QA scenarios:
  - Shell: `.venv/bin/python scripts/math_student_eval.py --help`
  - Pytest: `.venv/bin/python -m pytest -q tests/test_math_student_eval.py -k 'cli or writes_outputs'`
  - Evidence: `.omo/evidence/task-8-cli-output-math-150-student-intake-eval.txt`
  Commit: Y | feat(math-eval): add cohort evaluation CLI outputs | Files: `scripts/math_student_eval.py`, optional support module, `tests/test_math_student_eval.py`

- [ ] T9. Documentation for running the 150-student evaluation
  What to do / Must NOT do:
  - Update exactly one docs surface: either a small README section near the existing eval commands or one new focused doc.
  - Explain:
    - synthetic/no-PII/non-production
    - default fake run
    - optional `MODEL=auto` sample smoke
    - output files
    - how to interpret accuracy and missing slots
  - Must NOT imply the synthetic evaluation is proof of real educational effectiveness.
  Parallelization: Can parallel Y | Wave 3 | Blocks F4 | Blocked by T8
  References:
  - `README.md:92`
  - `README.md:170`
  - `docs/customization-guide.md`
  Acceptance criteria:
  - Documentation includes the exact command for 150 fake run.
  - Documentation states no real student data is used.
  QA scenarios:
  - Shell: `rg -n "math_student_eval|150|synthetic|no-PII|MODEL=fake" README.md docs`
  - Evidence: `.omo/evidence/task-9-docs-math-150-student-intake-eval.txt`
  Commit: Y | docs(math-eval): document 150-student synthetic evaluation | Files: `README.md` or `docs/math-150-student-eval.md`

- [ ] T10. 150-student fake full evaluation
  What to do / Must NOT do:
  - Run the full cohort with deterministic fake model.
  - Use `--workers 1` for the first mandatory pass to avoid global `chat._sessions` concurrency ambiguity.
  - Capture JSON/TXT/Markdown outputs under `.omo/evidence`.
  - Define pass criteria:
    - 150 rows produced
    - no row errors
    - track accuracy 150/150
    - required `track` and `chief_complaint` coverage 150/150
    - declared track-specific slot coverage 150/150
    - no forbidden disclosure terms in transcripts
  - If accuracy/coverage misses threshold, record failing cases and fix generator or schema only if the failure is caused by synthetic message wording. Do not hide real schema defects by weakening assertions.
  Parallelization: Can parallel Y | Wave 3 | Blocks F1-F4 | Blocked by T7, T8
  References:
  - `scripts/math_student_eval.py`
  - `knowledge-math/_intake_schema.md`
  - `app/chat.py:352`
  Acceptance criteria:
  - Command exits 0 and writes JSON/TXT/Markdown evidence.
  - Summary reports 150 total and threshold pass.
  QA scenarios:
  - Shell: `KNOWLEDGE_DIR=knowledge-math MODEL=fake .venv/bin/python scripts/math_student_eval.py --count 150 --workers 1 --out .omo/evidence/math-150-eval --write-profiles .omo/evidence/math-150-students.md`
  - Evidence:
    - `.omo/evidence/math-150-eval/*.json`
    - `.omo/evidence/math-150-eval/*.txt`
    - `.omo/evidence/math-150-students.md`
  Commit: N | evidence only unless repository policy asks to track evidence | Files: `.omo/evidence/*`

- [ ] T11. Optional small real/backend-chain model smoke
  What to do / Must NOT do:
  - Run only a small sample, 12 to 20 students.
  - For true real-model evidence, prefer `--bot-model codex-cli:gpt-5.4`.
  - If using `--bot-model auto`, label the result backend-chain smoke because `auto` can fall back to fake.
  - Record whether Codex/Claude/fake fallback was used if visible from logs.
  - If model CLIs are unavailable or rate-limited, record skipped/blocked with reason; do not fail the whole fake-gated evaluation.
  - Must NOT submit 150 real model conversations by default.
  Parallelization: Can parallel Y | Wave 3 | Blocks F3 risk note | Blocked by T8
  References:
  - `app/llm.py`
  - `.env.example`
  - `tests/test_llm_cli.py`
  Acceptance criteria:
  - Either sample smoke exits 0 or evidence records model CLI unavailability/rate limit as non-blocking.
  QA scenarios:
  - Shell: `KNOWLEDGE_DIR=knowledge-math MODEL=auto .venv/bin/python scripts/math_student_eval.py --count 12 --workers 1 --bot-model auto --out .omo/evidence/math-150-auto-smoke`
  - Evidence: `.omo/evidence/task-11-auto-smoke-math-150-student-intake-eval.txt`
  Commit: N | evidence only | Files: `.omo/evidence/*`

- [ ] T11b. Optional parallel repeatability smoke
  What to do / Must NOT do:
  - After the mandatory serial 150-student pass succeeds, run a parallel repeatability smoke with `--workers 4` or `--workers 8`.
  - Use unique session IDs and verify row count and pass/fail metrics match the serial run.
  - If non-determinism appears, keep serial mode as the required gate and record parallel mode as blocked.
  - Must NOT make parallel workers the primary gate before proving repeatability.
  Parallelization: Can parallel Y | Wave 3 | Blocks F2 risk note | Blocked by T10
  References:
  - `scripts/persona_eval.py:552`
  - `app/chat.py:52`
  Acceptance criteria:
  - Parallel smoke either matches serial metrics or records a concrete concurrency blocker.
  QA scenarios:
  - Shell: `KNOWLEDGE_DIR=knowledge-math MODEL=fake .venv/bin/python scripts/math_student_eval.py --count 150 --workers 4 --out .omo/evidence/math-150-parallel-smoke`
  - Evidence: `.omo/evidence/task-11b-parallel-smoke-math-150-student-intake-eval.txt`
  Commit: N | evidence only | Files: `.omo/evidence/*`

- [ ] T12. Local shell and browser/API smoke for `knowledge-math`
  What to do / Must NOT do:
  - Run existing shell smoke for the pack.
  - Start a local server on an unused port.
  - Use HTTP/API or Playwright to confirm:
    - title is `PNK 수학 학습 코치`
    - chip count is 4
    - forbidden terms absent from page text
    - a problem-solving message fills `track=문제풀이`
  - Stop the server and record cleanup.
  - Must NOT leave QA server running unless user explicitly asks.
  Parallelization: Can parallel Y | Wave 3 | Blocks F3 | Blocked by T8
  References:
  - `scripts/smoke_local.sh`
  - `scripts/gui-smoke/gui-smoke.mjs`
  - `tests/test_config.py`
  - `tests/test_math_pack.py`
  Acceptance criteria:
  - Shell smoke exits 0.
  - Browser/API check exits 0.
  - Cleanup evidence records server stopped.
  QA scenarios:
  - Shell: `PORT=8960 bash scripts/smoke_local.sh --pack knowledge-math`
  - Browser/API: Playwright from `scripts/gui-smoke` or `curl` plus JSON assertion against `http://127.0.0.1:<port>/api/config` and `/api/chat`
  - Evidence: `.omo/evidence/task-12-browser-smoke-math-150-student-intake-eval.txt`
  Commit: N | evidence only | Files: `.omo/evidence/*`

## Final verification wave (after ALL todos)

> Runs in parallel. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.

- [ ] F1. Plan compliance audit
  - Verify every Todo T1-T12 is complete or explicitly documented as non-blocking.
  - Verify `.omo/evidence` contains each referenced evidence artifact.
  - Verify `docs/slides/chatbot_development_story_keynote.html` was not touched by this work.
  - Verify `.omo/drafts/math-150-student-intake-eval.md` still exists.

- [ ] F2. Code quality review
  - Run `.venv/bin/python -m pytest -q`.
  - Run `.venv/bin/python -m py_compile scripts/math_student_eval.py` plus optional support module.
  - Inspect modified Python files for file-size risk. If a file exceeds 250 pure LOC, split or justify as pure data.

- [ ] F3. Real manual QA
  - Run `MODEL=fake` 150-student evaluator through its CLI.
  - Run local shell smoke for `knowledge-math`.
  - Run browser/API check against the live page and stop the server afterward.
  - Record cleanup of any live process.

- [ ] F4. Scope fidelity
  - Confirm no real PII, no school names, no phone/email, no counseling crisis copy in math outputs.
  - Confirm `knowledge/` counseling safety routes were not altered.
  - Confirm optional `MODEL=auto` smoke is marked optional and not treated as the primary pass/fail gate.
  - Confirm no counseling-domain crisis recall metric appears in the math evaluator summary.

## Commit strategy

- Commit 1: `test(math-eval): add 150-student evaluation contracts`
  - Include failing-first tests once implementation makes them pass.
  - Files: `tests/test_math_student_eval.py`
- Commit 2: `feat(math-eval): add synthetic student evaluator`
  - Include evaluator script and optional support module.
  - Files: `scripts/math_student_eval.py`, optional `scripts/math_student_data.py`
- Commit 3: `docs(math-eval): document 150-student synthetic evaluation`
  - Include README/doc updates.
  - Files: `README.md` or `docs/math-150-student-eval.md`

Final commit footers:

`Plan: .omo/plans/math-150-student-intake-eval.md`

Do not commit `.omo/evidence` unless the user asks to preserve evidence in Git. Evidence still must exist locally for final reporting.

## Success criteria

- 150 synthetic students are generated deterministically with approved grade/ability distribution.
- Every generated student is no-PII and uses only synthetic IDs.
- `MODEL=fake` full cohort evaluation produces 150 rows and exits 0.
- Track accuracy is 150/150 in the fake deterministic gate.
- Required `track` and `chief_complaint` coverage is 150/150.
- Declared track-specific slot coverage is 150/150.
- All three math tracks and all track-specific conditional slots are exercised.
- Reports are produced in JSON and TXT, with optional Markdown profile catalog.
- Existing test suite passes.
- `knowledge-math` shell smoke passes.
- Browser/API smoke confirms the live page still shows math UI and no forbidden counseling disclosure copy.
- Existing dirty slide file remains untouched.
