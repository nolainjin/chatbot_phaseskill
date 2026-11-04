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

남은 필수 단계는 Vercel CLI 인증, Supabase 공식 CA 확보 후 TLS 호스트 검증,
운영 schema/제한 역할 적용 및 실제 역할 검사, Auth 사용자 연결, 환경변수 등록,
정확한 버전 배포, 공개 HTTPS에서 이메일 링크와 보고서 흐름 검증이다.
이 단계들이 끝나기 전 실서비스 연결 완료로 보고하지 않는다.
