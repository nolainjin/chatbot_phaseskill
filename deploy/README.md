# 배포 가이드

## 현재 운영 경계 (2026-08-01)

현재 승인된 운영은 **1주일 동안의 개인 Mac 로컬 전용 시연**이다. 안전 기본값은
`MODEL=fake`이며, 실제 시연은 개인 Codex 로그인으로
`MODEL=codex-cli:gpt-5.6-luna`와 `high` 강도를 사용한다. 두 경로 모두
loopback에서만 접근하며 공개 도메인·공개 ingress·Railway/Cloudflare 배포는
현재 차단한다. fixture, 회귀 테스트, bounded loopback API, 비공개 Luna 응답을
함께 검증 근거로 사용한다. API 키나 시크릿을 입력하지 않는다.

공개 전환은 이 문서의 절차를 실행하는 것으로 승인되지 않는다. 별도의 진짜
**no-tool** 아키텍처 또는 API adapter를 설계·검토하고, 보안·운영 재승인을
받은 뒤에만 진행한다. read-only sandbox는 도구가 없다는 뜻이 아니므로, 도구
권한은 sandbox 표기와 별도로 명시적으로 제거·검증해야 한다.

## 향후 공개 배포 참고용 격리 절차

아래 Railway/Fly.io/VM 절차는 향후 재승인된 공개 전환을 위한 참고 자료일 뿐,
현재 실행 지침이 아니다. 시크릿은 어떤 명령·문서·이미지에도 기록하지 않는다.

## 공통 사항

### 환경변수

`.env.example` 기준. 실제 값은 플랫폼의 env/secret 설정 화면에 입력한다 —
`.env` 파일을 이미지에 굽거나 리포에 커밋하지 않는다(`.dockerignore`,
`.gitignore` 둘 다 `.env` 제외).

| 변수 | 필수 | 설명 |
|---|---|---|
| `ANTHROPIC_API_KEY` | 재승인된 Claude API adapter에만 필수 | Claude API 키 — 현재 fake 운영에서는 설정 금지 |
| `KNOWLEDGE_DIR` | 선택 (기본 `knowledge`) | 지식 디렉토리 — 이미지에 `knowledge/`가 빌드타임에 포함됨 |
| `MODEL` | 선택 (기본 `fake`) | 개인 Mac loopback 시연만 `codex-cli:gpt-5.6-luna`/high로 명시적 override; 공개 API adapter는 재승인 필요 |
| `TRUST_PROXY_HOPS` | 선택 (기본 `0`) | 플랫폼별 권장값은 아래 표 참고 |
| `DAILY_REQUEST_CAP` | 선택 (기본 `500`) | 전역 일일 요청 상한 |
> 현재 개인 loopback 운영에는 `ANTHROPIC_API_KEY`가 필요하지 않다. 이 표의
> 공개 플랫폼/API adapter 지침은 재승인된 공개 전환 때만 검토한다.

### 영속 볼륨

`data/` 디렉토리(컨테이너 경로 `/app/data`) 하나에 `ratelimit.json`,
`conversations/YYYY-MM-DD/*.json`, `chatlog.db`가 전부 들어간다. 이 경로가
재시작 후에도 남아있지 않으면 rate limit·대화 이력·배치 적재 결과가 전부
날아간다 — **반드시 영속 볼륨/디스크를 `/app/data`에 붙인다.**

### 배치(일 1회 SQLite 적재) 실행

이미지에 별도 ENTRYPOINT가 없으므로 같은 이미지의 CMD를 오버라이드해서
배치를 돌린다. 웹 서비스와 배치가 컨테이너 내부에서 같은 `/app/data`를
봐야 하므로, 배치도 웹 서비스와 **동일한 볼륨/디스크**를 마운트해서 실행한다.

```bash
docker run --rm -v <host_or_platform_data>:/app/data <image> \
  python scripts/load_to_sqlite.py            # 기본: 어제 날짜
docker run --rm -v <host_or_platform_data>:/app/data <image> \
  python scripts/load_to_sqlite.py --date 2026-07-11   # 특정 날짜 재실행(멱등)
```

### TRUST_PROXY_HOPS

`app/ratelimit.py`의 `client_ip()`는 `TRUST_PROXY_HOPS=0`이면 소켓 원격
주소를 그대로 쓰고(X-Forwarded-For 완전 무시), `>=1`이면 그 hop 수만큼
XFF 오른쪽에서 신뢰 가능한 IP를 뽑는다. 값이 실제 프록시 hop 수보다 작으면
클라이언트가 IP를 스푸핑해 rate limit을 우회할 수 있고, 값이 크면 모든
요청이 같은 IP로 뭉뚱그려져 rate limit이 과도하게 걸린다 — **플랫폼의 엣지
프록시 구조와 정확히 맞춰야 한다.**

> **격리됨 — 미래 공개 전환 전용:** 아래 플랫폼 지침은 현재 사용하거나 적용하지
> 않는다. 별도 no-tool 아키텍처/API adapter와 보안·운영 재승인 후에만 사용한다.
## Railway (Hobby, $5/월 고정)

- 근거: `https://docs.railway.com/pricing/plans` (2026-07-11 확인) — 영속
  Volume(~$0.15/GB·월) + 서비스 내장 Cron Schedule + spin-down 없음.
- 배포: 리포 루트의 `Dockerfile`을 그대로 인식(Railway가 자동 빌드). 서비스
  생성 시 "Deploy from Dockerfile" 선택.
- 볼륨: 서비스 설정 > Volumes에서 마운트 경로를 `/app/data`로 지정해 attach.
- 배치: 서비스 설정 > Cron Schedule에 새 크론 잡 등록. 커맨드는
  `python scripts/load_to_sqlite.py`, 스케줄은 `0 3 * * *`(매일 03:00) 권장.
  같은 서비스/같은 볼륨을 참조하므로 별도 `docker run` 불필요.
- env: Variables 탭에 위 공통 환경변수 입력.
- **TRUST_PROXY_HOPS=1** — Railway 엣지 프록시가 XFF에 1홉을 추가한다.
- 참고: "월 $1 크레딧 Free 플랜" 존재 여부는 문서 간 상충(research.md
  Remaining Uncertainty) — 가입 화면에서 실제 청구 방식 재확인.

## Fly.io (월 $5~10)

- 근거: `https://fly.io/docs/about/pricing/` (2026-07-11 확인) — 2024-10
  이후 신규 무료 티어 없음(트라이얼만). Volumes $0.15/GB·월 + 머신 초 단위
  과금. 소형 상시 구성 월 $5~10.
- 배포: `fly launch` (Dockerfile 자동 인식) 또는 `fly deploy`.
- 볼륨: `fly volumes create data --size 1` 로 생성 후 `fly.toml`의
  `[mounts]`에 `source = "data"`, `destination = "/app/data"` 지정.
- 배치: Fly.io는 서비스 내장 크론이 없다. 둘 중 하나를 쓴다.
  - **스케줄 머신**: `fly machine run <image> --schedule daily
    --command "python scripts/load_to_sqlite.py"` (같은 앱의 볼륨을 재마운트)
  - **외부 크론 트리거**: 외부 스케줄러(예: GitHub Actions cron, cron-job.org)가
    HTTP로 볼 수 있는 별도 관리 엔드포인트를 앱에 만들어야 하므로, 앱 코드
    무수정 제약(이 phase 영향 범위) 하에서는 스케줄 머신 방식을 우선 권장.
- env: 승인된 secret store에서 환경변수를 주입한다. 키 값은 명령행·셸 히스토리·문서에 넣지 않는다.
- **TRUST_PROXY_HOPS=1** — Fly.io Anycast 엣지가 XFF에 1홉을 추가한다.

## Oracle Always Free VM ($0)

- 근거: `https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm`
  (2026-07-11 확인) — 진짜 영구 무료: AMD Micro VM 2대(1GB RAM) 또는 Ampere
  A1 + 영속 블록 스토리지 200GB. 단 2026-06경 스펙 무공지 축소 전례(정책
  리스크, research.md 참고).
- 배포: VM에 Docker 설치 후,
  ```bash
  docker build -t lmwiki-chatbot .
  mkdir -p /opt/lmwiki-chatbot/data
  docker run -d --name lmwiki-chatbot -p 8000:8000 \
    -v /opt/lmwiki-chatbot/data:/app/data \
    --env-file .env \
    lmwiki-chatbot
  ```
- 볼륨: VM 로컬 디스크 경로(`/opt/lmwiki-chatbot/data`)를 `-v`로 바인드
  마운트 — 진짜 블록스토리지라 재시작·재배포에도 그대로 남는다.
- 배치: VM은 실제 리눅스라 시스템 crontab을 그대로 쓴다.
  ```cron
  0 3 * * * docker run --rm -v /opt/lmwiki-chatbot/data:/app/data lmwiki-chatbot python scripts/load_to_sqlite.py
  ```
- **TRUST_PROXY_HOPS=0** — 앱 앞에 별도 리버스 프록시를 두지 않고 uvicorn에
  직접 접속한다는 전제. HTTPS 공개 URL이 필요해 nginx/Caddy 같은 리버스
  프록시를 앞단에 얹으면 XFF가 1홉 추가되므로 **TRUST_PROXY_HOPS=1로
  변경**해야 한다(둘 다 붙이는 게 프로토타입이라도 권장 — Caddy는 도메인만
  있으면 자동 TLS 발급).
- 리스크: 서버 OS 패치·방화벽·Docker 설치를 직접 관리해야 함(Phase 7 보안
  검토 항목과 별개로 인프라 하드닝은 사용자 책임).

## Hetzner CX23 VPS (€5.49/월, ~$6.49)

- 근거: `https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/`
  (2026-07-11 확인, 2026-06-15 인상 후 가격) — 2 vCPU/4GB/40GB NVMe, 유럽
  리전 기준. 진짜 VPS.
- 배포·볼륨·배치·TRUST_PROXY_HOPS: Oracle Always Free VM 섹션과 동일한
  절차(둘 다 표준 리눅스 VM + Docker + systemd crontab). 차이는 비용(월
  €5.49 고정)과 무료 티어 정책 리스크가 없다는 점뿐.
- Hetzner는 리전 선택이 자유로워 유럽 외 리전(가격 상이 가능, research.md
  Remaining Uncertainty) 선택도 가능.

## 현재 로컬 loopback 점검

현재는 공개 포트나 공개 URL을 열지 않는다. 안전 기본값 `MODEL=fake`로 결정론
회귀를 확인하고, 개인 테스트에서는 `MODEL=codex-cli:gpt-5.6-luna`로 비공개
loopback 응답을 확인한다. fixture, 전체 회귀, bounded API 세션 검증, Luna
응답을 함께 성공 판정 근거로 사용한다.

Docker 이미지 점검이 미래 전환에 필요하면 공개 포트 대신 loopback에만 바인딩한다.

```bash
docker build -t lmwiki-chatbot .
docker run --rm -p 127.0.0.1:8000:8000 -v "$(pwd)/data:/app/data" \
  -e MODEL=fake -e KNOWLEDGE_DIR=knowledge lmwiki-chatbot
```

`ANTHROPIC_API_KEY`를 전달하지 않는다. 이 리포 워커 환경(2026-07-11 Phase 8
실행분)에는 docker CLI가 설치돼 있지 않아 당시 Docker 스모크는 직접 실행하지
못했다. 공개 배포·유료 호출·외부 플랫폼 검증은 별도 no-tool 아키텍처/API
adapter와 재승인 전까지 차단 상태다.

### 향후 공개 재승인 시 상담 페르소나 게이트

현재 Luna CLI 허용은 개인 Mac의 loopback 테스트에만 해당한다. 공개 배포나
제3자 접근으로 확대하려면 별도 진짜 no-tool 아키텍처 또는 API adapter의
보안·운영 재승인이 필요하다. 아래 기록과 명령은 과거 평가 근거 및 향후 공개
재승인 참고용이다.

과거 scripted 400회 게이트 결과(2026-07-13): 400/400 성공, 트랙 정확도
400/400, 위기 재현율 80/80. 과거 Codex 파일럿(`crisis-hidden` 1회,
`gpt-5.6-luna`, bot=fake): 1/1 성공, 위기 재현 1/1, 소요 91초.
