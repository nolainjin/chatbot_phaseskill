# 세션 스토어 분리 — Phase 1: 현황 분석 (정정된 인벤토리)

> 이 문서는 서술이 목적이다. "이 상태가 왜 문제인가"에 대한 해소 논증(불변식 충족 여부)은
> Phase 5가 맡는다. 저장 배치·인터페이스 설계는 각각 Phase 4·Phase 6 소관이다.
>
> intake 단계 수치 중 2건이 phase-init 재검증에서 오류로 확인되어 이 문서에서 정정한다:
> `_sessions` 직접 접근이 6곳이 아니라 **37곳/13파일**(app/chat.py 내부 참조 6건은 별도),
> `append_turn` ↔ `history.append` 비대칭이 3곳이 아니라 **5곳**이다. 이 문서를 작성하며
> `ChatSession` 필드 수(스펙 기재 6 → 실측 7)도 추가로 어긋난 것을 발견했다 — 상세는
> [§3](#3-chatsession-필드-인벤토리)과 실행 결과의 추가 발견사항 참고.

## 1. 블로커 4건

원 스펙(origin)이 확정한 병목 4가지. 모두 사용자 실측 제공이라 재조사 대상이 아니다(CAP22) —
아래는 코드 위치 재확인 결과다.

| # | 블로커 | 위치 | 내용 |
|---|--------|------|------|
| 1 | 세션 상태가 프로세스 메모리 dict | `app/chat.py:57` `_sessions: dict[str, ChatSession] = {}` | 모듈 전역 dict. 워커 프로세스 간 공유되지 않고, 재시작 시 전량 소실. 상단 모듈 docstring(`app/chat.py:1-5`)도 "재시작 시 소실은 프로토타입 수용 범위"라고 명시. |
| 2 | `RateLimiter` 단일 워커 전제 | `app/ratelimit.py:63` `class RateLimiter:`, 주석 `:66-68` | `threading.Lock`(프로세스 내부 락) + 로컬 JSON 파일 원자적 교체(`os.replace`, `:88`)로 카운터를 관리. 클래스 docstring이 "단일 uvicorn 워커 전제 ... 수평 확장 시 Redis 등 외부 스토어로 교체"라고 자기 한계를 명시. |
| 3 | `append_turn` 전체 재작성 | `app/storage.py:71` `def append_turn(...)` | 매 호출마다 오늘 날짜 파일을 read(`:88`) → 메모리에서 turn append(`:91`) → 파일 전체 write(`:92`)하는 read-modify-write. 모듈 docstring은 "세션당 최대 20턴이라 파일 전체를 매번 재작성해도 충분히 가볍다"고 설계 근거를 남겼다 — 동시 write 시 레이스는 별도 문제(Phase 3 소관). |
| 4 | `--workers 1` 고정 | `Dockerfile:30` `CMD [...  "--workers", "1"]` | 사유 주석은 `Dockerfile:25-29`: (1) `RateLimiter`가 프로세스 내부 락 전제, (2) `app/chat.py`의 `_sessions`가 프로세스 메모리 dict라 워커가 여럿이면 세션별 10턴 캡이 워커마다 따로 계산됨. 두 블로커(#1, #2)가 이 고정의 직접 원인. |

## 2. `_sessions` 직접 접근 인벤토리 — 37곳 / 13파일 (+ app/chat.py 내부 6건)

`grep -rn '\b_sessions\b' --include='*.py'`(단어 경계, 부분문자열 오탐 배제)로 저장소 전체를
전수 조사했다. `app/chat.py`가 `_sessions`를 정의·소유하는 모듈이므로 그 내부 6개 참조는
"소유자 접근"으로 별도 행에 두고, 나머지 13개 파일의 37개 접근을 "외부 직접 접근"으로 집계한다.

### 2.1 app/chat.py 내부 참조 (소유자, 6건 — 37에 불포함)

| 라인 | 코드 | 성격 |
|------|------|------|
| 57 | `_sessions: dict[str, ChatSession] = {}` | 정의 |
| 61 | `return session_id in _sessions` | 존재 확인 (`has_session`) |
| 65 | `session = _sessions.get(session_id)` | 조회 (`owns_session`) |
| 74 | `session = _sessions.get(session_id)` | 조회 (`session_token`) |
| 79 | `session = _sessions.get(session_id)` | 조회 (`_get_session`) |
| 82 | `_sessions[session_id] = session` | 신규 세션 등록 (`_get_session`) |

### 2.2 외부 직접 접근 — lifecycle 변경 (`.pop()` / `.clear()`, 7건)

| 파일 | 라인 | 코드 |
|------|------|------|
| app/knowledge_pack_exercise.py | 37 | `chat._sessions.pop(session_id, None)` |
| scripts/generate_demo_population.py | 265 | `chat._sessions.clear()` |
| scripts/red_team_prompt_injection.py | 46 | `chat._sessions.clear()` |
| scripts/tone_eval.py | 118 | `chat._sessions.clear()` |
| scripts/tone_eval.py | 134 | `chat._sessions.clear()` |
| tests/test_math_pack.py | 29 | `chat._sessions.pop("math-coaching", None)` |
| tests/test_math_pack.py | 72 | `chat._sessions.pop("math-fake-coaching", None)` |

### 2.3 외부 직접 접근 — 첨자 읽기 (30건: `.slots` 19 / `.history` 1 / 변수 대입 10)

같은 줄에서 바로 `.slots`/`.history`를 잇는 접근과, `session = chat._sessions[id]`처럼 변수에
받아 다음 줄에서 쓰는 접근을 구분했다. 후자도 "첨자 읽기"로 집계된다(스펙의 30건에 포함).

**`.slots` 직접 접근 (19건)**

| 파일 | 라인 |
|------|------|
| tests/test_addiction.py | 78, 98, 129 |
| tests/test_chat.py | 128 |
| tests/test_relationship_slot_semantics.py | 28, 33, 71 |
| tests/test_safety.py | 222 |
| tests/test_slot_e2e.py | 67, 78, 152, 166, 183, 230, 241, 256, 263, 264, 276 |

**`.history` 직접 접근 (1건)**

| 파일 | 라인 | 코드 |
|------|------|------|
| tests/test_security.py | 49 | `chat._sessions["sec-output-bound"].history` |

**변수 대입 후 사용 (10건)**

| 파일 | 라인 |
|------|------|
| tests/test_safety.py | 196 |
| tests/test_slot_e2e.py | 93, 109, 126 |
| tests/test_slot_extract.py | 214, 231, 287 |
| tests/test_slot_flow.py | 86, 99, 130 |

### 2.4 파일별 합계 (37건 검산)

| 파일 | 건수 |
|------|------|
| tests/test_slot_e2e.py | 14 |
| tests/test_slot_flow.py | 3 |
| tests/test_slot_extract.py | 3 |
| tests/test_relationship_slot_semantics.py | 3 |
| tests/test_addiction.py | 3 |
| tests/test_safety.py | 2 |
| tests/test_math_pack.py | 2 |
| tests/test_security.py | 1 |
| tests/test_chat.py | 1 |
| scripts/tone_eval.py | 2 |
| scripts/red_team_prompt_injection.py | 1 |
| scripts/generate_demo_population.py | 1 |
| app/knowledge_pack_exercise.py | 1 |
| **합계** | **37** |

7(lifecycle) + 30(첨자 읽기) = **37**. 13개 파일. app/chat.py 내부 6건은 별도.

### 2.5 부분문자열 오탐 — 스토어 참조 아님 (표에서 제외)

`app/stats.py`와 `app/ratelimit.py`에 `_sessions`로 끝나는 식별자가 있지만 단어 경계
검사(`\b_sessions\b`)에는 걸리지 않는다 — `app/chat.py`의 세션 dict와 무관한 별개 데이터다.
후속 감사가 단순 `grep _sessions`(부분문자열)로 조사하면 아래 6줄이 섞여 37건이 아니라
60건대로 오보고할 수 있어 명시적으로 배제한다.

| 파일 | 라인 | 식별자 | 실체 |
|------|------|--------|------|
| app/stats.py | 43, 308, 320, 426 | `red_flag_sessions` | SQLite 통계 집계용 로컬 카운터/딕셔너리 키. `chat._sessions`와 무관. |
| app/ratelimit.py | 77, 97 | `known_sessions` | `RateLimiter`가 디스크에 영속하는 JSON 상태의 키(`data/ratelimit.json`). 세션 dict가 아니라 "이미 카운트한 session_id" 집합. |

## 3. `ChatSession` 필드 인벤토리

`app/chat.py:46-47`(`@dataclass` 데코레이터 + `class ChatSession:`)를 AST로 파싱해 실측한
결과 **필드는 7개**다(스펙 서술은 6개 — §추가 발견사항 참고). `session_id`는 저장소 설계
관점에서 맵의 키(식별자)로 쓰이고 나머지 6개가 "값" 필드라서, 스펙의 "6 필드"는 아마
`session_id`를 키로 보고 제외한 셈으로 추정된다. 저장 배치(어느 필드를 어느 스토어에 둘지)
결정은 Phase 4 소관이며, 이 표는 현재 용도만 기재한다.

| 필드 | 타입 / 기본값 | 근거 라인 | 현재 용도 |
|------|---------------|-----------|-----------|
| `session_id` | `str` (필수, 키 역할) | chat.py:48 | `_sessions` dict의 키. API 요청의 `session_id`와 1:1. |
| `session_token` | `str`, `secrets.token_urlsafe(32)` 기본 생성 | chat.py:49 | 세션 소유권 인증 토큰. `owns_session()`(chat.py:64)이 `secrets.compare_digest`로 비교. 신규 세션 생성 시 API 응답에 1회 반환(main.py:59). |
| `turns` | `int`, 기본 0 | chat.py:50 | 완료된 턴 수. `MAX_TURNS`(10) 도달 판정(chat.py:358, 505)과 진행 표시(`progress` 문자열, chat.py:365)에 사용. |
| `history` | `list[dict[str, str]]`, 기본 `[]` | chat.py:51 | LLM 호출 컨텍스트(`llm.ask(history=session.history, ...)`, chat.py:464). role은 `user`/`assistant`만 들어간다(§5 참고) — `storage`가 저장하는 `intake_summary` 턴은 여기 없다. |
| `slots` | `dict[str, str]`, 기본 `{}` | chat.py:52 | 접수(intake) 슬롯 채움 상태. 라우팅(위기/중독 트랙 판단), 슬롯 패널 응답(`_intake_state`), 요약 생성(`intake.build_summary_json`)의 입력. |
| `last_question_slot_id` | `str \| None`, 기본 `None` | chat.py:53 | 직전에 질문한 슬롯 id. `_answer_to_previous_question`(chat.py:231)이 다음 사용자 발화를 이 슬롯에 대한 답으로 볼지 판단하는 폴백 근거. |
| `participant_id` | `str \| None`, 기본 `None` | chat.py:54 | 가명화된 내담자 식별자. 최초 요청에서만 설정(chat.py:354-356), 이후 `effective_participant_id`로 저장 계층에 전달. `session_id`와 별개 — 없으면 `session_id`로 폴백(chat.py:356). |

## 4. 401 분기 추적 — `has_session()==False` + `conversation_exists()==True`

`app/main.py`의 `POST /api/chat` 진입부 조건 조합을 추적한다.

- `:43` `session_was_known = chat.has_session(session_id)`
- `:44-46` `if session_was_known: if not chat.owns_session(...): raise 401`
- `:47-48` `elif storage.conversation_exists(session_id): raise 401 "만료된 세션입니다."`

| `has_session()` | `owns_session()` (has_session=True일 때만 평가) | `conversation_exists()` (has_session=False일 때만 평가) | 결과 |
|---|---|---|---|
| True | True | (미평가) | 통과 — 기존 세션으로 `chat.handle_message` 진행 |
| True | False | (미평가) | `401 "세션 인증이 필요합니다."` (main.py:46) |
| False | (미평가) | True | `401 "만료된 세션입니다. 새 세션으로 시작해 주세요."` (main.py:48) |
| False | (미평가) | False | 통과 — 신규 세션으로 `chat.handle_message` 진행, 응답에 `session_token` 포함(main.py:58-59) |

`conversation_exists()`(storage.py:29-36)는 `date.today().isoformat()` 디렉터리만 조회하므로,
이 401 분기는 "메모리 세션은 없지만(워커 재시작·리로드 등으로) 오늘자 대화 JSON 파일은
남아있는" 경우에만 발동한다. 도달 가능성 논증(재현 시나리오 구성)은 Phase 5 소관이다.

## 5. `append_turn` ↔ `history.append` 비대칭 지도 + 날짜 파티션

### 5.1 전체 집계

`app/chat.py` 안에서 `storage.append_turn(...)` 호출은 **9곳**(chat.py:320, 321, 330, 405,
406, 498, 499, 510, 525), `session.history.append(...)` 호출은 **5곳**(chat.py:323, 324, 407,
501, 502)이다. 비대칭은 5건으로 정리된다.

### 5.2 비대칭 5건

| # | storage 사이트 | history 사이트(대응 없음/조건부) | 원인 |
|---|-----------------|-----------------------------------|------|
| (a) | chat.py:330 `storage.append_turn(..., "intake_summary", ...)` (`_handle_addiction_route` 내부, 10턴 도달 시) | 없음 | `intake_summary`는 role 자체가 history에 없는 결정론적 요약 저장 — LLM 컨텍스트로 되먹임하지 않는다. |
| (b) | chat.py:510 `storage.append_turn(..., "intake_summary", ...)` (`handle_message`, 스키마 있는 경로, 10턴 도달 시) | 없음 | (a)와 동일한 이유. |
| (c) | chat.py:525 `storage.append_turn(..., "intake_summary", ...)` (`handle_message`, 스키마 없는 폴백 경로, LLM 요약 성공 시) | 없음 | (a)와 동일한 이유. |
| (d) | chat.py:405 `storage.append_turn(session_id, "user", message, ...)` (인젝션 차단 분기, `safety_assessment.blocked`, chat.py:373) | chat.py:407은 `assistant`만 history에 추가 — `user` 대응 없음 | 차단된 사용자 발화는 로그(storage)에는 남기지만, 다음 LLM 호출 컨텍스트(history)에는 넣지 않는다 — 인젝션 시도 문구가 모델 프롬프트에 재노출되는 것을 막는 설계로 추정. |
| (e) | chat.py:320 `storage.append_turn(..., "user", message, ...)` (`_handle_addiction_route`, 무조건) | chat.py:322-323은 `include_user_in_model_context`가 True일 때만 `user`를 history에 추가 | 저장(감사 로그)은 항상 원문을 남기지만, LLM 컨텍스트 포함 여부는 `include_user_in_model_context` 플래그로 분리 제어된다. |

**(d)·(e)는 독립된 두 사이트가 아니라 상호배타 분기다.** `handle_message`의 인젝션 차단
분기(`:373 if safety_assessment.blocked:`) 안에서 중독 라우트가 감지되면
`:386-398`에서 `elif assessment := addiction.assess(...): return _handle_addiction_route(...,
include_user_in_model_context=False)`로 **조기 return**한다(`:391`). 이 return 때문에 같은
호출에서 (d)의 `:405-407` 코드는 실행되지 않는다 — 즉 한 요청은 (d) 아니면 (e) 중 하나만
탄다. 두 지점을 별개 누적 사례로 세면 실제보다 비대칭이 부풀려진다.

### 5.3 날짜 파티션 구조

- `storage.py:84` `day_dir = Path(base_dir) / date.today().isoformat()` — 대화 JSON은
  `data/conversations/YYYY-MM-DD/{session_id}.json`에 날짜별로 분산 저장된다.
- `storage.py:91` `turns.append({"seq": len(turns), "role": role, "text": text})` — `seq`는
  그 날짜 파일 안에서 `len(turns)`로 매겨진다. 즉 **하루가 바뀌면 같은 세션이라도 새 파일에서
  `seq`가 0부터 다시 시작한다** — 세션 전체를 관통하는 단조 증가 시퀀스가 아니다.
- `storage.py:29-36` `conversation_exists()`는 `date.today().isoformat()` 디렉터리만 조회한다
  — 어제 이전 날짜의 대화 파일이 있어도 오늘 기준으로는 "존재하지 않음"으로 판정된다(§4의
  401 분기가 정확히 "오늘자" 파일 유무에만 반응하는 이유).

## 6. 회귀 기준선

`"$ROOT/.venv/bin/python" -m pytest -q`를 이 문서 작성 시점에 직접 실행해 **209 passed**를
확인했다(경고 1건은 `httpx`/`starlette.testclient` deprecation으로 테스트 결과와 무관).
재현 시 반드시 저장소 venv 인터프리터(`$ROOT/.venv/bin/python`)를 써야 한다 — 맨몸 `python`에는
pytest가 설치돼 있지 않다. 이후 모든 페이즈는 이 **209 passed**를 유지해야 할 회귀 기준선으로
삼는다.
