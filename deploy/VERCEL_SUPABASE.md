# Vercel·Supabase 합성 시연 배포

2026-11-04 사용자가 요청한 외부 연결 후보. 기존 로컬 운영은 기본 동작을 유지한다.
`MAEUM_DATABASE_URL`이 있을 때만 Postgres를 사용하며 기존 `data/`는 업로드하지 않는다.

## 구조

- Vercel: `app/main.py` FastAPI, 기존 `static/` 챗봇 UI, Anthropic Messages API.
- Supabase Postgres: 비공개 `maeum.records` 테이블. 세션 상태, 날짜별 대화,
  동의·삭제 코드의 소금/해시, 해시로 남긴 삭제 표식·열람 기록, 요청 제한을 저장한다.
- 브라우저에는 DB 비밀번호, Claude API 키, 서비스 역할 키를 전달하지 않는다.
  Supabase Data API는 이 배포에서 사용하지 않으며, `anon`/`authenticated` 역할에
  스키마와 테이블 권한을 주지 않는다. RLS도 활성화한다.
- 원격 센터 관리 화면과 관리 API는 기존대로 404다. 공개 챗봇 연결을 검증하는
  범위이며, 센터별 로그인·권한·실제 내담자 운영 승인을 대신하지 않는다.

## 필수 환경변수

실제 값은 Vercel 프로젝트의 Environment Variables에 입력한다.
키 값은 소스, Git, 문서, 배포 로그 또는 채팅에 붙이지 않는다.

| 이름 | 값 또는 역할 |
|---|---|
| `MAEUM_DATABASE_URL` | Supabase Connect의 Transaction pooler URI, TLS 사용 |
| `ANTHROPIC_API_KEY` | 사용자가 제공하는 Claude API 키 |
| `MODEL` | `claude-haiku-5-5` (명시적 테스트에서만 `fake`) |
| `KNOWLEDGE_DIR` | `knowledge-maeum` |
| `PUBLIC_CHAT_UI` | `1` |
| `DAILY_REQUEST_CAP` | 초기 시연 `100`; 동의·후속 발화가 각각 요청에 포함됨 |
| `TRUST_PROXY_HOPS` | Vercel 프록시 뒤에서 `1` |
| `PARTICIPANT_TICKET_SECRET` | 32자 이상의 고정 난수; 배포마다 바꾸지 않음 |
| `CRON_SECRET` | 32자 이상의 난수; Vercel 보관 기간 작업 인증용 |

Vercel은 `VERCEL=1`을 제공한다. 이때 DB·서명 시크릿·Claude 키 누락이나
`auto`/CLI 모델 설정은 시작 단계에서 거부한다. API 호출에는 도구를 전달하지 않으며,
CLI subprocess 분기를 선택할 수 없다. Claude 호출은 요청당 45초, SDK 재시도 0회다.
한 발화에는 답변과 정보 추출 등 복수의 API 호출이 포함될 수 있다.

## 적용 순서

1. Supabase 무료 프로젝트를 만들고 `supabase/migrations/202611040001_cloud_store.sql`을
   해당 프로젝트에 적용한다. 앱 시작 시 DDL이나 자동 이관은 실행하지 않는다.
2. 합성 데이터로 `scripts/cloud_smoke.py`를 실행한다. DB URI는 환경변수 또는
   `--config`가 가리키는 별도 비공개 JSON의 `MAEUM_DATABASE_URL`에서 읽는다.
3. 검증한 Git 브랜치를 Vercel에 연결하고 필수 환경변수를 설정한 뒤 배포한다.
4. `/api/health`의 DB 연결, 실제 브라우저의 동의·Claude 응답·후속 대화,
   Supabase 대화 레코드, 삭제 결과와 원격 관리자 404를 확인한다.

## 일관성과 보관

같은 세션 요청은 Postgres advisory transaction lock을 먼저 얻고 상태를 읽는다.
기존 엔진의 임시 작업 사본과 대화 기록은 한 트랜잭션에서 저장되며, 실패 시 함께
롤백한다. 요청 종료 후 메모리 작업 사본은 제거한다. 실패한 모델 요청도 일일 예산을
소모하도록 요청 제한은 별도 짧은 트랜잭션에서 확정한다.
동시 처리 중인 같은 세션의 잠금은 최대 10초 기다리며 저장소 장애는 503으로 응답한다.
소규모 시연을 위한 구현이며, 각 요청의 DB 연결과 전체 보고서 투영 비용을 포함한
부하 시험을 수행한 것은 아니다.

원문과 모델 컨텍스트는 90일, 요약은 365일 보관 계약을 따른다. Vercel Cron이 매일
18:00 UTC에 인증된 `/api/maintenance/retention`을 호출한다. 삭제 코드나 세션 인증으로
요청하면 대화·세션·삭제 코드·확인 기록을 지우고 해시 표식만 남긴다.
직접 식별정보 치환은 정규식 기반이며 모든 개인정보가 익명화되었다는 보장은 아니다.

## 확인한 범위

로컬 기본 경로의 pytest 710개 통과. 새 Supabase 프로젝트에서 합성 시연으로
서로 다른 프로세스의 대화 지속, 세션 인증, 동시 발화의 턴 보존, 원문·컨텍스트 치환,
롤백, 보고서, 전역 요청 상한, 삭제, 90/365일 보관, 브라우저 DB 역할 차단 등
`scripts/cloud_smoke.py`의 16개 검사를 통과했다(`MODEL=fake`).
Claude 실제 응답과 Vercel 배포 후 브라우저 검증은 별도 실행 결과로 기록해야 한다.
