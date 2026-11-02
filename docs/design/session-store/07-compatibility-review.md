# 세션 스토어 분리 — Phase 7: 크로스플랫폼·범위 밖 충돌 검토

> 이 문서는 origin(원 스펙)의 제약 두 가지와 범위 밖 항목에 붙은 단서 하나를 닫는다.
>
> - "크로스플랫폼(Windows/macOS/Linux)을 깨지 않을 것. `.github/workflows/cross-platform.yml`
>   매트릭스가 가드다."
> - "음성 기능은 제거됐다. 되살리는 설계를 넣지 말 것."
> - "범위 밖(인증·권한 체계, 관리자 화면 도메인 중립화, LLM 백엔드 API 전환) — 단, 세션 스토어
>   설계가 이들과 충돌하지 않는지는 검토해 문서에 남길 것."
>
> CAP43·CAP44·CAP45 가 지목하는 실패 모드는 "범위 밖"을 "완전히 무시"로 읽어 전방 호환성
> 검토를 아예 쓰지 않거나 "충돌 없을 것으로 예상" 한 줄로 fake-satisfy 하는 것이다. 그래서
> §5 는 세 항목을 하나의 문단으로 묶지 않고 각각 독립된 절로 쓴다. CAP38·CAP39 가 지목하는
> 실패 모드는 한 문장으로 크로스플랫폼 안전을 주장하고 위반 검출 메커니즘의 한계는 적지 않아
> 그 주장을 반증 불가능하게 만드는 것이다. §2 가 가드의 한계를 명시하는 이유가 이것이다.
>
> 입력 문서: [Phase 1 현황 분석](./01-current-state.md), [Phase 2 정책 결정](./02-policy-decisions.md)
> (D01 — SQLite 채택), [Phase 4 인터페이스 설계](./04-interface.md)(§2.2 저장 배치, §7.4 인증
> 필드 고립, §7.6 UTF-8 고정 계약). 이 문서 작성으로 저장소 코드는 한 줄도 바뀌지 않는다
> (CAP04·CAP08·CAP09).

---

## 1. 크로스플랫폼 위험 항목별 명명

"안전하다"는 결론 전에 무엇이 위험했는지를 먼저 적는다. 이 리포는 macOS에서 개발되지만
Windows 노트북·Linux 서버에서도 동작해야 하며(`.github/workflows/cross-platform.yml:2-6`
주석), 실제로 크로스플랫폼 실행 경로 정비를 별도 커밋(`1e9d900`, `19ffb76`, `c5adc0c`)으로
두 차례 이상 고친 전례가 있다(02-policy-decisions.md D01 근거 참고). 세션 스토어 설계가 같은
계열의 실패를 재도입하지 않는지 항목별로 논증한다.

| # | 위험 항목 | 위험의 실체 | 새 설계가 안전한 이유 |
|---|-----------|-------------|------------------------|
| 1 | Windows 파일락 시맨틱 | Windows는 POSIX와 파일 잠금 모델이 다르다 — 열려 있는 파일을 덮어쓰거나 이름을 바꾸는 연산이 플랫폼별로 실패 조건이 다르다 | 대화 JSON 파일 교체는 `os.replace`로 수행한다(04-interface.md §6.2 단계4, §6.3). **여기서 3-OS CI가 보증하는 범위를 정확히 좁혀 적는다**: `app/ratelimit.py:88` `os.replace(tmp_path, self._path)`가 세 러너에서 도는 것이 보증하는 것은 **크로스플랫폼 rename 시맨틱**(이 행이 다루는 위험)이며, `tests/test_ratelimit.py`가 전부 단일 프로세스·순차 테스트이므로 **다중 프로세스 안전성은 보증하지 않는다**(§2.2, 04-interface.md §6.3). 프로세스 간 안전의 근거는 별도다 — 새 설계의 tmp write + `os.replace`는 `BEGIN IMMEDIATE` 임계 구역 **안**에 있어 writer가 직렬화된다(04-interface.md §6.1·§6.2·§6.3). 세션 상태 자체는 SQLite에 있고, `sqlite3`는 WAL 모드에서 Windows/POSIX 양쪽의 잠금 프리미티브를 표준 라이브러리 내부에서 흡수한다 — 설계 문서가 플랫폼별 잠금 코드를 직접 작성하지 않는다(D01이 기각한 후보 ④ "파일 + 크로스플랫폼 파일락 직접 구현"이 정확히 이 위험을 피하려 기각된 안이다) |
| 2 | 경로 구분자 | Windows는 `\`, POSIX는 `/`를 쓴다. 문자열로 경로를 이어붙이면 한쪽 플랫폼에서만 깨진다 | 기존 코드가 이미 `pathlib.Path`로 경로를 조립한다(`app/storage.py:11` `from pathlib import Path`, `:13` `DEFAULT_CONVERSATIONS_DIR = Path("data/conversations")`, `:35`·`:84`의 `Path(base_dir) / ...`). 신규 `data/sessions.db`(04-interface.md §7.1)도 같은 `data/` 루트 아래 cwd 상대 경로이며 별도의 경로 조립 코드를 새로 추가하지 않는다 — 기존 관례를 그대로 잇는다 |
| 3 | 한국어 Windows 콘솔 cp949 | 한국어 Windows의 콘솔 기본 코드페이지는 cp949다. 한글을 그대로 `print`하면 `UnicodeEncodeError`로 죽는다(`run.py:51-52` 함수 docstring) | `run.py:50` `_force_utf8_console()`이 `sys.stdout`/`sys.stderr`를 `reconfigure(encoding="utf-8", errors="replace", line_buffering=True)`(`run.py:61`)로 강제하고, 서버 기동 직전 `run.py:334`에서 호출된다. 세션 스토어 계층은 콘솔에 직접 출력하지 않고 SQLite `TEXT` 컬럼과 JSON 파일에만 쓰므로 이 위험의 표면이 아니다 — 콘솔 강제는 런처(run.py) 책임으로 이미 닫혀 있고, 새 설계는 그 경계를 침범하지 않는다 |
| 4 | `sqlite3` 가용성 | 표준 라이브러리라도 일부 최소 빌드에서 빠질 가능성이 이론상 있다 | `app/stats.py:6` `import sqlite3`가 이미 이 리포의 살아있는 의존이고, `GET /api/stats`가 매 배포 환경에서 이를 임포트해 동작한다(02-policy-decisions.md D01 근거). `run.py:92`의 `check_environment()`는 Python 버전·`.venv`·의존성 패키지(`fastapi, uvicorn, yaml, anthropic`)·`.env`만 점검하고 `sqlite3`는 점검 대상에 없다 — `sqlite3`가 CPython 표준 배포에 포함되어 별도 점검이 불필요하기 때문이다. `.github/workflows/cross-platform.yml`의 `actions/setup-python@v5`(:27-30)가 windows/ubuntu/macos 세 러너 모두에 표준 CPython 배포를 설치하므로 `sqlite3` 부재 시나리오는 이 CI 환경에서 발생하지 않는다 |

### UTF-8 고정 계약과의 연결

UTF-8 고정은 이 리포의 계약이다. `run.py`의 콘솔 강제(위 표 3행)뿐 아니라, `storage`의 파일
I/O도 `encoding="utf-8"`을 명시한다 — `app/storage.py:88` `path.read_text(encoding="utf-8")`,
`:92` `path.write_text(..., encoding="utf-8")`. 기본 인코딩(플랫폼 로케일 의존)을 쓰지 않는
것이 이 계약의 핵심이며, 기본 인코딩을 쓰면 한국어 Windows에서 cp949로 조용히 떨어진다.

새 스토어 계층도 이 계약을 그대로 따른다는 것이 04-interface.md §7.6 "UTF-8 고정 계약"에
명문화되어 있다 — 대화 파일 read/write는 기존 규정을 유지하고, SQLite `TEXT` 컬럼은
`sqlite3`가 UTF-8로 저장·반환하며 `text_factory`를 바꾸지 않고, JSON 컬럼(`slots`,
`turn_partitions`, `context_excluded`)은 `json.dumps(..., ensure_ascii=False)`로 직렬화한다.
새 계층이 이 표의 위험 3항목(파일락 시맨틱 제외)에 노출되는 유일한 지점이 파일 I/O와 텍스트
인코딩인데, 그 지점이 기존 계약을 상속하므로 새로운 위험 표면을 추가하지 않는다.

---

## 2. CI 가드 지목과 그 한계

### 2.1 가드로 지목한다

`.github/workflows/cross-platform.yml:21-22`의 매트릭스가 이 task의 크로스플랫폼 위반 검출
가드다.

```yaml
matrix:
  os: [windows-latest, ubuntu-latest, macos-latest]
  python-version: ["3.11", "3.13"]
```

이 매트릭스가 실제로 실행하는 것은 세 단계다: (1) `python -m pytest -q`(:36) — 209 기준선,
(2) "런처 자동 복구"(:38-56) — 클론 직후 상태에서 `run.check_environment()` /
`run.repair_environment()`가 끝까지 도는지, (3) "서버 기동 + 대화 1턴(한글 왕복)"(:58-105) —
uvicorn을 `subprocess.Popen`으로 띄우고(`:68-71`, `--workers` 인자 없음 → 기본값 1워커 단일
프로세스) 한글 메시지를 보내 저장된 JSON을 read-back해 문자 단위로 대조한다(`:96-101`).

### 2.2 가드의 한계 — 스위트가 단일 프로세스다

**동시에 그 한계를 적는다.** 이 매트릭스는 스위트가 실제로 돌리는 것만 지킨다. 저장소 전체를
실측한 결과, `tests/` 27개 파일 어디에도 uvicorn 워커를 2개 이상 동시에 띄우거나
`multiprocessing.Process`로 별도 프로세스를 fork해 같은 세션에 동시 접근하는 테스트가 없다
(`grep -rniE "workers|multiprocess|Process\(|subprocess.*uvicorn" tests/`의 유일한 매치는
`tests/test_llm_cli.py`의 `subprocess.Popen` 목킹이며, 이는 LLM CLI 서브프로세스 호출을 흉내
내는 것이지 uvicorn 워커가 아니다). CI 워크플로 자신의 "서버 기동" 스텝도 `--workers` 인자
없이 단일 프로세스 uvicorn 하나만 띄운다(:68-71).

즉 CI는 다음을 지킨다:

- `sqlite3` 가용성 (§1의 4행 — 임포트·기본 동작이 세 OS 모두에서 실패하지 않음)
- 경로 구분자 (§1의 2행 — 대화 JSON이 실제로 저장되고 다시 열림)
- UTF-8/cp949 왕복 (§1의 3행 — 한글 메시지를 보내 저장된 파일을 바이트 단위로 대조하는 것이
  바로 이 워크플로의 "한글 왕복" 스텝의 목적)

그러나 **Phase 5의 다중 워커 불변식은 지키지 않는다.** 구체적으로, 04-interface.md가 형식
논증 대상으로 남긴 것들 — §4.4의 성질 P1(승자 토큰: 두 워커가 동시에 같은 `session_id`로 첫
요청을 보내도 클라이언트에게 나가는 토큰이 항상 테이블에 실재하는 값임), §5.2의 10턴 캡
불변식(`consume_turn`의 `WHERE turns < max_turns` 원자성), §6.5의 꼬리 폐쇄성 불변식(매체 간
정합성) — 이들은 모두 **두 워커가 실제로 동시에 같은 세션에 접근할 때만** 검증 가능한
성질이다. CI 매트릭스는 그런 시나리오를 한 번도 실행하지 않으므로, 이 불변식들이 실제
구현에서 성립하는지에 대해 아무 신호도 주지 않는다. **이 문장을 적는 것이 CAP39를
fake-satisfy와 가르는 지점이다** — "3-OS 매트릭스가 있으니 안전하다"고만 쓰면 매트릭스가
검증하는 축(OS·인코딩)과 이 task의 핵심 위험 축(동시성)이 다르다는 사실이 가려진다.

이 한계는 이번 설계 문서의 결함이 아니라 **범위 경계**다 — 다중 워커 시나리오를 실제로
실행하는 테스트를 추가하는 일은 Phase 6(이행 스펙)의 소관이며, 그 불변식들의 형식 논증은
Phase 5의 소관이다. 이 문서는 "지금 가드가 무엇을 보장하지 않는가"만 정확히 기록한다.

---

## 3. 반사실 기록 — 외부 서비스형 스토어를 필수로 골랐다면

GitHub Actions의 service container 기능은 **Linux 러너 전용**이다 — `windows-latest`,
`macos-latest` 러너는 Docker 데몬을 갖지 않으므로 `services:` 키로 선언하는 컨테이너(Redis
등)를 그 두 러너에서 실행할 수 없다.

D01(02-policy-decisions.md)에서 이미 후보 ②(Redis 필수 의존)를 기각하며 이 사실을 근거로
들었다. 이 절은 그 논증을 **CI 가드 대칭성** 관점에서 다시 확인한다:

- 세션 스토어를 필수 외부 서비스(Redis 등)로 설계했다면, `windows-latest`/`macos-latest`
  레그에서 그 서비스를 기동할 방법이 없다. 선택지는 둘뿐이다 — (a) 해당 두 레그에서 스토어
  의존 코드 경로를 건너뛰거나 목(mock)으로 대체하는 것, 또는 (b) 워크플로를 `ubuntu-latest`
  전용으로 좁히는 것. 둘 다 매트릭스의 실질 보장 범위를 `[windows-latest, ubuntu-latest,
  macos-latest] × [3.11, 3.13]`(:21-22)이 **암시하는 대칭 6조합**에서 실제로는 **ubuntu만
  스토어 경로를 검증하는 비대칭 매트릭스**로 축소시킨다.
- 이 비대칭은 §2가 이미 지목한 "CI는 실제로 돌리는 것만 지킨다"는 원칙의 또 다른 사례다 —
  매트릭스 선언(6조합)과 매트릭스가 실제로 검증하는 것(스토어 경로는 2조합만) 사이에
  간극이 생기고, 그 간극이 이번에는 OS 축 전체에 걸린다는 점에서 §2의 간극(동시성 축)보다
  더 크다.
- **SQLite 채택이 이 비대칭을 피한 이유**: `sqlite3`는 표준 라이브러리라 `services:` 선언이
  전혀 필요 없다. 세 OS 모두 `actions/setup-python@v5`(:27-30)가 설치하는 동일한 CPython
  배포에 이미 포함되어 있으므로, 스토어 경로(`GET /api/chat`이 세션을 읽고 쓰는 전 과정)가
  6조합 전부에서 **실제로** 실행된다. §2.1의 "서버 기동 + 대화 1턴" 스텝이 세 OS 모두에서
  같은 방식으로 통과하는 것이 그 증거다 — 이 스텝이 성립하려면 세션 저장 경로가 그 OS에서
  실제로 동작해야 한다.

이 절이 §2의 한계 기록과 모순되지 않는다는 점을 명시한다: §2는 "매트릭스가 동시성을
검증하지 않는다"는 한계를, §3은 "그럼에도 매트릭스가 OS×스토어 조합 전체를 대칭적으로
실행한다"는 사실을 기록한다. 전자는 검증 **깊이**의 한계이고 후자는 검증 **범위**의
대칭성이며, SQLite 선택은 후자를 지키는 대가로 전자의 한계를 도입하지 않는다 — 오히려
Redis 안이었다면 전자(동시성 미검증)와 후자(OS 비대칭)가 **동시에** 발생했을 것이다.

---

## 4. Docker 배포 형상 적합성

### 4.1 단일 `/app/data` 영속 볼륨

`Dockerfile:21` `VOLUME ["/app/data"]`가 유일한 영속 마운트 지점이다. 04-interface.md §7.1이
확정한 파일 배치 — 신규 `data/sessions.db`, 기존 `data/chatlog.db`, `data/conversations/`,
폐기 예정 `data/ratelimit.json` — 는 전부 이 한 볼륨 아래에 있다. 새 마운트나 새 서비스를
요구하지 않으므로 배포 형상을 바꾸지 않는다.

### 4.2 cwd 상대 경로

`Dockerfile:15-20` 주석이 명시하듯, `app/ratelimit.py`(`DATA_PATH`)·`app/storage.py`
(`DEFAULT_CONVERSATIONS_DIR`)·`scripts/load_to_sqlite.py`(`DEFAULT_DB_PATH`)가 전부 cwd 기준
상대경로를 쓰며, 컨테이너 실행 시 cwd가 `WORKDIR`(`/app`, `Dockerfile:5`)와 같다는 전제에
의존한다. 신규 `data/sessions.db`(04-interface.md §7.1)도 같은 관례(cwd 상대, `data/` 루트
아래)를 따르므로 이 전제를 깨지 않는다 — 새 예외 경로를 추가하지 않는다.

### 4.3 컨테이너 수명주기와 `--workers 1`

`Dockerfile:25-30`이 `--workers 1`을 사유 주석과 함께 고정한다: (1) `RateLimiter`의 프로세스
내부 `threading.Lock` 전제, (2) `app/chat.py`의 `_sessions`가 프로세스 메모리 dict라 워커가
여럿이면 세션별 10턴 캡이 워커마다 따로 논다. 이 task 전체(Phase 1~6)의 목표가 이 고정을
해제할 수 있는 조건을 설계하는 것이지만, **이 문서 자신이 그 고정을 지금 푸는 것은 아니다**
— `Dockerfile`은 코드/설정 파일이므로 CAP04·CAP08·CAP09에 따라 이 task 어떤 문서 페이즈도
직접 수정하지 않는다. `--workers 1` 해제는 Phase 6(이행 스펙)이 다루는 실행 단계의 산출물이다.

컨테이너 수명주기 관점에서 새 설계가 개선하는 지점: 오늘은 컨테이너 재시작(배포, 크래시
복구)마다 `_sessions` dict가 전량 소실된다(Phase 1 §1 블로커 1). 새 설계는 세션 상태가
`/app/data` 볼륨 위 SQLite 파일에 있으므로, 컨테이너가 재생성돼도 볼륨이 유지되는 한 세션이
살아남는다 — D03의 24시간 TTL이 그 생존 상한을 규정한다.

**`--workers 1`이 보장하지 않는 것 — 블로커 3.** 위 두 사유가 `--workers 1`로 닫히는 항목의
전부다. **블로커 3(대화 JSON 동시 쓰기 유실)은 이
고정으로 보호되지 않는다.** 근거는 `app/main.py:20` `def post_chat`이 `async def`가 아니라
**동기 함수**라는 점이다 — Starlette는 동기 라우트 핸들러를 이벤트 루프가 아니라 스레드풀에서
실행하므로, 워커 프로세스가 하나여도 같은 세션에 대한 요청이 **한 프로세스 안에서 병렬로**
`app/storage.py:88`(read) / `:92`(write)에 도달한다. `:92` `path.write_text(...)`는 먼저
truncate하고 쓰므로 그 창에서 `:88`이 빈 파일을 읽어 `JSONDecodeError`로 죽는다
(04-interface.md §6.3). 실측으로도 `--workers 1`에서 같은 세션 동시 4건으로 3라운드 전부
재현됐다.

따라서 §4.3의 정확한 진술은 "`--workers 1`이 블로커 1·2 계열(프로세스 내부 락, 프로세스
메모리 dict)을 닫고 **블로커 3은 열어 둔다**"이다. 이 구분은 §2.2가 기록한 CI 가드의 한계와
같은 계열이다 — 단일 프로세스라는 전제가 보장 범위를 **암시적으로 넓혀 보이게** 만드는
지점이다.

**05 §9 #5 인계의 종결.** [05-invariants.md §9](./05-invariants.md) 표의 5행이 정확히 이
관측(`app/main.py:20` 동기 함수 → 블로커 3이 `--workers 1`에서도 도달 가능)을 Phase 7로
인계했다. 이 절이 그 인계를 수용해 **여기서 종결한다**: `--workers 1` 해제 논의의 입력으로
확정된 결론은 "블로커 3은 `--workers 1` 해제와 **독립된** 결함이며, 워커를 늘리지 않아도
존재하고 워커 수를 되돌려도 사라지지 않는다"이다.

**다만 이것이 05 §8.3의 필요조건에 항목을 더한다는 뜻은 아니다.** 05 §8.2의 T3 정의는
"`_sessions` 직접 접근 **37곳/13파일**과 `storage.append_turn` 호출 **9곳**이 전부 스토어
연산으로 이행된다"이므로, `append_turn` 9곳의 이행이 T3 안에 이미 들어 있다. 그 9곳이
04-interface.md §6.2의 임계 구역으로 옮겨가면 T4("모든 갱신이 `BEGIN IMMEDIATE` 단일 트랜잭션
안에")와 결합해 쓰기가 직렬화된다 — 즉 **블로커 3의 쓰기 직렬화는 T3 완결의 귀결이지 T3 밖의
추가 조건이 아니다.** 이 절이 채우는 빈칸은 필요조건의 개수가 아니라 그 연결의 명시다: 05
§8.3 서술이 `Dockerfile:25-29`의 두 사유만 다루기 때문에, T3 완결이 블로커 3까지 닫는다는
사실이 그 절에 드러나 있지 않다.

코드 수정 자체는 이 task 범위 밖이며(CAP04·CAP08·CAP09) 이행 task의 S단계가 담당한다 —
`app/ratelimit.py` 계열은 D04가 레이트리밋을 DB 테이블로 옮기면서, `storage.append_turn`
쓰기는 04-interface.md §6.2의 임계 구역으로 이행하면서 닫힌다.

### 4.4 확인 — 음성 기능 미부활, 범위 밖 3항목 미설계

- **음성 기능**: `docs/design/session-store/01-current-state.md`부터 `04-interface.md`까지
  네 문서를 전수 검색한 결과(`grep -niE "음성|voice|tts|stt"`) 음성/TTS/STT 관련 언급이
  한 건도 없다. 되살리는 설계를 넣지 말라는 origin 제약(`origin.md:70` "음성 기능은
  제거됐다. 되살리는 설계를 넣지 말 것.")을 위반하지 않는다.
- **범위 밖 3항목의 실제 설계 여부**: 같은 네 문서를 검색한 결과, "관리자"라는 단어는 한
  건도 등장하지 않고(관리자 화면 UI/라우팅을 설계하지 않았다), "인증 체계"/"로그인"/"IdP"는
  04-interface.md §7.4의 **인증 필드를 스키마에서 고립시키는** 근거 설명 두 곳에서만
  등장하며 실제 인증 흐름(로그인 폼, 세션 발급 정책 변경, 권한 등급)을 설계하지 않았다.
  "LLM 백엔드"/"제공자 전환"/`provider` 관련 설계도 네 문서에 없다. 세 항목 모두 §5에서
  다루는 것은 **충돌 여부 검토**이지 그 항목 자체의 설계가 아니다 — origin이 요구한 경계를
  지켰다.

---

## 5. 범위 밖 3항목 충돌 검토

세 항목을 하나의 문단으로 묶지 않고 각각 독립된 절로 검토한다.

### 5.1 인증·권한 체계

세션 토큰은 이미 인증 역할을 하고 있다. `app/chat.py:49`
`session_token: str = field(default_factory=lambda: secrets.token_urlsafe(32))`가 암호학적으로
안전한 난수 토큰을 발급하고, `app/chat.py:64-69` `owns_session()`이
`secrets.compare_digest(session.session_token, session_token)`(`:69`)로 타이밍 공격에 안전한
상수시간 비교를 수행한다. 이것은 장래 도입할 "인증 체계"가 아니라 **오늘 이미 동작 중인**
인증 메커니즘이다 — 범위 밖 항목은 이것을 **대체하거나 확장**하는 미래 작업이지, 무(無)에서
시작하는 작업이 아니다.

**충돌 지점**: 장래 인증 체계(로그인, 외부 IdP 연동, 만료·회전되는 토큰 등)를 도입하면 그
체계가 지금의 `session_token`이 있던 자리를 손대야 한다. 이 위치가 스토어 스키마의 어디에
있는지가 그 도입 비용을 결정한다.

**Phase 4의 조치와 그 연결**: 04-interface.md §7.4가 `session_token`을 `sessions` 테이블이
아니라 별도 `session_auth` 테이블(`session_id` PRIMARY KEY, `session_token`, `issued_at`,
`ON DELETE CASCADE`)에 고립시켰다. 그 근거로 명시한 것이 정확히 이 충돌 항목이다 —
"**교체 가능성**: 장래 인증 체계(로그인, 외부 IdP, 만료·회전되는 토큰)를 도입할 때 손대야
할 범위가 이 테이블 하나로 고립된다. `sessions`의 스키마는 인증 방식과 무관하게 유지된다"
(04-interface.md §7.4). 즉 이 충돌은 Phase 4에서 **미리 인지되어 완화 조치까지 설계된**
상태다 — 인증 체계 전환 시 `sessions` 테이블(turns/slots/last_question_slot_id/
participant_id/turn_partitions/context_excluded/last_activity_at)은 건드릴 필요가 없고,
`session_auth` 테이블 하나만 교체·확장 대상이 된다. 완전한 무결합은 아니다 — `session_auth`
자체가 `sessions(session_id)`를 외래키로 참조하므로(§7.4 `FOREIGN KEY ... REFERENCES
sessions(session_id)`) 세션 식별자 자체와는 여전히 묶여 있다. 그러나 "인증 방식"(토큰 발급
로직, 검증 로직, 만료 정책)이라는 가변 부분과 "세션 식별"이라는 불변 부분이 테이블 경계로
분리되어 있다는 것이 이 조치의 실질이다.

### 5.2 관리자 화면 도메인 중립화

**판단할 것**: 저장되는 세션 형상이 이 상담 도메인(중독/위기 상담)의 슬롯을 하드코딩하는가.

**Phase 4의 선택**: 04-interface.md §2.2 표의 4행이 `slots`(`app/chat.py:52`,
`dict[str, str]`)를 `sessions.slots` 컬럼 하나에 `TEXT NOT NULL DEFAULT '{}'`로 **JSON
직렬화**해 저장한다고 확정했다. 선택 이유로 명시한 문장을 그대로 인용한다: "`dict[str,str]`,
항상 통째로 읽고 쓰며 슬롯 키 단위로 질의하지 않는다(라우팅·패널·요약이 전량을 본다). 자식
테이블은 조인 비용만 늘린다"(04-interface.md §2.2). 즉 개별 슬롯(예: 위기 징후 여부, 중독
유형, 나이대 등 이 도메인 특유의 접수 항목)을 SQL 컬럼으로 펼쳐서 스키마에 박아 넣는 안은
검토되어 **채택되지 않았다** — `sessions` 테이블 DDL(04-interface.md §7.2)에는 슬롯 이름이
한 글자도 등장하지 않는다.

**귀결**: `slots`가 불투명 직렬화(opaque blob)로 남아 있으므로, 장래 관리자 화면이 다른
도메인(예: 다른 상담 유형, 다른 접수 항목 집합)으로 중립화될 때 `sessions` 테이블의 DDL을
바꿀 필요가 없다 — 슬롯 스키마의 변경은 애플리케이션 계층(`app/chat.py`, `app/intake.py`)의
책임으로 남고, 스토어 계층은 그 변경에 대해 완전히 불가지(agnostic)다. 이것이 표에 적힌
"슬롯 키 단위로 질의하지 않는다"는 선택이 우연히 얻은 부수 효과가 아니라, 도메인 중립화라는
범위 밖 항목과 실제로 충돌하지 않는 이유다. **대가**: 이 선택의 대가는 §2.2가 이미 적었듯
SQL로 슬롯 단위 질의(예: "특정 슬롯 값을 가진 세션 목록")가 불가능하다는 것이며, 그런
질의가 필요해지면 자식 테이블로 승격해야 한다 — 그 시점이 오면 이 문서의 "불투명 유지"
선택을 재검토해야 한다.

`last_question_slot_id`(04-interface.md §2.2 5행)는 슬롯 값 자체가 아니라 "직전에 질문한
슬롯의 id 문자열"을 담는 범용 컬럼이며 도메인 특유의 슬롯 이름을 스키마에 고정하지 않는다
— 이 컬럼도 같은 중립성을 유지한다.

### 5.3 LLM 백엔드 API 전환

**판단할 것**: `history` 엔트리의 `{"role": ..., "content": ...}` 형상(OpenAI/Anthropic 계열
메시지 API가 공유하는 관례적 형상)이 현재 LLM 제공자를 스키마에 고정하는가.

**스키마에는 고정되지 않는다** — Phase 3의 D02 결정(02-policy-decisions.md, 03-history-restore.md
§1)에 따라 `history`(`app/chat.py:51`) 자체가 세션 스토어에 저장되지 않는다. 04-interface.md
§2.2 3행이 명시하듯 저장 위치는 "**미저장**"이며, `sessions` 테이블 DDL(§7.2)에도 `role`/
`content`라는 컬럼이나 그런 구조를 암시하는 JSON 스키마가 없다. 따라서 스키마 자체를 놓고
보면 이 결합은 존재하지 않는다.

**그럼에도 결합이 남는 지점**: 03-history-restore.md §5 "복원 알고리즘"의 6단계가
`return [ {role: t.role, content: t.text} for t in collected ]`로 저장된 `text`를 `content`
키로 사상하며, "대화 JSON은 `text`, history는 `content` 키를 쓴다(chat.py:323-324 참고)"고
명시한다(03-history-restore.md §5, 6단계). 이 사상은 04-interface.md §1.5 연산 표 8행
`restore_history`의 반환 타입 `list[{role, content}]`로 인터페이스 계약에 승격되어 있다
(04-interface.md §1.5). 즉 **결합이 남는 곳은 스키마(저장 형태)가 아니라 복원 경로의 반환
계약(`restore_history`의 출력 형상)이다** — `role`/`content`라는 두 키 이름과, `role` 값이
`user`/`assistant` 두 어휘로 제한된다는 점(03-history-restore.md §4 "복원 필터 규칙":
`role ∈ {"user", "assistant"}`만 통과)이 그 계약에 박혀 있다.

**전환 시 실제로 영향받는 범위**: 현재 제공자(Anthropic 계열, `app/llm.py`)가 이 두 키
이름의 메시지 배열을 컨텍스트로 받는 관례를 쓰기 때문에 `restore_history`가 그 형상을 그대로
재조립한다. LLM 백엔드가 바뀌어 컨텍스트 표현이 달라진다면(예: 멀티파트 콘텐츠 블록, 다른
role 어휘, 배열이 아닌 다른 구조), 영향받는 것은 `sessions` 테이블 DDL이 아니라
`restore_history`의 반환 타입과 03-history-restore.md §5의 6단계 사상 함수뿐이다. 저장된
원본(`data/conversations/{day}/{session_id}.json`의 `{seq, role, text}`, `app/storage.py:91`)과
스토어 인덱스(`turn_partitions`, `context_excluded`)는 `role`/`text`라는 저장 계층 고유의
어휘를 쓰고 있어 LLM 제공자 어휘와 이미 분리되어 있으므로 전환의 영향이 스키마까지 번지지
않는다 — Phase 3 §0의 "저장 계층은 '무슨 일이 있었나'를, `history`는 '모델에게 무엇을
보여줄까'를 담는다"는 원칙이 이 분리를 만든 원인이다.

---

## 6. 후속 페이즈 인계 요약

| 항목 | 인계처 |
|------|--------|
| §2가 지목한 다중 워커 불변식(P1·10턴 캡·꼬리 폐쇄성)의 형식 논증 — CI는 이를 검증하지 않는다 | Phase 5 (이미 진행 중) |
| `--workers 1`(`Dockerfile:25-30`) 해제, 다중 워커 시나리오를 실제로 실행하는 테스트 추가 | Phase 6 |
| §5.2가 기록한 "슬롯 단위 SQL 질의 불가"의 대가가 실제로 필요해지는 시점의 재검토 | 이번 task 범위 밖 |
| §5.1·§5.3이 기록한 결합 지점(`session_auth` 외래키, `restore_history` 반환 계약)의 실제 전환 작업 | 이번 task 범위 밖 (해당 전환 자체가 별도 task) |

## 관련 문서

- [Phase 1 현황 분석](./01-current-state.md)
- [Phase 2 정책 결정](./02-policy-decisions.md) — D01(SQLite 채택, service container 논증의 선행 근거)
- [Phase 3 개인정보 경계와 `history` 복원](./03-history-restore.md) — §0, §5 복원 알고리즘
- [Phase 4 `SessionStore` 인터페이스 설계](./04-interface.md) — §2.2, §7.1, §7.4, §7.6
- [phase-07-compatibility-review.md — 이 문서의 소스 페이즈](../../planning/session-store-multiworker/phase-07-compatibility-review.md)
- `.github/workflows/cross-platform.yml` — 크로스플랫폼 CI 가드
- `Dockerfile` — 배포 형상
