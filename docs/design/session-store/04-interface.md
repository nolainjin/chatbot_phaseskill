# 세션 스토어 분리 — Phase 4: `SessionStore` 인터페이스 설계

> D06 에서 사용자는 권장안(기존 시그니처 보존)이 아니라 **인터페이스 전면 재설계**를 택했다
> ([decisions.md#D06](../../planning/session-store-multiworker/decisions.md), `status: answered`).
> 이 문서는 그 선택이 약속한 이득 — 생성·만료·소유권 검증을 한 곳에 모아 TTL(D03)과 맞물리게
> 하는 것 — 을 실제로 수확하는 자리다.
>
> 입력 문서: [Phase 1 현황 분석](./01-current-state.md)(정정된 인벤토리 — `ChatSession` 필드
> **7개**, `_sessions` 직접 접근 37곳/13파일, 날짜 파티션 구조), [Phase 2 정책 결정](./02-policy-decisions.md)
> (D01·D03·D04·D05 확정), [Phase 3 개인정보 경계와 `history` 복원](./03-history-restore.md)
> (해소안 (다), `(day, seq)` 전역 순서, `append_turn` 반환 시그니처 요구).
>
> 이 문서 작성으로 저장소 코드는 **한 줄도 바뀌지 않는다**(CAP04·CAP08·CAP09). 아래 모든
> 시그니처·스키마는 **설계 표기**이며 구현체가 아니다. 목표 달성 논증(불변식)은 Phase 5,
> 이행 절차는 Phase 6 소관이다.

---

## 0. 이 문서가 정하는 것 — 한 문장

세션 스토어는 **"지금 이 세션이 어떤 상태인가"에 대한 유일한 권위**이며, 그 권위는
**연산 집합과 오류 코드**로만 드러난다 — 호출부가 스토어 밖에서 세션 레코드를 읽어 고친 뒤
되쓰는 경로는 이 설계에 **존재하지 않는다.**

이 한 문장이 §4(생성 원자성)·§5(10턴 캡)·§6(대화 쓰기)의 세 경합을 같은 방식으로 닫는다.
세 경합은 모두 **read-modify-write 가 API 형태로 노출되어 있다**는 하나의 원인에서 나온다.

---

## 1. 연산 집합

### 1.1 반환 규약

모든 연산은 두 형태 중 하나를 돌려준다. 예외를 오류 채널로 쓰지 않는다 — 오류 시맨틱이
타입에 드러나야 호출부가 `없음`과 `만료됨`을 **구분해서** 처리하도록 강제할 수 있다
(오늘 `owns_session`(`app/chat.py:64`)은 이 둘을 `False` 한 값으로 뭉갠다).

```
Ok(value)              성공. value 의 형태는 연산별로 §1.4 에 정의한다.
Err(code, detail)      실패. code ∈ { NOT_FOUND, CONFLICT, EXPIRED, CORRUPT }
```

### 1.2 오류 시맨틱 — 네 코드의 정확한 의미

| 코드 | 한국어 | 의미 | 발생 조건 | 호출부가 해야 할 일 | 오늘의 대응 지점 |
|------|--------|------|-----------|----------------------|------------------|
| `NOT_FOUND` | 없음 | 그 `session_id` 의 레코드가 스토어에 **없다** | 한 번도 만들어지지 않았거나, 이미 만료 정리가 끝난 뒤 | 신규 세션 생성(`open_session`) 또는 401 | `has_session()` 이 `False` (`app/chat.py:61`) |
| `EXPIRED` | 만료됨 | 레코드가 **있었으나** `now - last_activity_at > 24h` 라서 **이 호출이 그 자리에서 삭제했다**(D03 lazy sweep) | 조회·갱신 계열 연산의 진입부 | HTTP 401 `"만료된 세션입니다. 새 세션으로 시작해 주세요."` (`app/main.py:48` 의 문구를 그대로 재사용) | 오늘 존재하지 않는 상태 — 만료 개념 자체가 없다 |
| `CONFLICT` | 경합 | `busy_timeout` 안에 쓰기 락을 얻지 못했다 | SQLite `SQLITE_BUSY` | HTTP 503 + 재시도. **멱등 연산만** 재시도 가능(§1.5) | 오늘 존재하지 않는 상태 |
| `CORRUPT` | 손상 | 레코드 역직렬화 실패, 또는 매체 간 불일치 탐지(§6.4) | JSON 컬럼 파싱 실패, 대화 파일 턴 수 < 인덱스 기대치 | HTTP 500 + 로그. **자동 복구·자동 삭제 금지** | `normalize_conversation_payload`(`app/storage.py:39`)가 오늘 조용히 흡수하는 계열 |

**`EXPIRED` 는 일회성 신호다.** lazy sweep 이 같은 호출 안에서 레코드를 지우므로, 같은
`session_id` 에 대한 **다음** 호출은 `NOT_FOUND` 를 돌려준다. 이는 결함이 아니라 의도다 —
401 응답이 클라이언트에게 "새 세션으로 시작하라"고 이미 지시했고, 그 다음 요청은 실제로
신규 세션이기 때문이다. 이 성질을 모르는 구현이 "`EXPIRED` 가 안정적으로 반복 관측된다"고
가정하면 안 된다.

**`EXPIRED` 판정의 오라클은 `conversation_exists()` 가 아니다.** Phase 3 §3.4 가 기록한
어긋남(`app/storage.py:29-36` 은 오늘 디렉터리만 본다) 때문에, 만료 판정은 **스토어 레코드의
`last_activity_at`** 이 단독으로 담당한다. `conversation_exists()` 는 새 401 경로에서 호출되지
않는다. 이 변경이 CAP12·CAP13(거짓 401 제거)에 실제로 닿는지의 **논증**은 Phase 5 소관이며,
이 문서는 판정 오라클을 바꿨다는 사실까지만 확정한다.

### 1.3 설계 규칙 두 개

> **R1 — 스토어 밖에서 레코드를 고쳐 되쓰지 않는다.**
> 모든 갱신 연산은 *무엇을 어떻게 바꿀지*를 인자로 받고, **스토어 내부 트랜잭션 안에서**
> 읽고 고치고 쓴다. `put(record)` / `save(session)` 같은 **전체 덮어쓰기 API 를 두지 않는다.**
> 이 규칙이 없으면 §5 의 10턴 캡 lost update 가 API 형태 그 자체로 되살아난다.

> **R2 — 판정과 변경은 한 문장 안에 있다.**
> "캡을 넘었는지 확인한 뒤 증가", "있는지 확인한 뒤 생성" 같은 check-then-act 를 두 연산으로
> 쪼개지 않는다. 판정은 `WHERE` 절로 내려가고, 판정 결과는 영향 행 수로 되돌아온다.

R1·R2 는 §4·§5·§6 에서 각각 한 번씩 실제로 쓰인다.

### 1.4 자료형

```
SessionView                      # 읽기 전용 스냅샷. 이걸 고쳐 되쓰는 경로는 없다 (R1)
  session_id            : str            # 키
  session_token         : str
  turns                 : int
  slots                 : dict[str, str]
  last_question_slot_id : str | None
  participant_id        : str | None
  turn_partitions       : dict[str, int] # {"2026-07-27": 4, ...}  day -> 그 날 파일의 턴 수
  context_excluded      : list[TurnKey]  # 저장됐지만 history 에서 제외된 턴 (Phase 3 §2.4)
  last_activity_at      : str            # ISO 8601 UTC — D03 TTL 판정 기준

TurnKey  = (day: str, seq: int)          # ISO "YYYY-MM-DD" + 그 파일 안의 정수 seq
TurnGrant= (turn_no: int, limit_reached: bool)
RateVerdict = ALLOWED | DENIED_WINDOW | DENIED_DAILY
```

`turn_partitions` 는 Phase 3 §2.4 의 `turn_days`(날짜 **집합**)를 **날짜 → 턴 수 사상**으로
좁힌 것이다. 키 집합은 `turn_days` 와 동일하므로 Phase 3 의 §3.3 열거는 그대로 성립하고,
날짜당 정수 하나가 늘어난다. 이 정수가 §6.4 의 매체 간 불일치를 **읽기·쓰기 두 국면 모두에서**
안전한 쪽으로 닫는 장치이며(§6.5), 그것이 이 좁힘의 유일한 이유다. (Phase 3 §5.3 이 "임계 구역의 구체 범위"와 "반환값의
구체 형태"를 이 페이즈로 넘겼다.)

`TurnKey` 의 비교는 **튜플 비교**다. Phase 3 §3.2 가 경고한 문자열 결합(`"2026-07-27#10" <
"2026-07-27#9"`)을 이 설계도 금지한다.

### 1.5 연산 표

`now` 는 모든 연산이 인자로 받는다 — 스토어 내부에서 `date.today()` / `datetime.now()` 를
호출하지 않는다. 시간을 주입 가능하게 두어야 TTL·자정 경계 테스트가 가능하고, 무엇보다
**한 요청 안에서 시간 기준이 두 번 평가되는 일**(Phase 3 §5.2 의 자정 경합)이 구조적으로
사라진다.

| # | 연산 | 인자 | 성공 반환 `Ok(...)` | 가능한 `Err` 코드 | 멱등 | 비고 |
|---|------|------|---------------------|-------------------|------|------|
| 1 | `open_session` | `session_id`, `now` | `(SessionView, created: bool)` | `CONFLICT`, `CORRUPT` | 예 | **생성·조회 통합**(§4). `NOT_FOUND`/`EXPIRED` 를 반환하지 않는다 — 없으면 만들고 만료됐으면 지운 뒤 만든다 |
| 2 | `get_session` | `session_id`, `now` | `SessionView` | `NOT_FOUND`, `EXPIRED`, `CONFLICT`, `CORRUPT` | 예 | 읽기 전용 경로. 진입부에서 lazy sweep 판정(D03) |
| 3 | `verify_owner` | `session_id`, `token`, `now` | `bool` | `NOT_FOUND`, `EXPIRED`, `CONFLICT`, `CORRUPT` | 예 | **토큰 불일치는 오류가 아니라 `Ok(False)`** — "세션 없음"(401 만료 문구)과 "토큰 틀림"(401 인증 문구)을 호출부가 구분할 수 있어야 하기 때문. 비교는 `secrets.compare_digest` 를 유지한다(`app/chat.py:69`) |
| 4 | `update_session` | `session_id`, `now`, 그리고 `slots` / `last_question_slot_id` / `participant_id` 중 **명시된 것만** | `SessionView` | `NOT_FOUND`, `EXPIRED`, `CONFLICT`, `CORRUPT` | 예 | R1 준수 — 부분 갱신. 인자로 주지 않은 필드는 건드리지 않는다. `last_activity_at` 을 `now` 로 갱신 |
| 5 | `consume_turn` | `session_id`, `now`, `max_turns` | `TurnGrant` | `NOT_FOUND`, `EXPIRED`, `CONFLICT`, `CORRUPT` | **아니오** | §5. 캡 판정과 증가가 한 `UPDATE` (R2) |
| 6 | `release_turn` | `session_id`, `turn_no` | `released: bool` | `NOT_FOUND`, `CONFLICT`, `CORRUPT` | 예 | §5 의 보상 연산. `turn_no` 가 현재값과 다르면 `Ok(False)` (무동작) |
| 7 | `append_conversation_turn` | `session_id`, `role`, `text`, `participant_id`, `exclude_from_context: bool`, `now` | **`TurnKey`** ★ | `NOT_FOUND`, `EXPIRED`, `CONFLICT`, `CORRUPT` | **아니오** | §6 임계 구역. **실제로 기록한 `(day, seq)` 를 반환한다** — Phase 3 §5.2 의 구속 규정 |
| 8 | `restore_history` | `session_id`, `now` | `list[{role, content}]` | `NOT_FOUND`, `EXPIRED`, `CONFLICT`, `CORRUPT` | 예 | Phase 3 §5 알고리즘을 스토어 연산으로 승격. `turn_partitions` 로 열 파일을 확정 — 디렉터리 스캔 없음. **읽기 경로지만 `CONFLICT` 가 가능하다** — §1.2 의 TTL 판정이 삭제(쓰기)를 수반하므로 그 구간에서 `SQLITE_BUSY` 가 날 수 있다. 파일 잘라내기(§6.5 국면 ①)는 인덱스를 고치지 않으므로 이 외의 쓰기는 없다 |
| 9 | `expire_session` | `session_id` | `deleted: bool` | `CONFLICT`, `CORRUPT` | 예 | 명시적 만료(테스트·이행용). 없으면 `Ok(False)` |
| 10 | `sweep_expired` | `now`, `limit` | `deleted_count: int` | `CONFLICT`, `CORRUPT` | 예 | D03 의 일괄 sweep. **`limit` 필수** — 임계 구역 길이 상한을 위해(§6.3) |
| 11 | `check_rate` | `ip`, `session_id`, `now`, `max_per_window`, `daily_cap` | `RateVerdict` | `CONFLICT`, `CORRUPT` | **아니오** | D04. 확인·판정·증가가 한 트랜잭션(§7.3) |

**멱등 열의 용도**: `CONFLICT` 는 유일하게 "그대로 다시 부르면 될 수도 있는" 오류인데,
5·7·11 은 재시도가 **중복 소비**를 낳으므로 재시도 대상이 아니다. 이 열이 없으면
"`CONFLICT` 면 재시도"라는 자연스러운 오독이 턴 이중 소비·턴 이중 기록을 만든다.

**`MAX_TURNS` 는 스토어의 상수가 아니다.** `max_turns`(5) / `max_per_window`·`daily_cap`(11)은
전부 인자다. 정책 상수는 `app/chat.py:15`(`MAX_TURNS = 10`)와 `app/config.py` 쪽에 남고,
스토어는 정책을 모른 채 원자성만 제공한다.

---

## 2. `ChatSession` 저장 배치

### 2.1 먼저 — 키와 값 필드를 구분한다

`ChatSession`(`app/chat.py:46-54`)의 속성은 **7개**다. 그중 `session_id`(`:48`)는
`_sessions` dict 의 **키**이자 API 요청의 식별자이고(`app/main.py:21`), 나머지 **6개가 값
필드**다. 이 문서의 배치표가 6행인 것은 필드를 하나 빠뜨려서가 아니라 `session_id` 가 값이
아니라 **스토어 키**이기 때문이다 — Phase 1 §3 이 이미 같은 판독을 기록했다.

| 항목 | 역할 | 스토어에서의 위치 |
|------|------|-------------------|
| `session_id` | **키** (값 필드 아님) | `sessions.session_id` — PRIMARY KEY. 값이 아니라 좌표다 |

### 2.2 여섯 값 필드의 저장 배치 (CAP11)

| # | 필드 | 근거 | 저장 위치 | 형태 | 선택 이유 |
|---|------|------|-----------|------|-----------|
| 1 | `session_token` | `app/chat.py:49` | **`session_auth.session_token` 컬럼** (별도 테이블) | `TEXT NOT NULL` | 인증 필드 고립(§7.4) — 장래 인증 체계 도입 시 이 테이블만 교체·확장한다. `sessions` 테이블은 토큰을 갖지 않는다 |
| 2 | `turns` | `app/chat.py:50` | `sessions.turns` 컬럼 | `INTEGER NOT NULL DEFAULT 0` | 원자적 증가(§5)의 대상이므로 반드시 **독립 컬럼**이어야 한다. JSON 안에 넣으면 `UPDATE ... SET turns = turns + 1` 이 불가능해지고 R2 가 깨진다 |
| 3 | `history` | `app/chat.py:51` | **미저장** | — | D02 확정(Phase 2 §D02, Phase 3 §1). 대화 원문 사본을 늘리지 않는다. **복원 경로**: `restore_history`(§1.5 #8) → [Phase 3 §5 복원 알고리즘](./03-history-restore.md#5-복원-알고리즘-통합). 원본은 `data/conversations/{day}/{session_id}.json` |
| 4 | `slots` | `app/chat.py:52` | `sessions.slots` 컬럼 — **JSON 직렬화** | `TEXT NOT NULL DEFAULT '{}'` | `dict[str,str]`, 항상 통째로 읽고 쓰며 슬롯 키 단위로 질의하지 않는다(라우팅·패널·요약이 전량을 본다). 자식 테이블은 조인 비용만 늘린다. **대가**: SQL 로 슬롯 단위 질의가 불가능하다 — 필요해지면 자식 테이블로 승격한다 |
| 5 | `last_question_slot_id` | `app/chat.py:53` | `sessions.last_question_slot_id` 컬럼 | `TEXT NULL` | `str \| None` 단일 값. `slots` JSON 안에 섞으면 "슬롯 값"과 "직전 질문 대상"이 같은 이름 공간에 놓여 충돌한다 — `NULL` 이 의미를 갖는 독립 컬럼으로 둔다 |
| 6 | `participant_id` | `app/chat.py:54` | `sessions.participant_id` 컬럼 | `TEXT NULL` | 최초 요청에서만 설정되고(`app/chat.py:354-355`) 이후 불변. 가명화 로컬 ID 이며 `valid_participant_id`(`app/storage.py:24-26`) 형식만 허용한다 |

`history`(3행)와 `last_question_slot_id`(5행)는 CAP11 이 "조용히 빠뜨릴 것"으로 지목한 두
필드다. 둘 다 위 표에 **자기 행**을 갖고, `history` 행은 복원 경로를 참조로 갖는다.

### 2.3 스토어가 추가로 갖는 세 항목

값 필드 6개 밖에 스토어만 아는 항목이 셋이다. 셋 다 **발화 텍스트를 한 글자도 담지 않는다.**

| 항목 | 형태 | 출처 | 왜 필요한가 |
|------|------|------|-------------|
| `turn_partitions` | `TEXT` (JSON `{day: count}`) | Phase 3 §2.4 `turn_days` 를 §1.4 에서 좁힘 | 복원 시 열 파일을 스캔 없이 확정(Phase 3 §3.3) + §6.4 의 매체 불일치 방어(§6.5 의 두 국면) |
| `context_excluded` | `TEXT` (JSON `[[day, seq], ...]`) | Phase 3 §2.4 해소안 (다) | 차단된 `user` 턴이 복원으로 모델 컨텍스트에 되살아나는 것을 막는다 — Phase 3 의 1차 정확성 의무 |
| `last_activity_at` | `TEXT` (ISO 8601 UTC) | **D03** | 24시간 TTL 판정 기준. D03 이 "마지막 활동 기준"을 확정했으므로 이 필드 없이는 D03 이 구현 불가능하다 |

`last_activity_at` 은 Phase 3 의 추가 2항목 목록에 없던 것이므로 여기서 명시적으로 추가를
선언한다. D02 의 "최소 상태" 서술은 §2.3 만큼 확장되며, 그 긴장은 Phase 3 §2.4 가 이미
기록한 것과 같은 성격이다 — **실질(개인정보 표면)이 아니라 명목(항목 수)** 의 확장이다.

---

## 3. 기존 4개 공개 함수의 처리 방침 (CAP36)

호출부를 먼저 실측했다. 네 함수의 **외부 호출부는 `app/main.py` 세 줄이 전부**이고,
`_get_session` 은 `app/chat.py` 안에서만 한 번 불린다.

| 함수 | 정의 | 방침 | 무엇이 되는가 | 실측 호출부 |
|------|------|------|----------------|-------------|
| `has_session` | `app/chat.py:60` | **폐기** | `open_session` 의 `created` 플래그에 흡수된다. "존재 확인"이라는 **독립 왕복 자체가 사라진다** — 배경이 지목한 3회 왕복의 첫 번째가 여기다 | `app/main.py:43` (외부 유일) |
| `owns_session` | `app/chat.py:64` | **대체** | `verify_owner(session_id, token, now)`. 오늘 `False` 한 값으로 뭉개지던 "세션 없음"과 "토큰 불일치"를 `Err(NOT_FOUND)` / `Ok(False)` 로 **분리**한다. `secrets.compare_digest` 상수시간 비교는 그대로 유지(`app/chat.py:69`) | `app/main.py:45` (외부 유일) |
| `session_token` | `app/chat.py:73` | **폐기** | `open_session` 반환값 `SessionView.session_token` 에 흡수된다. 세 번째 왕복이 사라지고, 이 흡수가 §4 의 승자 토큰 성질을 만든다 | `app/main.py:59` (외부 유일) |
| `_get_session` | `app/chat.py:78` | **대체** | `open_session(session_id, now)`. 오늘 `:79` 조회 → `:81` 생성 → `:82` 등록의 세 단계가 **하나의 트랜잭션**이 된다 | `app/chat.py:353` (모듈 내부 유일) |

**폐기 2 / 대체 2.** 네 함수 모두 최종적으로 `app/chat.py` 에서 사라지고, `app/main.py` 의
세 줄이 두 줄로 줄어든다(`open_session` 1회 + `verify_owner` 1회). 구체 이행 절차와 단계별
회귀 방어는 Phase 6 이 받는다.

**이 표에 없는 이행 비용**: `_sessions` 직접 접근 **37곳 / 13파일**(Phase 1 §2)은 위 네 함수를
거치지 않고 dict 를 직접 만진다. 그 이행은 이 인터페이스의 설계 사항이 아니라 **Phase 6 의
이행 절차**다. 다만 형태만 여기서 못박는다 — 테스트가 `chat._sessions[id].slots` 로 읽던 것은
`store.get_session(id, now)` 의 `SessionView.slots` 로, `chat._sessions.pop(id, None)` 은
`store.expire_session(id)` 로 대응된다(그래서 §1.5 에 #9 가 있다).

---

## 4. 생성의 멱등성·원자성 — TOCTOU 를 닫는다

### 4.1 오늘 열려 있는 창

```
app/main.py:43   session_was_known = chat.has_session(session_id)      ← 왕복 1 (읽기)
app/main.py:57   result = chat.handle_message(...)                     ← 왕복 2 (내부 _get_session 이 생성)
app/main.py:59   result["session_token"] = chat.session_token(...)     ← 왕복 3 (읽기)
```

두 워커가 같은 `session_id` 로 동시에 첫 요청을 받으면, 둘 다 왕복 1 에서 "모르는 세션"을
보고 각자 왕복 2 에서 **서로 다른 `ChatSession` 을 각자의 프로세스 dict 에 만든다**. 각
클라이언트는 자기 워커가 만든 토큰을 받는데, 그 토큰을 아는 행은 다른 워커에 존재하지 않는다 —
이후 요청이 반대 워커로 가면 `owns_session` 이 영구히 거부한다. **영구 401** 이다.

### 4.2 세 시맨틱 중 택일

| 후보 | 동작 | 판정 |
|------|------|------|
| **덮어쓰기** (`INSERT OR REPLACE`) | 나중 워커가 앞선 행을 덮어쓴다 | **기각.** 앞 워커의 클라이언트가 쥔 토큰이 그 순간 무효가 된다 — 메모리 dict 시절의 영구 401 을 스토어 안으로 그대로 옮기는 셈이다. 게다가 이미 쌓인 `turns`/`slots` 가 소실된다 |
| **`INSERT OR IGNORE` 단독** | 충돌 시 무시 | **불충분.** 원자성은 얻지만, 호출부가 *방금 만든* 토큰을 그대로 반환하면 `INSERT` 가 무시된 경우 **패자의 토큰**을 돌려준다. 원자적인데도 영구 401 이 남는다 |
| **단일 트랜잭션 내 조회-생성 통합 — 채택** | `BEGIN IMMEDIATE` 안에서 조회·만료정리·생성·**재조회**를 모두 수행하고 그 결과를 반환 | **채택.** 아래 §4.3 |

### 4.3 채택 시맨틱

```
open_session(session_id, now) -> Ok((view, created))

  BEGIN IMMEDIATE                      # 쓰기 락을 시작 시점에 확보 — 읽기→쓰기 승격 교착을 없앤다
    row ← SELECT ... FROM sessions WHERE session_id = ?

    if row 있음 and now - row.last_activity_at > TTL_24H:      # D03 lazy sweep
        DELETE FROM sessions     WHERE session_id = ?
        DELETE FROM session_auth WHERE session_id = ?
        row ← 없음

    if row 없음:
        INSERT OR IGNORE INTO sessions(session_id, turns, slots, ...,
                                       turn_partitions, context_excluded, last_activity_at)
               VALUES (?, 0, '{}', NULL, NULL, '{}', '[]', now)
        INSERT OR IGNORE INTO session_auth(session_id, session_token, issued_at)
               VALUES (?, <새 토큰>, now)
        created ← (INSERT 가 실제로 행을 넣었는가)
    else:
        UPDATE sessions SET last_activity_at = now WHERE session_id = ?
        created ← False

    row  ← SELECT ... FROM sessions     WHERE session_id = ?    # ★ 재조회
    auth ← SELECT ... FROM session_auth WHERE session_id = ?    # ★ 재조회
  COMMIT

  return (SessionView(row, auth.session_token), created)
```

**왜 `BEGIN IMMEDIATE` 인가.** D01 이 확정한 SQLite 는 한 시점에 커밋 가능한 writer 가 1개다.
`IMMEDIATE` 는 트랜잭션 시작 즉시 그 writer 자리를 잡으므로, 조회부터 생성까지가 하나의
직렬화 단위가 된다. 기본 `DEFERRED` 로 두면 조회는 읽기 락으로 시작했다가 생성 시점에
쓰기로 **승격**해야 하고, 두 트랜잭션이 동시에 승격을 시도하면 한쪽이 `SQLITE_BUSY` 로
죽는다 — TOCTOU 를 없애려다 새 실패 모드를 만드는 셈이다.

**왜 `INSERT OR IGNORE` 와 재조회를 함께 쓰는가.** `IMMEDIATE` 만으로도 이 구간은 직렬화된다.
그럼에도 둘을 함께 두는 이유는 **승자 토큰 성질이 트랜잭션 모드 설정 하나에 의존하지 않게**
하기 위해서다. 재조회를 생략하고 방금 만든 토큰을 그대로 반환하면, `INSERT` 가 무시된 경우
호출부는 테이블에 없는 토큰을 클라이언트에게 발급한다 — §4.1 이 지목한 영구 401 의 정확한
발생 지점이 바로 거기다.

### 4.4 토큰 발급이 항상 승자의 토큰을 반환함 (`app/main.py:59`)

> **성질 P1 (승자 토큰).** `open_session` 이 반환하는 `SessionView.session_token` 은 항상
> 그 시점 `session_auth` 테이블에 **실재하는 행**의 값이다.

증명 요지: 토큰은 `COMMIT` 직전 재조회(§4.3 ★)의 결과에서만 나온다. 그 `SELECT` 는 같은
트랜잭션 안에서 실행되므로 다른 워커의 개입이 불가능하고, 반환된 행은 정의상 테이블에 있다.
따라서 **테이블에 없는 행의 토큰이 클라이언트에게 나가는 경로가 존재하지 않는다.**
§4.1 의 영구 401 은 "고쳐진" 것이 아니라 **발생 가능한 상태 자체가 사라진다.**
(형식 논증은 Phase 5.)

**토큰 응답 규정.** `app/main.py:58-59` 의 대응 규칙을 다음으로 못박는다.

| 상황 | `open_session` 결과 | 요청이 제시한 토큰 | 응답 |
|------|---------------------|--------------------|------|
| 신규 세션 | `created = True` | (없음) | 200 + `session_token` 동봉 |
| 기존 세션, 올바른 토큰 | `created = False` | 일치 | 200, 토큰 미동봉(이미 갖고 있다) |
| 기존 세션, 토큰 없음/불일치 | `created = False` | 없음 또는 불일치 | **401 `"세션 인증이 필요합니다."`** |

**대가를 정직하게 적는다.** 같은 클라이언트가 첫 요청을 **중복 전송**해 두 워커에 동시에
도달하면, 이긴 요청은 200+토큰을, 진 요청은 401 을 받는다. 오늘(단일 워커)은 왕복 1 의 stale
read 때문에 **양쪽 모두 같은 토큰을 받는다** — 그 점에서 이것은 동작 변화다.

그럼에도 이 규정을 택하는 이유: 오늘의 그 동작은 **토큰 유출 경합**이기도 하다. `session_id`
는 클라이언트가 정하는 값이라(`app/main.py:21`) 추측·열거가 가능한데, 공격자가 토큰 없는
요청을 정확히 생성 순간에 끼워 넣으면 왕복 1 에서 `has_session()==False` 를 얻어 왕복 3 에서
**피해자 세션의 토큰**을 받는다. 새 규정은 그 창을 닫는다. 중복 전송의 대가는 401 이라는
**소리 나는 실패**이고 클라이언트는 새 세션으로 복구할 수 있는 반면, 유출은 조용하다.

---

## 5. 10턴 캡의 경합

### 5.1 오늘의 read-modify-write

`session.turns` 는 세 곳에서 증가하고(`app/chat.py:325`, `:408`, `:503`) 세 곳에서 판정된다
(`:328`, `:358`, `:505`). 문제는 판정과 증가의 **거리**다 — `handle_message` 진입부 `:358`
에서 `session.turns >= MAX_TURNS` 를 확인하고, 증가는 LLM 호출을 지나 `:503` 에서 일어난다.

워커가 여럿이면 둘 다 `turns == 9` 를 읽고 둘 다 `:358` 을 통과한 뒤 각자 증가시켜 `11` 이
된다. 오늘은 dict 가 프로세스마다 따로라 **캡 자체가 워커마다 따로 논다**(`Dockerfile:25-29`
가 `--workers 1` 고정 사유로 이걸 지목한다). 스토어를 공유해도 R2 를 지키지 않으면 이
check-then-act 창은 그대로 남는다.

### 5.2 채택 — 소비 후 보상 (`consume_turn` / `release_turn`)

```
consume_turn(session_id, now, max_turns) -> Ok(TurnGrant)

  BEGIN IMMEDIATE
    UPDATE sessions
       SET turns = turns + 1, last_activity_at = <now>
     WHERE session_id = ? AND turns < <max_turns>          # ← 판정이 WHERE 절 (R2)
    if 영향 행 수 == 0:
        (레코드 존재 여부·만료 여부를 확인해 NOT_FOUND / EXPIRED 를 구분하고,
         레코드가 살아있는데 0 이면) → Ok(TurnGrant(turns, limit_reached=True))
    else:
        turn_no ← SELECT turns FROM sessions WHERE session_id = ?
  COMMIT
  return Ok(TurnGrant(turn_no, limit_reached=False))
```

판정과 증가가 **한 `UPDATE`** 이므로 두 워커가 동시에 `turns == 9` 에서 출발해도 `WHERE turns
< 10` 을 만족시키는 쪽은 하나뿐이다. 진 쪽은 영향 행 수 0 을 받아 `limit_reached=True` 로
`LIMIT_MESSAGE`(`app/chat.py:17`) 경로를 탄다.

> **불변식 후보 (Phase 5 인계)**: 어떤 워커 수에서도 `sessions.turns ≤ max_turns` 이고,
> `limit_reached=False` 인 `consume_turn` 성공 횟수는 세션당 정확히 `max_turns` 회다.

### 5.3 보상 연산이 필요한 이유

소비를 **진입부로 옮기면** 오늘과 달라지는 것이 하나 있다: LLM 호출이 실패해도 턴이 소모된다
(오늘은 증가가 `:503` 이라 실패하면 소모되지 않는다). 상담 도메인에서 10턴 예산 중 1턴이
오류로 날아가는 것은 사용자에게 그대로 체감된다.

그래서 짝을 이루는 보상 연산을 둔다.

```
release_turn(session_id, turn_no) -> Ok(released)

  UPDATE sessions SET turns = turns - 1
   WHERE session_id = ? AND turns = <turn_no>     # ← 그 사이 아무도 전진하지 않았을 때만
  return Ok(영향 행 수 == 1)
```

`turns = <turn_no>` 가드가 있으므로, 다른 워커가 이미 다음 턴을 소비했다면 되돌림은
**무동작**(`Ok(False)`)이 되고 턴은 소모된 채 남는다. 이는 잔여 손실이며 스스로 한정된다 —
되돌림이 실패하려면 같은 세션에 다른 요청이 실제로 진행 중이어야 한다.

**기각한 대안**: 판정은 진입부에서 낙관적으로 하고 증가는 오늘처럼 말미에 원자적으로 하는
안. 오늘 동작을 그대로 보존하지만, 두 워커가 동시에 `turns == 9` 를 통과하면 **응답 두 개가
생성된 뒤** 증가 하나만 성공한다 — `turns` 는 10 을 넘지 않지만 **11번째 응답이 이미 사용자에게
나간 뒤**다. 캡의 목적이 응답 수 제한이므로 이 잔여는 캡을 실질적으로 무력화한다.

---

## 6. 대화 JSON 쓰기 임계 구역 (D05)

D05 는 "JSON 포맷 유지 + 쓰기를 세션 스토어 트랜잭션/락으로 직렬화"를 확정하고, 임계 구역의
구체 설계를 이 페이즈로 넘겼다. **SQLite 트랜잭션이 별도 매체(파일)의 쓰기를 감싸는 구조**를
연산으로 정의한다.

### 6.1 "대화 쓰기 락"의 정의 — 새 테이블을 두지 않는다

임계 구역 범위(세션별 vs 스토어 전역)를 Phase 3 §5.3 이 이 페이즈로 넘겼다.

> **결정: 스토어 전역 락 — 그 락은 `BEGIN IMMEDIATE` 쓰기 트랜잭션 그 자체다.
> 별도의 락 테이블을 만들지 않는다.**

근거:

- SQLite 는 어차피 한 시점 writer 가 1개다(D01 의 "대가와 한계"). 세션별 락 테이블을 만들어도
  **실제 병렬성은 늘지 않는다** — 락 획득 자체가 쓰기라 같은 단일 writer 를 두고 경합한다.
- 락 테이블은 **해제 누락**이라는 새 실패 모드를 만든다. 워커가 락을 쥔 채 죽으면 스텁 락이
  남고, 그걸 청소할 타임아웃·소유자 추적 메커니즘이 또 필요하다. 트랜잭션은 프로세스가 죽으면
  SQLite 가 자동으로 롤백한다 — 청소 메커니즘이 공짜다.
- "새 동시성 프리미티브를 도입하지 않고 기존 트랜잭션 경계를 재사용한다"는 D05 의 근거와
  정확히 일치한다.

**대가**: 임계 구역이 전역이므로 **한 세션의 파일 I/O 가 다른 세션의 쓰기까지 막는다.**
D05 가 "락 보유 중 파일 I/O 라 임계 구역이 길어진다"고 지목한 비용이 전역으로 퍼진다.
그래서 길이를 §6.3 에서 **설계로 통제한다.**

### 6.2 임계 구역의 경계와 순서

```
append_conversation_turn(session_id, role, text, participant_id,
                         exclude_from_context, now) -> Ok(TurnKey)

  ┌─ BEGIN IMMEDIATE ───────────────────────────────── 임계 구역 시작 ─┐
  │ 1. 세션 레코드 조회 + TTL 판정                                      │
  │      없음 → Err(NOT_FOUND) / 만료 → 삭제 후 Err(EXPIRED)            │
  │                                                                     │
  │ 2. 대상 파일 read           data/conversations/{now.date}/{sid}.json│
  │      day       ← now.date().isoformat()   ← now 는 인자다. 재평가 없음│
  │      payload   ← normalize_conversation_payload(raw, ...)(storage.py:39)
  │      actual    ← len(payload["turns"])       # 파일이 실제로 담은 개수 │
  │      committed ← turn_partitions.get(day, 0) # 인덱스가 인정한 개수    │
  │                                                                     │
  │ 2'. 미커밋 꼬리 조정 (reconciliation) — §6.5 국면 ②                   │
  │      if actual < committed:  → Err(CORRUPT)   # 있어야 할 턴이 없다    │
  │      orphans ← [(day, s) for s in range(committed, actual)]          │
  │      # orphans = 파일에는 있으나 인덱스가 모르는 턴. 등재 여부를 알 수 │
  │      #          없으므로 전부 제외로 확정한다 (fail-closed)           │
  │                                                                     │
  │ 3. 좌표 확정 + 인덱스 UPDATE (SQLite)                                │
  │      committed' ← committed + len(orphans)   # 조정 후 인정 개수      │
  │      seq ← committed'                                               │
  │        ★ seq 는 파일 길이가 아니라 인덱스가 "커밋을 인정한 개수"에서   │
  │          나온다. 미커밋 꼬리는 등재를 거치지 않고는 이 값에 기여할 수  │
  │          없다 — 이것이 흡수(§6.5)를 막는 지점이다                     │
  │      context_excluded += orphans                                    │
  │      if exclude_from_context: context_excluded += [(day, seq)]      │
  │      turn_partitions[day] ← seq + 1                                 │
  │      last_activity_at ← now                                         │
  │                                                                     │
  │ 4. 파일 원자적 교체 (seq 위치에 append — 꼬리는 보존한다)             │
  │      tmp 에 write(encoding="utf-8", ensure_ascii=False) → os.replace │
  │                                                                     │
  │ 5. COMMIT                                                           │
  └───────────────────────────────────────────── 임계 구역 끝 ─────────┘

  return Ok(TurnKey(day, seq))        ★ 실제로 기록한 키를 반환한다
```

고아가 없는 정상 경로에서는 `orphans` 가 비어 `committed' = committed = actual` 이므로
단계 2'·3 은 아무 일도 하지 않는다 — 조정은 §6.4 의 잔여 창이 실제로 발생했을 때만 작동하는
경로이며, 정상 append 의 비용을 늘리지 않는다.

**반환값은 선택 사항이 아니다.** Phase 3 §5.2 는 인덱스 키를 호출부가 `date.today()` /
`len(turns)` 로 **재계산하는 것을 금지**했다. 오늘 `app/storage.py:71-77` 은 `-> None` 이고
키의 두 성분을 `:84`(`date.today()`)와 `:91`(`len(turns)`)에서 내부 계산하므로, 호출부는 자기가
방금 저장한 턴의 좌표를 알 수 없다. 이 연산은 그 좌표를 **반환한다.**

여기에 더해, 이 설계는 키를 **호출부에 맡기지도 않는다** — `exclude_from_context` 플래그를
받아 인덱스 갱신(3)을 스토어가 **같은 임계 구역 안에서** 직접 수행한다. 반환된 `TurnKey` 는
호출부의 로깅·인계용이며, 인덱스 정합성은 호출부의 행동에 의존하지 않는다. Phase 3 의 구속
규정을 만족시키는 가장 강한 형태다.

**`exclude_from_context` 를 호출 지점별로 확정한다** (Phase 3 §5.2 는 `user` 턴 3곳만 키가
필요하다고 실측했다):

| 호출 지점 | role | `exclude_from_context` | 근거 |
|-----------|------|------------------------|------|
| `app/chat.py:320` | `user` | `not include_user_in_model_context` | `:322-323` 이 그 플래그일 때만 history 에 넣는다 |
| `app/chat.py:405` | `user` | **`True`** | 인젝션 차단 분기(`:373`). `:407` 은 `assistant` 만 history 에 넣는다 |
| `app/chat.py:498` | `user` | `False` | 정상 경로. `:501` 이 history 에 넣는다 |
| `:321`, `:406`, `:499` | `assistant` | `False` | `assistant` 는 어느 경로에서도 항상 history 에 들어간다(`:324`, `:407`, `:502`) |
| `:330`, `:510`, `:525` | `intake_summary` | `False` (무의미) | Phase 3 §4 의 role 화이트리스트가 복원 단계에서 이미 거른다 |

### 6.3 임계 구역 길이의 통제

| 규칙 | 내용 |
|------|------|
| **허용** | 대상 세션 파일 **1개**의 read, JSON 파싱·직렬화, 임시 파일 write + `os.replace`, 같은 세션 행의 `UPDATE` |
| **금지** | LLM 호출, 네트워크 I/O, 지식 검색, 다른 세션 파일 접근, `data/conversations/*` 디렉터리 전수 스캔, 무제한 `sweep_expired` |
| **상한** | 세션당 저장 턴 ≤ 20(요청 턴 10 × user/assistant), 사용자 메시지 ≤ 2000자(`app/main.py:12`), 모델 출력 ≤ 12,000자(`app/llm.py:81` `MAX_MODEL_OUTPUT_CHARS`, `app/chat.py:16` 이 재사용). 따라서 파일 크기는 **세션 수·운영 일수와 무관한 상수 상한**을 갖고, 임계 구역 길이도 그렇다 |
| **대기 상한** | `PRAGMA busy_timeout = 5000` (5초). 임계 구역이 파일 I/O 1건 + `UPDATE` 몇 개라 밀리초 단위이므로 5초는 정상 부하에서 도달할 수 없는 값이다 — 도달하면 그 자체가 이상 신호이며 `Err(CONFLICT)` 로 표면화한다 |
| **sweep 분리** | `sweep_expired(now, limit)` 의 `limit` 이 필수인 이유가 이것이다. 만료 레코드가 수천 건 쌓인 상태에서 무제한 sweep 이 임계 구역에 들어오면 위 상수 상한이 깨진다 |

`os.replace` 를 쓰는 이유: 오늘 `app/storage.py:92` 는 `path.write_text(...)` 로 **직접** 쓴다 —
쓰기 도중 크래시하면 파일이 잘린다. 같은 리포의 `app/ratelimit.py:85-88` 은 이미 임시 파일 +
`os.replace` 원자적 교체 관례를 갖고 있고 3-OS CI 로 검증돼 있다. 이 연산은 그 관례를 따른다.

### 6.4 롤백 시맨틱 — 두 매체는 원자적으로 묶이지 않는다

SQLite 트랜잭션은 파일시스템 쓰기를 롤백하지 못한다. 그래서 **어느 방향의 불일치가 남는지**를
설계로 고정한다.

| 실패 지점 | 대화 파일 | 인덱스 | 복원에 미치는 영향 | 판정 |
|-----------|-----------|--------|---------------------|------|
| 1 (레코드 조회) | 변화 없음 | ROLLBACK | 없음 | 안전 |
| 2 (파일 read) | 변화 없음 | ROLLBACK | 없음 | 안전 |
| 3 (인덱스 UPDATE) | 변화 없음 | ROLLBACK | 없음 | 안전 |
| 4 (tmp write 또는 `os.replace`) | **원본 그대로** — `os.replace` 는 원자적이라 중간 상태가 없다 | ROLLBACK | 없음 | 안전 |
| **5 (COMMIT 실패 / 프로세스 크래시)** | **새 턴 포함 (N+1개)** | 옛 상태 (`turn_partitions[day] = N`) | **두 국면 모두 §6.5 가 닫는다** — ① 다음 append 전의 복원: `seq ≥ N` 인 꼬리를 **버린다**. ② 다음 append: 단계 2' 가 그 꼬리를 `context_excluded` 에 **등재하면서** 수용 범위로 승격시킨다 | **안전 (양 국면)** — 충실도만 손실 |

**잔여 창은 5 하나뿐이고, 방향이 하나로 고정된다**: 파일이 인덱스보다 **앞선다**. 반대 방향
(인덱스가 파일보다 앞섬)은 4 가 원자적이므로 발생하지 않는다.

**5행의 판정은 두 국면을 모두 논증해야 성립한다.** 잔여 창이 남긴 고아 턴은 다음 append 가
올 때까지만 "인덱스 밖"에 있다. 국면 ①(잘라내기)만 설계하고 국면 ②를 빠뜨리면, 다음 append
가 고아를 수용 범위 안으로 **흡수**해 이 행의 "안전" 판정이 **그 시점부터 거짓이 된다.**
§6.5 가 두 국면을 각각 정의하는 이유가 이것이다.

### 6.5 앞선 파일을 닫는 두 국면 — 읽기의 잘라내기 + 쓰기의 등재

`turn_partitions` 가 날짜 → **턴 수** 사상인 이유가 여기다(§1.4). §6.4 의 잔여 창이 남긴
**고아 턴**(파일에는 있고 인덱스는 모르는 턴)은 서로 다른 두 국면에서 처리된다.
**한 국면만 설계하면 다른 국면에서 구멍이 난다** — 아래 국면 ②가 그 구멍이다.

#### 국면 ① — 읽기(복원). 아직 다음 append 가 없다

```
복원 시 (Phase 3 §5 알고리즘 2단계에 추가되는 규칙)
  for day, expected_count in record.turn_partitions:
      turns ← 파일에서 읽은 턴들
      if len(turns) > expected_count:
          turns ← turns[:expected_count]      # ← 커밋되지 않은 꼬리를 버린다
      if len(turns) < expected_count:
          → Err(CORRUPT)                      # ← 있어야 할 턴이 없다. 외부 변조·유실
```

인덱스에 커밋되지 못한 꼬리 턴은 그 `context_excluded` 등재 여부를 **알 수 없는** 턴이고,
알 수 없는 턴을 모델 컨텍스트에 넣지 않는 것이 안전한 기본값이다.

복원은 **읽기 경로**이므로 인덱스를 고치지 않는다. 고치려면 쓰기 트랜잭션이 필요해 복원마다
단일 writer 를 점유하게 되고, §6.3 의 임계 구역 규율이 읽기 경로로 번진다. 따라서 잘라내기는
**그 호출 안에서만 유효한 방어**이며 인덱스는 그대로 남는다 — 이 사실이 국면 ②를 필수로
만든다.

#### 국면 ② — 쓰기(다음 append). 여기서 고아가 영구히 확정된다

국면 ①만 두고 `seq` 를 **파일 길이**에서 뽑으면 다음과 같이 무너진다.

```
시작:   파일 N턴,  turn_partitions[day] = N,  고아 없음

요청 A: seq ← N → 파일 N+1턴으로 교체 → COMMIT 실패(인덱스 롤백)
        결과: 파일 N+1 / 인덱스 N / context_excluded 에 (day, N) 없음
        이 시점 복원: N+1 > N → turns[:N] → 고아 버려짐            ✅ 안전

요청 B: seq ← len(file) = N+1   ← 고아가 좌표 계산에 끼어든다
        → turn_partitions[day] = N+2, COMMIT 성공
        이 시점 복원: len=N+2, expected=N+2 → 잘라내기 미발동
        인덱스 N 위치의 고아가 수용 범위 안에 있고 등재는 없다    ❌ 부활
```

마지막 줄이 차단된 인젝션 `user` 턴을 모델 컨텍스트로 되돌린다 — Phase 3 의 1차 정확성 의무
위반이다. 그래서 §6.2 단계 2'·3 이 `seq` 를 **파일 길이가 아니라 조정 후 커밋 개수**에서
뽑고, `[committed, actual)` 구간의 고아를 **같은 트랜잭션에서 `context_excluded` 에 등재한
뒤에만** 수용 범위로 승격시킨다.

#### 꼬리 처리 방향 — (B) 를 택한다

| 안 | 방법 | 이득 | 대가 |
|----|------|------|------|
| (A) 꼬리를 **버린다** | append 시점에 파일을 `turn_partitions[day]` 길이로 잘라낸 뒤 이어 쓴다 | 가장 단순하다. `seq` 가 언제나 커밋 개수와 같고 좌표 공간에 구멍이 없다. 인덱스가 커지지 않는다 | **감사 기록이 사라진다.** 그 턴이 차단된 인젝션 시도였다면, 남겨야 할 보안 흔적을 시스템이 스스로 지운다. 대화 JSON 에 대한 쓰기가 append 가 아니라 **파괴적 쓰기**가 되어 잘라내기 도중의 크래시가 더 큰 손실을 만든다 |
| **(B) 보존 + 등재 — 채택** | 꼬리를 파일에 그대로 두고, **같은 트랜잭션에서** `context_excluded` 에 등재하며 커밋 범위로 승격한다 | 감사 기록(대화 JSON)과 안전 경계(제외 집합)를 **둘 다** 지킨다. 대화 JSON 은 계속 append-only 로 다뤄진다 | `context_excluded` 가 크래시당 최대 1~2 원소 커진다(세션당 저장 턴 ≤ 20 이라 상수로 묶인다). 고아가 정상 발화였다면 그 턴만큼 컨텍스트 충실도가 준다 |

**(A) 를 버려서 잃은 것**: 단순함. (A) 면 `seq = turn_partitions[day]` 가 무조건 성립해 조정
개념 자체가 필요 없고, 국면 ①·②를 나눠 논증할 일도 없다.
**버린 이유**: 이 문서와 Phase 3 §0 은 "저장 계층은 **무슨 일이 있었나**를 기록하고 `history`
는 **모델에게 무엇을 보여줄까**를 담는다. 후자는 전자의 부분집합이며 그 차집합이 곧 안전
경계다"를 규정한다. (A) 는 안전 경계를 지키려고 **전자(감사 기록)를 지운다** — 이 task 가
지키기로 한 두 성질 중 하나를 다른 하나로 갚는 것이다. (B) 는 고아를 차집합 쪽으로 옮길 뿐
전자를 건드리지 않으므로, 같은 안전성을 **갚지 않고** 얻는다.

#### `seq` 공간에 구멍도 중복도 없다

조정 후 `committed' = committed + len(orphans) = actual` 이므로 새 턴은 항상 **파일의 끝**에
붙는다. 따라서 한 날짜 파일 안의 `seq` 는 `0, 1, …, actual` 로 조밀하다.

- **중복 없음**: 고아를 덮어쓰지 않는다(덮어쓰는 것이 (A) 다). 새 턴의 `seq` 는 언제나 기존
  최대 `seq` + 1 이다.
- **구멍 없음**: 고아 구간은 `context_excluded` 로 **분류만** 바뀔 뿐 파일에서 사라지지
  않으므로 좌표가 비지 않는다.
- Phase 3 §3.2 의 전역 순서 `(day, seq)` 튜플 비교는 그대로 성립한다.

#### 불변식 후보 (Phase 5 인계) — 꼬리 폐쇄성

> 어느 시점에 복원하더라도, `context_excluded` 에 등재되지 않은 채 수용 범위
> (`seq < turn_partitions[day]`) 안에 있는 턴은 존재하지 않는다.

논증 골자: 턴이 수용 범위로 들어오는 경로는 둘뿐이다 — (i) **자기 append 의 커밋**. 그 커밋은
`exclude_from_context` 판정을 같은 트랜잭션에서 함께 쓴다. (ii) **다음 append 의 조정**. 그
조정은 등재를 같은 트랜잭션에서 함께 쓴다. 두 경로 모두 "수용 범위 진입"과 "등재 여부 확정"이
**하나의 커밋 경계** 안에 묶여 있으므로, 등재 없이 수용되는 상태는 만들어지지 않는다.
`context_excluded` 에 들어간 턴이 차단된 인젝션 발화였다면 복원으로 부활하지 않고, 정상
발화였다면 그 한 턴만큼 컨텍스트 충실도가 준다 — **감사 기록(대화 JSON)에는 어느 쪽이든 그
턴이 그대로 남는다.** 이 불변식의 형식 논증은 Phase 5 가 받는다.

#### 반대 방향은 `CORRUPT` 다

`actual < committed`(파일이 인덱스보다 **적음**)는 이 설계에서 발생할 수 없다 — 단계 4 의
`os.replace` 가 원자적이라 인덱스만 앞서는 커밋이 생기지 않기 때문이다. 그럼에도 관측되면
원인은 외부 변조나 저장 매체 유실이므로 `Err(CORRUPT)` 로 승격하고 **자동 복구하지 않는다.**
이 판정은 읽기(국면 ①)와 쓰기(§6.2 단계 2') 양쪽에 동일하게 둔다.

### 6.6 날짜 파티션 수의 상한은 **20** 이다

Phase 3 §3.3 은 "요청 턴 1개는 정확히 하나의 날짜 파티션"이라는 전제에서 상한 10 을 유도했다.
그 전제는 Phase 3 자신의 자정 경합 논증(§5.2)과 어긋난다 — 한 요청 턴은 `user` append 와
`assistant` append **두 번** 파일에 쓰고, 그 둘 사이에 자정이 지날 수 있다. `MAX_TURNS = 10`
(`app/chat.py:15`) × 2 append = **최대 20개 파티션**이 상한이다.

이 문서는 상한을 **20** 으로 쓴다. 실무적으로 둘 다 상수라 §6.3 의 길이 통제 논증은 영향받지
않지만, 복원이 여는 파일 수의 상한을 10 으로 못박은 구현은 20일에 걸친 세션에서 **조용히
잘린다.** 열 파일은 어차피 `turn_partitions` 의 키 집합이 확정하므로, 구현은 상한을
가정하지 말고 **키 집합을 그대로 순회**해야 한다.

---

## 7. 스키마와 계약

### 7.1 파일 배치

| 파일 | 용도 | 근거 |
|------|------|------|
| `data/sessions.db` | **신규** — 세션 + 레이트리밋 (D01·D04) | 기존 `/app/data` 볼륨(`Dockerfile:21` `VOLUME ["/app/data"]`)에 들어간다. 새 마운트·새 서비스 없음 |
| `data/chatlog.db` | 기존 — 일배치 분석용(`scripts/load_to_sqlite.py`) | **섞지 않는다.** 배치가 적재·재구축하는 분석 DB 에 런타임 상태를 넣으면 배치 재실행이 세션을 날린다 |
| `data/conversations/{day}/{sid}.json` | 기존 — 대화 원문 (D05 로 포맷 유지) | 소비자 5곳이 그대로 동작한다 |
| `data/ratelimit.json` | **폐기 예정** (Phase 6) | 내용이 `sessions.db` 의 레이트리밋 테이블로 이관된다 |

### 7.2 세션 테이블

```sql
PRAGMA journal_mode = WAL;      -- D01 확정. 동일 호스트 멀티프로세스 동시 접근
PRAGMA synchronous  = NORMAL;   -- WAL 에서의 표준 조합
PRAGMA foreign_keys = ON;       -- scripts/load_to_sqlite.py:27 의 관례를 따른다
PRAGMA busy_timeout = 5000;     -- §6.3

CREATE TABLE IF NOT EXISTS sessions (
    session_id            TEXT PRIMARY KEY,           -- 키 (§2.1)
    turns                 INTEGER NOT NULL DEFAULT 0, -- 독립 컬럼이어야 원자적 증가가 된다 (§5)
    slots                 TEXT    NOT NULL DEFAULT '{}',  -- JSON 직렬화 (§2.2)
    last_question_slot_id TEXT,                       -- NULL 이 의미를 갖는다
    participant_id        TEXT,
    turn_partitions       TEXT    NOT NULL DEFAULT '{}',  -- JSON {day: count} (§1.4, §6.5)
    context_excluded      TEXT    NOT NULL DEFAULT '[]',  -- JSON [[day, seq], ...] (Phase 3 §2.4)
    last_activity_at      TEXT    NOT NULL              -- ISO 8601 UTC — D03 TTL 기준
);
CREATE INDEX IF NOT EXISTS idx_sessions_last_activity
    ON sessions(last_activity_at);                    -- sweep_expired 의 범위 삭제용
```

`idx_sessions_last_activity` 가 없으면 `sweep_expired` 가 전체 스캔이 되어 §6.3 의 임계 구역
길이 상한이 세션 수에 비례해 깨진다.

### 7.3 레이트리밋 테이블 (D04)

D04 는 "같은 DB, 별도 테이블, 하나의 트랜잭션 경계"를 확정했다. 오늘 `data/ratelimit.json`
의 세 구조(`windows` / `known_sessions` / `daily`, `app/ratelimit.py:77`)를 그대로 옮긴다.

```sql
CREATE TABLE IF NOT EXISTS rate_window (
    ip       TEXT NOT NULL,
    seen_at  TEXT NOT NULL,                 -- ISO 8601 UTC
    PRIMARY KEY (ip, seen_at)
);
CREATE TABLE IF NOT EXISTS rate_known_session (
    session_id    TEXT PRIMARY KEY,
    first_seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rate_daily (
    day   TEXT PRIMARY KEY,                 -- ISO "YYYY-MM-DD"
    count INTEGER NOT NULL DEFAULT 0
);
```

`check_rate`(§1.5 #11)는 `BEGIN IMMEDIATE` 안에서 **알려진 세션 확인 → 윈도우 정리 → 캡 판정 →
카운트 증가**를 수행한다. `app/ratelimit.py:95-124` 의 `threading.Lock` + JSON read-modify-write
가 통째로 이 트랜잭션으로 대체되며, D04 가 논증한 "워커 수에 비례해 느슨해지지 않음"이 여기서
성립한다.

**`rate_known_session` 을 `sessions` 테이블에 흡수하지 않는 이유**: 흡수하면 "알려진 세션"의
수명이 세션 레코드의 수명(D03 24시간 TTL)에 묶인다. 만료 뒤 같은 `session_id` 로 오는 요청이
**신규 세션으로 다시 카운트**되어 레이트리밋이 느슨해진다. 오늘 `known_sessions` 는 만료되지
않으므로, 시맨틱을 보존하려면 별도 테이블이어야 한다. (이 테이블의 자체 보존 정책은 이번
설계 범위 밖이며 Phase 6 이 받는다.)

### 7.4 인증 필드 고립

```sql
CREATE TABLE IF NOT EXISTS session_auth (
    session_id    TEXT PRIMARY KEY,
    session_token TEXT NOT NULL,
    issued_at     TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);
```

`session_token` 을 `sessions` 에 두지 않고 분리하는 이유:

- **교체 가능성**: 장래 인증 체계(로그인, 외부 IdP, 만료·회전되는 토큰)를 도입할 때 손대야 할
  범위가 이 테이블 하나로 고립된다. `sessions` 의 스키마는 인증 방식과 무관하게 유지된다.
- **최소 권한**: 통계·복원 등 인증이 필요 없는 읽기 경로가 토큰 컬럼을 아예 보지 않는다.
- **`ON DELETE CASCADE`**: 세션 삭제(만료 sweep) 시 토큰이 남는 일이 없다.

**대가**: 생성이 두 테이블에 걸치므로 §4.3 의 두 `INSERT` 가 **반드시 같은 트랜잭션** 안에
있어야 한다. 한쪽만 커밋되면 "행은 있는데 토큰이 없는" 세션이 생겨 P1 이 깨진다.

### 7.5 `schema_version` 관례

기존 관례는 `app/storage.py:48`·`:58`·`:64` 의 payload 안 `"schema_version": 2` 다 —
**데이터와 같은 자리에 정수 단조 버전을 함께 저장**한다. 세션 스토어도 같은 관례를 따르되,
행마다 반복하지 않고 메타 테이블 한 행에 둔다.

```sql
CREATE TABLE IF NOT EXISTS store_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- INSERT OR IGNORE INTO store_meta(key, value) VALUES ('schema_version', '1');
```

**번호 공간은 `app/storage.py` 와 독립이다.** 대화 JSON 의 `schema_version = 2` 와 세션 스토어의
`schema_version = 1` 은 서로 다른 스키마의 서로 다른 버전이며, 두 숫자를 맞추려는 시도는
한쪽 포맷이 바뀔 때 다른 쪽에 의미 없는 번호 점프를 강요한다. 맞추는 것은 **번호가 아니라
관례**(정수 단조 증가, 데이터와 함께 저장, 읽기 시 확인)다.

`PRAGMA user_version` 을 쓰지 않는 이유: 이 리포의 기존 관례는 명시적 `schema_version` 키이고,
`user_version` 은 `sqlite3` CLI 로 들여다보지 않으면 보이지 않아 비개발자 운영 경로
(`run.py`)와 어울리지 않는다.

### 7.6 UTF-8 고정 계약

한국어 Windows 의 cp949 기본 인코딩은 이 리포가 이미 두 차례 비싸게 고친 실패 계열이다
(`1e9d900`, `c5adc0c`). 세션 스토어는 다음을 계약으로 고정한다.

| 지점 | 규정 | 기존 근거 |
|------|------|-----------|
| 대화 파일 read | `read_text(encoding="utf-8")` — 기본 인코딩 사용 금지 | `app/storage.py:88` |
| 대화 파일 write | `write_text(..., encoding="utf-8")` + `json.dumps(..., ensure_ascii=False)` | `app/storage.py:92` |
| 임시 파일 write (§6.3) | 같은 규정. `os.replace` 는 같은 볼륨 안에서만 | `app/ratelimit.py:86-88` |
| SQLite TEXT | `sqlite3` 는 TEXT 를 UTF-8 로 저장·반환한다. `text_factory` 를 바꾸지 않는다 | `app/stats.py:6`, `:237` |
| JSON 컬럼(`slots`, `turn_partitions`, `context_excluded`) | `json.dumps(..., ensure_ascii=False)` — 슬롯 값에 한국어가 들어간다 | `app/chat.py:333`, `app/prompting.py:38` |
| 프로세스 환경 | `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8` 유지 | `run.py:239-240` |

`ensure_ascii=False` 를 유지하는 것은 미관 문제가 아니다 — `True` 로 바뀌면 기존 파일과
새 파일의 바이트 표현이 갈려 diff·백업·수동 점검이 모두 어긋난다.

---

## 8. 후속 페이즈 인계

| 항목 | 인계처 |
|------|--------|
| 성질 P1(승자 토큰), §5.2 의 턴 캡 불변식, §6.5 의 **꼬리 폐쇄성** 불변식과 §6.4~6.5 의 매체 간 정합성(건전성·완전성, Phase 3 §5.3 의 I6), CAP12·CAP13 의 거짓 401 소멸 논증 | **Phase 5** |
| `app/main.py:43`·`:45`·`:59` 와 `app/chat.py:353` 의 이행, `_sessions` 직접 접근 **37곳/13파일**, `append_turn` 호출부 **9곳**의 반환값 수용, `data/ratelimit.json` → `rate_*` 테이블 데이터 이관, 스토어 도입 시점의 기존 `data/conversations` 파일 처리, `rate_known_session` 보존 정책 | **Phase 6** |
| `--workers 1` 고정(`Dockerfile:30`) 해제 조건과 기존 4개 공개 함수 폐기의 호환성 검토 | **Phase 7** |
| `docs/security-review.md §5` (a)~(e) 실제 해소 | 이번 task 범위 밖 (공개 전환 전 보안·법무 검토) |

회귀 기준선은 Phase 1 §6 이 확정한 **pytest 209 passed** 이며, 위 이행이 끝난 뒤에도 이
숫자가 유지되어야 한다.

---

## 관련 문서

- [Phase 1 현황 분석](./01-current-state.md)
- [Phase 2 정책 결정](./02-policy-decisions.md) — D01·D03·D04·D05
- [Phase 3 개인정보 경계와 `history` 복원](./03-history-restore.md) — D02, 해소안 (다)
- [phase-04-interface.md — 이 문서의 소스 페이즈](../../planning/session-store-multiworker/phase-04-interface.md)
- [decisions.md — D06 인터페이스 전면 재설계](../../planning/session-store-multiworker/decisions.md)
