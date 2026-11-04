# 마음 접수 기관 포털 — 로컬 구현 및 검증

2026-11-04. 범위: 통합설계 P0~P4의 **로컬 구현**. P5 외부 연결과 배포는 수행하지 않았다.
기준: `feat/supabase-vercel-20261104`, 시작 HEAD `36710468b4c6eeac1cf8c6c0d26d74aa3140cc0e`, 앱 Git clean.
변경은 이 브랜치 작업 파일로 남아 있으며 자동 commit/push하지 않는다.

## 실행

저장소 루트에서:

```sh
cd "/Volumes/부부공용/worknote/앱/lmwiki-chatbot"
rtk .venv/bin/python scripts/portal_local.py serve
```

- 기관 포털: <http://127.0.0.1:8797/portal>
- 내담자: 포털에서 발급한 링크를 사용한다. 루트 주소만 열면 새 기관 접수를 만들 수 없다.
- 합성 A기관: `a0@example.test` 관리자, `a1@example.test` 상담사, `a2@example.test` 요약 전용.
- 합성 B기관: `b0@example.test` 관리자, `b1@example.test` 상담사.
- 생성된 로컬 시험 비밀번호: `~/.local/share/maeum-portal-test/accounts.txt`.
- 캡처 메일: 같은 디렉터리의 `mail/*.json`. 해당 계정의 최신 `purpose=device` 파일의 code를 로그인 화면에 입력한다.
  초대는 `purpose=invitation`, 이메일 변경은 `purpose=email_change`로 분리한다.
- 비밀번호·코드·초대 token·설정 JSON은 채팅이나 Git에 복사하지 않는다. 파일은 0600, 디렉터리는 0700.
- 앱은 Ctrl+C로 중지. 전용 시험 DB 중지는 `rtk .venv/bin/python scripts/portal_local.py stop`.
  `serve`는 기존 시연 자료를 보존해 재시작한다.
- `init`는 최초 클러스터/합성 기관 생성용이며 운영 설정 파일을 읽지 않는다.
- 이미 이 세션에서 PostgreSQL 17.11을 설치했다. 다른 환경에서는 `MAEUM_PG_BIN`으로 설치된 PostgreSQL bin 위치를 지정한다.
  실행 스크립트는 패키지 설치나 외부 DB 접속을 자동으로 하지 않는다.

실제 서버를 실행한 상태에서는 두 번째 serve를 띄우지 말고 위 URL을 연다.
메일 캡처 디렉터리는 HTTP로 제공하지 않는다. 공개된 코드 조회 기능으로 기기 인증을 우회하지 않도록 한 로컬 시험 경계다.

## 구현된 흐름

1. 담당자 이메일·비밀번호 확인. 최초·새 브라우저는 pending 세션으로 제한한다.
2. 등록 이메일용 8자리 코드를 캡처. 유효기간/시도/재전송 제한, 로그인·브라우저 nonce·목적에 결합한 MAC, 성공 시 세션 교체.
3. 확인된 담당자가 자신의 기관 링크 발급·회수. URL fragment의 난수 token을 첫 교환 후 주소에서 제거한다.
4. 기관명·전달 목적·기존 보관/삭제 고지를 확인한 뒤 동의. 링크 잠금과 동의 저장, 기관 불변 연결, 보고서 초기 투영이 같은 트랜잭션으로 처리된다.
5. 기존 대화 엔진이 저장한 intake_snapshot을 보고서에 투영. 원문은 legacy records에서 허용된 접수만 제한 함수로 읽는다.
6. 기관 목록·관리번호 검색·페이지 이동·행정 집계·상세·원문·담당자 확인 이력. 출처는 저장된 사용자 발화에 실제 포함된 값만 연결한다.
7. 자기 기기 회수, 기관 소속 회수/복원, 권한을 제한한 초대와 수락, 비밀번호 변경, 새 이메일 소유 확인 후 변경. 신원 변경은 기존 세션/기기를 모두 회수한다.
8. 삭제/보관과 보고서 읽기를 잠금으로 직렬화. 삭제된 접수의 링크는 다시 쓰지 못하고, 원문 만료 시 출처와 자유 서술 요청도 제거한다.

개인 기기 신뢰는 일반 로그인을 대신하지 않는다. IP는 남용 제한에만 사용하며 **IP 변경은 기기 재인증 조건이 아니다**.
초대 수락도 기기 인증을 대신하지 않는다. 보고서 열람 시 새 LLM 호출은 없다.
의학적 점수·새 진단·추천·기관 매칭 기능을 추가하지 않았다.

## 파일과 책임

| 파일 | 책임 |
|---|---|
| `app/portal_config.py` | 임시 정책, 기본 닫힘, 로컬 전용 플래그 |
| `app/portal_auth.py` | 로컬 비밀번호 어댑터, 캡처 메일, 세션/기기/코드/CSRF/제한 |
| `app/portal_store.py` | 비소유자 연결 검사, 기관 컨텍스트, 동의 결합, 보고서 투영·삭제 |
| `app/portal.py` | 로그인·기관 보고서·링크·기기·초대·계정 API |
| `app/main.py` | 기존 엔드포인트 연결, 로컬 경계·no-store, 라우터 등록 |
| `app/cloud_store.py` | 같은 트랜잭션의 투영, 원문 읽기/삭제 공통 잠금, 보관 정리 |
| `static/app.js` | 기관 링크 교환·동의, 같은 탭에서 새 링크 재진입 |
| `static/portal/index.html`, `app.js` | 기관 담당자 화면, 모바일 단일 열, 키보드·오류/빈 결과 처리 |
| `supabase/migrations/202611040002~004_*.sql` | 로컬 적용한 추가 스키마·복합 FK·RLS·역할 경계 후보 |
| `scripts/portal_local.py` | 전용 클러스터·합성 시연 DB·비밀 설정 생성/실행 |
| `tests/test_portal.py` | 별도 일회용 DB의 통합·권한·경합·오류 검사 |

## DB 경계

- 로컬 클러스터: `~/.local/share/maeum-portal-test/pg`, TCP `127.0.0.1:55439`, SCRAM 인증.
- 시연 DB `maeum_test_portal`과 검사마다 생성하는 `maeum_test_<run id>`를 분리한다.
  검사는 자기 DB만 삭제하며 기존 data/나 시연 DB를 초기화하지 않는다.
- `maeum_portal`: 비소유자·NOSUPERUSER·NOBYPASSRLS. records와 인증 테이블 직접 접근 없음.
- `maeum_auth`: 인증 전용. 보고서와 원문 직접 접근 없음.
- 서버가 검증한 세션 해시·user·org를 트랜잭션 한정 컨텍스트로 설정한다.
  DB 정책은 세션 verified/만료/회수, 사용자·기기·기관·회원 활성 및 개별 권한을 다시 검사한다.
- 포털은 기존 전체 `stats_snapshot()`을 사용하지 않는다. 기관/접수 인덱스를 이용한다.
- 원문 함수의 감사 INSERT 실패는 전체 요청을 실패시킨다.
- 기관 미지정 기존 records는 목록·보고서에 포함하지 않는다.
- 스키마를 기존 운영 DB에 적용하지 않았으며, 일반 앱 시작 때 migration을 실행하지 않는다.

RLS의 소유자/BYPASSRLS 우회 특성을 고려해 실제 제한 역할로 시험했다.
근거: [PostgreSQL 17 RLS](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).
Auth의 운영 연결은 [Supabase 비밀번호 인증](https://supabase.com/docs/reference/python/auth-signinwithpassword)을 기준으로 P5에서 별도 어댑터를 연결한다.

## 임시 정책과 설정

아래는 로컬 기본값이며 운영 정책 승인으로 해석하지 않는다. `PORTAL_<대문자 필드>` 환경변수로 바꾼다.

| 필드 | 기본값 |
|---|---:|
| DEVICE_SECONDS | 2592000 (30일) |
| IDLE_SECONDS | 1800 (30분) |
| SESSION_SECONDS | 28800 (8시간) |
| CODE_SECONDS | 600 (10분) |
| CODE_ATTEMPTS | 5 |
| RESEND_SECONDS | 60 |
| SENDS_PER_HOUR | 5 |
| LINK_SECONDS | 604800 (7일) |

공용 PC의 기기 기억은 기본 해제. 서버 세션이 살아 있는 동안만 확인된 기기를 연결한다.
원문 90일·요약 365일의 기존 계약은 유지한다. 감사 보관 기간은 운영 결정으로 남겨 둔다.

`PORTAL_ENABLED`는 기본 off. 켜더라도 `PORTAL_LOCAL_TEST=1`, loopback 호스트/peer,
loopback의 `maeum_test_` DB, `MODEL=fake`만 허용한다.
현재 로컬 HTTP 쿠키는 HttpOnly·SameSite=Strict·host-only이며 Secure=false다.
이는 운영 HTTPS 설정이 아니다. P5에서는 Secure 쿠키와 운영 어댑터가 준비된 뒤 별도 검증해야 한다.
`PORTAL_ORIGIN`과 CSRF 헤더를 함께 검사하고, 보고서 응답은 no-store다.

## 재실행과 검증 해석

```sh
# 기존 전체 회귀. 외부 DB 설정 없는 기본 모드.
rtk .venv/bin/python -m pytest -q

# 매 실행마다 별도 로컬 PostgreSQL DB 생성, 검사, 자기 DB만 제거
rtk .venv/bin/python scripts/portal_local.py test

rtk node --check static/app.js
rtk node --check static/portal/app.js
rtk git diff --check
```

- 시작 기준: 기존 710 passed (19.86s).
- 구현 후 기존 전체 회귀: 710 passed, 기관 검사 33 skipped (17.79s).
  skip은 기본 실행에 전용 DB 설정이 없기 때문이며 별도 실행 결과를 확인해야 한다.
- 마지막 동작 변경인 같은 탭의 새 기관 링크 처리 뒤 관련 기존 UI 회귀 69 passed (3.03s).
- 최종 기관 통합 검사: **33 passed (12.64s)**. 매 실행별 전용 PostgreSQL DB에서 수행했다.
- JS 문법 검사 2개, Python compileall, git diff --check 통과. 최신 코드 서버 재시작 및 HTTP 응답 확인.
- 현재 로컬 시연 DB에는 A/B의 동일 관리번호 D-101을 각기 다른 합성 대화로 저장했다. A는 전달 완료·확인 기록, B는 진행 중이다.
- pytest의 Starlette/httpx 사용 중단 예고 경고 1건은 기존 의존성 경고다. 테스트 실패는 아니다.
- 원래 data/의 파일별 SHA-256을 기관 검사 전후 비교했고 일치했다. 기존 전체 회귀의 data 보호 fixture도 통과했다.

| 설계 시나리오 | 이번 증거 |
|---|---|
| T01~T04 | A/B 동일 D-101, 교차 목록/집계/상세/원문/검토/링크·회원 차단, pending/미로그인, 요약 전용 |
| T05~T10 | 새 기기/공용 PC/다른 사용자, 같은 쿠키 IP 변경, OTP 만료·5회·재전송·동시 1회, 회수, CSRF, 권한 상승 거부 |
| T11 | 실제 runtime에서 records/인증 테이블 조회 거부, 검증된 세션 없는 DB 컨텍스트 거부, commit 뒤 컨텍스트 초기화 |
| T12 | 동의 거부 0건, 만료/회수, 동시 소모 1회, 동일 세션 토큰+요청 키 재시도만 허용 |
| T13 | 저장 snapshot/원문 일치, 실제 존재하는 발화 출처, 전달 완료, 새 Python 프로세스 동일 내용, 투영 실패 롤백 |
| T14 | 열람/확인 감사, 감사 실패 시 원문 미반환 |
| T15 | 삭제·원문 읽기·대화 경합, 90/91 및 365/366일 경계, 삭제 후 재등장 차단 |
| T16 | 캡처 메일/인증/DB/모델 오류 주입, 요청 제한, 정제 오류·권한 미부여 |
| T17 | 원격 legacy stats/admin/CSV 및 포털 404, no-store, 로그아웃 이후 신규 조회 차단 |
| T18 | 실제 Ego 브라우저: 로그인→코드→링크→동의→대화→전달→보고서/원문/출처/확인, 390px 가로 넘침 없음, 검색 빈 결과와 키보드 진입, A/B 내용 분리 |
| T19 | 비밀번호 변경, 새 이메일 소유 확인 전 불변·확인 후 세션 회수, 신뢰 만료 |
| T20 | 기존 회귀, 로컬 Postgres, 보관 endpoint 인증, data 보존 |

브라우저 검사 중 확인 집계의 즉시 갱신 및 같은 문서 내 새 링크 이동 문제를 고쳐 재검증했다.
스크린샷: `screenshots/portal-desktop-final.png`, `screenshots/portal-mobile.png` (합성 자료만, Git 제외).
UI 주 기능은 실제 클릭·입력으로 검사했고 화면도 직접 보았다. 모든 보조 관리 화면의 모든 조합을 수동 검증한 것은 아니다.

## P5 전 남은 연결과 사용자 선택

이번에는 외부 계정 설정, 운영 DB migration, 배포, 실제 메일 발송, Claude 호출을 하지 않았다.

1. **기존 프로젝트 재사용**: Supabase `maeum-intake / ojhuuipsyxewtiubujom`,
   Vercel `maeum-intake / prj_E3EmUR9zhFQecS0VGPdjmmtEBHUR`.
   ID는 기존 인계 기준이며 이번에는 외부 콘솔을 재조회하지 않았다. 프로젝트 신규 생성 금지.
2. **운영 담당자·역할 확정**: 담당자별 이메일 계정 여부, 첫 기관/관리자,
   원문 열람자·회원 관리자의 범위, 기기/세션/보관·감사 정책, 분실/퇴사 대응 책임.
3. **메일 선택**: 공급자, 발신 계정·도메인, 회신 주소, DNS 작업 권한과 비용 범위.
   Supabase Auth용 메일과 앱 기기 코드 발송 어댑터를 각각 구성하고 실제 전달·실패·제한을 시험.
4. **Auth 연결 구현**: 로컬 scrypt 어댑터를 Supabase Auth로 교체, auth.users와 로컬 사용자 ID 매핑/FK,
   초대·재설정·이메일 변경의 공급자 이벤트와 앱 auth_version/기기 회수 동기화.
   지금의 합성 계정 파일을 운영에 올리지 않는다. SDK 선택·버전 고정도 이 단계에서 수행.
5. **DB 운영 역할/백업**: 후보 SQL 검토, 권한을 분리한 운영 역할과 별도 preview DB,
   백업·복구 및 회수 절차. 로컬 DSN·시험 DB·테스트 비밀번호를 외부로 옮기지 않는다.
6. **사용자 비밀 입력**: Claude API 키, 운영 DB/Auth/메일 비밀, 고정 서명/MAC/cron 값은
   선택된 기존 프로젝트의 비밀 환경변수에 직접 입력. 채팅/Git에 입력하지 않는다.
7. **배포 승인 뒤 검증**: HTTPS Secure 쿠키, 정확한 Origin·프록시·캐시·로그 설정,
   실제 메일/Claude 응답, 재배포 이후 지속, 실제 Supabase 역할의 A/B 격리,
   모바일 공개 URL E2E와 복구 절차를 확인한다.

현재 MODEL=fake는 저장·인증·화면 연결 검증용이다. 실제 Claude 요약의 의미 정확성이나
임상 안전성, 기관 운영 승인을 대신하지 않는다. 모든 기존 16개 클라우드 검사 결과는
이번 로컬 기관 기능의 새 검증 수치로 포함하지 않았다.
