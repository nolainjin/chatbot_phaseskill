# Claude 키의 로컬 보관과 실행

macOS 터미널에서 실행한다. 실제 키를 명령 인수에 적지 않는다.

```sh
cd "/Volumes/부부공용/worknote/앱/lmwiki-chatbot"
sh scripts/claude_keychain.sh set
sh scripts/claude_keychain.sh status
```

`set`은 에코가 꺼진 터미널 입력으로 받아 macOS Keychain의
`com.maeum-intake.anthropic / ANTHROPIC_API_KEY`에 저장한다.
기존 항목이 있으면 같은 항목을 갱신한다. iCloud 동기화는 요청하지 않는다.
키를 소스·셸 기록·`.env`·배포 JSON에 기록하지 않는다.
`status`는 항목 존재만 확인하며 실제 API 유효성을 검증하지 않는다.

로컬 프로세스에 필요할 때만 키체인에서 읽어 환경변수로 전달한다.

```sh
sh scripts/claude_keychain.sh run -- .venv/bin/python -m uvicorn app.main:app
```

이 명령은 키 전달 예시다. 기존 서버의 실행 정책·DB·기타 환경변수 설정을 대신하지 않는다.
실행 대상은 신뢰하는 프로그램으로 제한한다. `env`나 환경변수를 출력하는 진단 도구를
실행 대상으로 지정하면 키가 출력될 수 있다.

키체인 암호화는 저장 중 보호다. 사용 시에는 키체인이 복호화한 값이 실행 프로세스
메모리와 자식 환경에 존재한다. 관리자 권한, 메모리 덤프, 악성 자식 프로그램까지
차단하는 기능은 아니다. 키체인 접근 확인 창이 뜨면 사용자 본인이 확인한다.
자체 암호화 파일과 같은 폴더의 복호화 키를 추가하는 방식은 사용하지 않는다.

Vercel은 다른 머신이므로 이 로컬 키체인을 읽을 수 없다. 서버 환경변수
`ANTHROPIC_API_KEY`를 Vercel의 **Secret**으로 별도 등록해야 한다.
로컬 저장 성공을 배포 등록·Claude 응답 성공으로 보고하지 않는다.
현재 도구는 Vercel로 자동 업로드하지 않는다.

검증: Swift 컴파일과 shell 구문 검사, 별도 selftest 키체인 항목에 합성 값의
숨김 입력·저장·자식 프로세스 전달을 확인했다. 합성 값은 결과 로그에 출력되지 않았으며
시험 항목을 제거했다. 실제 사용자 키·실제 Anthropic 호출은 시험하지 않았다.
