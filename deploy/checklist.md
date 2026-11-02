# 운영 검증 체크리스트

## 현재 승인 범위: 1주일 개인 Mac local-only 운영

안전 기본값은 `MODEL=fake`이며, 실제 개인 테스트는
`MODEL=codex-cli:gpt-5.6-luna`와 `high` 강도를 사용한다. 두 경로 모두 private
loopback 전용이다. 공개 URL·공개 ingress·Railway/Cloudflare 배포는 현재
차단한다. API 키를 설정·전달·기록하지 않는다.

- [ ] 프로세스가 loopback에만 바인딩되고 공개 포트/도메인/ingress가 없는지 확인
- [ ] LaunchAgent가 `codex-cli:gpt-5.6-luna`와 `high` 강도로 기동되는지 확인
- [ ] 지정 fixture와 전체 회귀 테스트가 통과하는지 확인
- [ ] bounded loopback API에서 차단 입력 마스킹, 10턴 상한, 새 세션 1턴을 확인
- [ ] 비공개 Luna 응답이 비어 있지 않고 내부 런타임 정보를 노출하지 않는지 확인

## 향후 공개 배포 검증 (격리됨 — 현재 실행 금지)

다음 항목은 Railway/Cloudflare 등을 포함한 공개 전환이 별도의 진짜 **no-tool**
아키텍처 또는 API adapter로 설계되고 보안·운영 재승인을 받은 뒤에만 사용한다.
read-only sandbox 표기는 도구 부재를 보장하지 않으므로, 해당 전환에서 도구
권한의 명시적 제거와 검증이 선행되어야 한다. 시크릿은 문서·명령행·이미지·로그에
기록하지 않고 승인된 secret store로만 주입한다.

- [ ] 재승인된 공개 아키텍처/API adapter가 no-tool 경계를 명시하고 검증함
- [ ] Railway: 승인된 secret store와 `/app/data` 영속 볼륨을 연결하고, 키 값을
      콘솔 캡처·명령행·로그에 노출하지 않음
- [ ] Cloudflare: 공개 경로·TLS·원본 접근 제한 및 실제 프록시 hop 수를 설계
      검토에 기록하고 `TRUST_PROXY_HOPS` 검증에 반영함
- [ ] 플랫폼의 영속 볼륨이 `/app/data`에 연결되고 보존·삭제·접근 통제가 검토됨
- [ ] 실제 프록시 구조에 맞는 `TRUST_PROXY_HOPS`가 검증됨
- [ ] 공개 URL health 및 live-chat 검증은 재승인 범위와 비용 통제 안에서만 수행됨
- [ ] 공개 전환 결과와 보안 검토를 별도 변경 기록에 남김
