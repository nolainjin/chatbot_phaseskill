# 기관 포털 클라우드 시험 후보

기존 `maeum-intake` 프로젝트에 연결할 후보 코드다. 이 문서의 존재는 배포나
실메일 인증 성공을 뜻하지 않는다. 로컬 사용법은 [PORTAL_LOCAL.md](PORTAL_LOCAL.md)를 따른다.

## 연결 계약

- 기존 Supabase 프로젝트 `ojhuuipsyxewtiubujom`과 Vercel 프로젝트
  `prj_E3EmUR9zhFQecS0VGPdjmmtEBHUR`를 재사용한다.
- `scripts/portal_cloud_prepare.py`는 기존 001 스키마를 전제로 schema-only 백업,
  신규 제한 역할, 002~005 migration 및 Auth 동기화 트리거를 적용한다.
  승인된 배포 작업에서만 실행한다. 비밀은 사용자 설정 폴더의 0600 파일에 저장한다.
- **배포의 `MAEUM_DATABASE_URL`에는 `PORTAL_ENGINE_DATABASE_URL` 값을 넣는다.**
  개인 설정 파일의 기존 owner URI를 복사하지 않는다. 클라우드 엔진은 실제 역할이
  `maeum_engine`인지, 소유자·superuser·BYPASSRLS가 아닌지 검사한다.
- 보고서와 인증 연결에는 각각 `PORTAL_DATABASE_URL` (`maeum_portal`),
  `PORTAL_AUTH_DATABASE_URL` (`maeum_auth`)을 사용한다.
- `PORTAL_ENABLED=1`, `PORTAL_AUTH_PROVIDER=supabase`, `PORTAL_LOCAL_TEST=0`,
  고정 HTTPS `PORTAL_ORIGIN`, 고정 `PORTAL_CODE_SECRET`, `SUPABASE_URL`,
  `SUPABASE_PUBLISHABLE_KEY`가 필요하다. 기본 챗봇 변수는
  [VERCEL_SUPABASE.md](VERCEL_SUPABASE.md)를 따른다.
- Supabase Auth의 허용 redirect는 확정된 origin의 `/portal/auth-return`으로 제한한다.
  Auth 사용자 UUID와 확정 이메일을 앱 사용자·기관 소속에 연결한다.

## 인증 동작과 한계

비밀번호 확인 후 최초·새 브라우저는 Supabase PKCE 이메일 링크를 요구한다.
확인 요청은 로그인 세션, nonce, challenge와 결합하고 성공 시 세션을 회전한다.
IP 변경만으로 기기 확인을 다시 요구하지 않는다. 공급자 토큰은 기기 확인 후 폐기한다.
공급자 비밀번호·이메일·정지·삭제 변경은 앱 세션과 신뢰 기기를 회수한다.
이미 앱에서 정지한 계정은 공급자 변경만으로 복원하지 않는다.

기본 SMTP 시험은 조직 Owner 주소 한 계정의 제한된 검증이다. 초대·비밀번호 변경·
이메일 변경의 로컬 기능은 cloud에서 닫는다. 다기관 운영용 계정 관리와 custom SMTP는
별도 연결이 필요하다. 콜백 query는 페이지에서 즉시 제거하지만 최초 HTTP 요청의
플랫폼 로그에 code/state가 절대로 남지 않는다고 보장하지 않는다.

## 현재 검증과 배포 전 남은 확인

2026-11-04 로컬 PostgreSQL disposable DB에서 44개 검사 통과. 기관 교차 접근,
메일 실패 시 제한 유지, PKCE 동시 단일 성공·실패 횟수·nonce·이전 challenge 무효화,
Auth 변경 시 회수, 정지 계정 유지와 owner 연결 거부를 포함한다. 공급자 HTTP는
모사했으며 실제 메일 수신 증거가 아니다. 원래 `data/` 해시 유지 확인.
기존 회귀는 710개 통과했고 신규 DB 검사는 기본 pytest 실행에서 44개 skip된다.

별도 격리된 실제 Claude 대화 시험에서 전달 완료·저장·세션 인증·삭제를 확인했다.
기대 항목의 질문 전 오추출과 제어 ID에 대한 과도한 전화번호 치환을 수정했다.

Supabase 대시보드 Database Settings에서 제공하는 공식 CA
`https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt`를
`supabase-ca.crt`로 보관했다. SHA-256은
`700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7`이다.
클라우드 인증·보고서·엔진 연결과 준비 스크립트는 이 CA로 `verify-full`을 강제한다.
2026-11-04 실제 기존 DB에서 스키마·제한 역할 적용, 엔진 저장/롤백,
인증·보고서 역할의 legacy records 접근 거부, 미인증 RLS 결과 0건을 확인했다.
Owner Auth 사용자를 합성 기관 A에만 연결했고 별도 합성 기관 B를 유지한다.

## 공개 시험 완료 (2026-11-04)

공개 주소는 https://project-4nww4.vercel.app/portal 이다. 기존 프로젝트에 배포했고
Gmail 시험 계정으로 실제 수신한 이메일 두 통을 사용해 최초·새 기기 PKCE를 완료했다.
같은 신뢰 기기 재로그인은 추가 메일 없이 성공했다. 로그아웃 후 목록은 401이었다.
실제 Claude로 6개 항목과 전달 완료를 진행해 7개 사용자 발화를 저장했다.
보고서 버전8의 요약·원문 출처·담당자 확인·미확인 집계 갱신을 브라우저에서 확인했다.
동일 번호의 합성 B 보고서에 대한 목록/집계는403, 교차 상세/원문/확인은404였다.
잘못된 CSRF는403, 잘못된 삭제 세션은401, 별도 시험접수 삭제코드는200이었다.
재배포 뒤에도 보고서·기대 답변·7개 사용자 발화·확인 이력이 유지됐다.
390px 화면 가로 넘침이 없었고 데스크톱/모바일 스크린샷을 직접 확인했다.
근거는 [실행 결과 JSON](evidence/portal-cloud-20261104.json)에 있다.

이는 Owner 한 계정과 합성 기관 자료에 대한 연결·기능 시험이다. 실제 기관 자료 이관,
다기관 계정 운영, 임상적 적합성 승인을 뜻하지 않는다. 기본 SMTP는 시간당2통이며
이번 시험에서 두 통을 사용했다. 일반 기관 운영에는 custom SMTP와 계정 관리 연결이 필요하다.
자동 Git 배포 연결은 설정하지 않았으며 현재 배포는 CLI로 수행했다.
