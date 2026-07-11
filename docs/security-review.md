# 보안 검토 — lmwiki-chatbot (Phase 7)

- 검토일: 2026-07-11
- 검토 대상: Phase 1~6 완료 시점의 `app/`, `scripts/`, `static/`, 저장 데이터(`data/`)
- 검토자: AI 검토 (opus). 사람 보안 개발자 검토는 아래 "권고" 항목 참고.
- 배포 맥락: **내부 시연**. 첫 도메인은 상담 초기 면담(민감정보 유입 가능) → 저장 데이터 항목 가중 점검.

판정 표기: `PASS`(문제 없음) / `FIXED`(이 phase에서 수정) / `RISK`(수용한 잔여 위험) / `FOLLOW-UP`(공개 서비스 전환 시 필요, 현재 비차단) / `권고`(사람 보안 개발자 검토 권장).

---

## 1. 키 노출 — PASS

- `ANTHROPIC_API_KEY`는 `app/config.py`가 환경변수에서만 읽는다. 코드/문서에 하드코딩된 키 없음.
- `.env`와 `data/`는 `.gitignore`에 있고, git 히스토리에 **한 번도 추적된 적 없음** (`git log --all --name-only`로 확인).
- git 히스토리 시크릿 스캔: `sk-ant-...` 패턴 매치 0건 (`git rev-list --all` 전체 대상 `git grep`). `.env.example`은 값이 빈 템플릿이라 안전.
- 클라이언트 응답(`/api/chat` JSON, 에러 메시지)에 키/시크릿 노출 경로 없음. `app/llm.py`는 응답 텍스트만 반환하고 예외 메시지에 키를 싣지 않음.

## 2. 입력 검증 — FIXED

경계 = HTTP 엔드포인트 `POST /api/chat` (`app/main.py`).

- **길이 상한**: `MAX_MESSAGE_LEN=2000` 초과 시 400. (`tests/test_security.py::test_over_length_message_is_rejected`)
- **타입 검증**: `message`/`session_id`가 문자열 아니거나 빈 값이면 400.
- **비 JSON content-type 거부**: `application/x-www-form-urlencoded`·`text/plain`·빈 본문 → 422. FastAPI가 `Body(...)` 계약으로 application/json만 수용. 실측 확인. (`tests/test_security.py`의 content-type 테스트 2건)
- **[FIXED] session_id 화이트리스트를 API 경계로 끌어올림**: 기존엔 `main.py`가 session_id를 "비어있지 않은 문자열"로만 검사하고, 실제 화이트리스트(`[A-Za-z0-9._-]{1,128}`) 검증은 `app/storage.py` 층에서만 했다. 그 결과 `session_id="../../etc/passwd"`나 129자 이상 입력이 **500 Internal Server Error**로 샜다(경로 순회 자체는 정규식이 막아 파일 쓰기는 발생 안 함 — 순수 견고성/노출 문제). 수정: `storage.valid_session_id()` 공개 헬퍼를 추가해 `main.py`와 `storage.append_turn`이 **같은 규칙 하나**를 공유하도록 하고, 경계에서 불합격 시 400 반환. (`tests/test_security.py`의 session_id 테스트 3건)
  - 변경: `app/main.py`, `app/storage.py`.

## 3. 프롬프트 인젝션 — PASS (지식 문서 = 신뢰 경계로 문서화) + 잔여 위험 문서화

- 구조(`app/chat.py`): 시스템 프리앰블 + 지식 문서 본문 → `system` 역할, 사용자 발화 → `user` 역할로 분리 전달. 사용자 입력은 시스템 지시와 다른 역할 채널에 들어가므로 사용자가 시스템 프리앰블을 직접 덮어쓰지 못한다.
- **지식 문서는 신뢰 경계**: 지식 문서 본문이 `system`에 그대로 합쳐진다. 즉 지식 문서를 넣는 주체(운영자 / SecondBrain 위키 큐레이션)가 신뢰 주체다. 외부인이 지식 디렉토리에 문서를 주입할 수 있으면 시스템 지시를 오염시킬 수 있다 → `KNOWLEDGE_DIR`는 운영자만 쓰기 가능해야 한다(배포 시 권한 확인).
- **[RISK] LLM 프롬프트 인젝션은 코드로 100% 못 막음**: 사용자가 "이전 지시 무시" 류 발화를 시도할 수 있다. 완화책 = 역할 분리(위) + 출력이 어디서도 실행/평가되지 않음. LLM 응답은 UI에서 `textContent`로만 렌더(§7)되어 XSS로 전이되지 않고, 서버 측에서 코드/쿼리로 해석되는 경로도 없다. 정보 유출 표면도 시스템에 넣은 지식 문서(공개 위키)로 한정. 내부 시연 범위에서 수용.

## 4. Rate limit 우회 (XFF 스푸핑) — PASS

- `app/ratelimit.py::client_ip()`가 `TRUST_PROXY_HOPS`로 X-Forwarded-For 신뢰 범위를 결정한다.
  - `hops=0`(기본): XFF 완전 무시, 소켓 원격 주소만 사용 → 클라이언트가 XFF를 위조해도 무효.
  - `hops>=1`: XFF 오른쪽에서 hops번째 값만 신뢰, 그 왼쪽(클라이언트 조작 가능)은 버림.
  - `hops`보다 XFF 항목이 적으면 소켓 주소로 폴백.
- 시나리오 재점검: 기존 `tests/test_ratelimit.py`가 hops 0/1/2·헤더 없음 경우를 모두 커버. 스푸핑된 왼쪽 값이 채택되지 않음을 확인.
- 운영 주의: 프록시 뒤 배포 시 `TRUST_PROXY_HOPS`를 실제 홉 수로 정확히 설정해야 한다. `hops=0`인데 XFF가 관측되면 프로세스당 1회 경고 로그를 남긴다.

## 5. 저장 데이터 — PASS + FOLLOW-UP (상담 도메인 가중)

현재 저장물:

- `data/conversations/YYYY-MM-DD/{session_id}.json`: `{seq, role, text}`만 저장. IP·이름·이메일 등 **불필요한 식별자 미저장**. session_id는 클라이언트가 생성한 `crypto.randomUUID()`(`static/app.js`)라 서버가 개인정보를 심지 않음.
- `data/ratelimit.json`: rate limit 상태로 **IP 주소**와 session_id 보관. IP는 일부 규제상 개인식별정보 — 운영상 필요하고 `data/`(gitignore)에 국한. [RISK-수용]
- `data/chatlog.db`(배치 적재): 위 대화 JSON을 그대로 UPSERT. 추가 식별자 없음.
- **접근 경계**: `data/`를 서빙하는 엔드포인트 없음. static 마운트는 `static/`에 루트가 고정된 `StaticFiles`라 `data/`로 못 빠져나감(StaticFiles 자체 경로 순회 방어 + 디렉토리 루트 제한). session_id 화이트리스트(§2)가 파일명 경로 순회를 차단.

**[FOLLOW-UP] 공개 서비스 전환 시 (현재 내부 시연이라 비차단):**

- 상담 초기 면담 도메인 → 사용자가 대화에 민감정보(정신건강·개인사)를 입력할 수 있음. 지금은 평문 저장, 암호화·접근통제 없음.
- 필요 항목: (a) **보존 기간** 정의 + 자동 만료 삭제, (b) **삭제 요청** 처리 절차, (c) 저장 고지 강화 — 현재 UI 문구 "이 대화 내용은 서버에 저장됩니다"를 동의/목적/보존기간까지 포함하도록 확장, (d) 저장 시 암호화 또는 `data/`·`chatlog.db` 파일 권한 최소화, (e) 백업/로그에 대화 원문이 새지 않는지 점검.
- **[권고]** 위 (a)~(e)는 개인정보/의료정보 취급 요건과 얽히므로 공개 전환 전 **사람 보안·법무 검토** 권장.

## 6. 의존성 — 권고 (pip-audit 미가용)

- `requirements.txt`가 **버전 미고정**(fastapi, uvicorn, anthropic, pyyaml, pytest, httpx). 현재 설치본: fastapi 0.139.0, starlette 1.3.1, uvicorn 0.51.0, anthropic 0.116.0, pydantic 2.13.4, PyYAML 6.0.3, httpx 0.28.1, pytest 9.1.1.
- `pip-audit` 미설치 → 이번 검토에서 알려진 취약점 자동 조회는 수행 못 함(checklist "pip-audit 가용 시" 조건 미충족). 새 도구를 무리해서 설치하지 않음.
- **[권고]** (a) `requirements.txt` 버전 핀 고정, (b) CI 또는 배포 파이프라인(Phase 8)에서 `pip-audit` 정기 실행.

---

## 요약

- 즉시 수정(FIXED): §2 session_id 500→400 경계 하드닝 (1건). high/critical급 취약점 없음.
- PASS: 키 노출, XFF 스푸핑, 저장 데이터 접근 경계, XSS(§7 아래).
- 수용 잔여 위험(RISK): LLM 프롬프트 인젝션(구조적 완화·저영향), ratelimit IP 저장.
- 후속 과제(FOLLOW-UP, 비차단): 상담 데이터 보존/삭제/고지/암호화 정책.
- 사람 검토 권고: 공개 서비스 전환 시 개인·의료정보 취급(§5), 의존성 취약점 스캔(§6).

### 참고: 클라이언트 XSS (static/, scope 밖 — 관측만)

`static/app.js`의 `addMessage()`는 `li.textContent = text`로만 렌더한다(`innerHTML` 미사용). LLM 응답에 HTML/스크립트가 섞여도 텍스트로만 표시되어 XSS로 전이되지 않음. 현재 안전 — 별도 수정 불필요.
