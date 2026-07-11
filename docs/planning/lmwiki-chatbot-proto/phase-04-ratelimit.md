---
phase: 4
title: IP rate limit + 사용량 상한
status: completed
depends_on: [2]
scope:
  - app/ratelimit.py
  - app/main.py
  - tests/test_ratelimit.py
intervention_likely: false
intervention_reason: ""
executor: sonnet
load_bearing: ""
e2e_refs: []
e2e_triggers: []
phase_context:
  baseline: "missing"
  adoption: "bootstrap"
  coverage: "standard"
  enforcement_during_run: "warn"
  materialize_at: "finalization"
---

# Phase 4: IP rate limit + 사용량 상한

> **범위**: Backend
> **난이도**: S
> **의존성**: Phase 2
> **영향 파일**: `app/ratelimit.py` (신규), `app/main.py` (미들웨어 등록)

## 배경

origin §6: 동일 IP는 1시간에 5회 이상 사용 불가 + API 비용 공격 방지. '5회'의 단위는 사용자 확정(2026-07-11, D05)으로 **신규 대화 세션 5회**다. 사용자 재확인(2026-07-11): 이 제한의 목적은 해킹·프롬프트 인젝션·비용 공격 방어 — 세션 5회 + 10턴 캡(시간당 최대 50 호출) + DAILY_REQUEST_CAP 조합이 비용 방어를 담당하고, 프롬프트 인젝션 자체는 Phase 7 점검 항목 3이 담당한다. capabilities.md 적대적 플래그(CAP13)는 "코드만 있고 실제 6번째가 차단되지 않는" fake-satisfy를 경고한다. 스펙 리뷰에서 세 가지 견고성 결함이 지적되어 반영됐다: XFF 신뢰 홉수 env화(O3), 카운터 파일 원자적 쓰기+락(O4), hops=0 오구성 경고(O7).

## 심볼 인벤토리

- `app.ratelimit.RateLimiter`
  - [NEW]
- `app.ratelimit.client_ip`
  - [NEW]

## 설계

```
client_ip(request):
    hops = TRUST_PROXY_HOPS (기본 0)
    hops == 0 → 소켓 원격 주소 그대로 (XFF 무시. 단, XFF가 관측되면 경고 로그 1회
                — 프록시 뒤인데 설정을 안 한 오구성 신호)
    hops >= 1 → X-Forwarded-For 오른쪽에서 hops번째 주소 사용 (그 밖은 불신)

RateLimiter (신규 세션 시작 시에만 카운트):
    창 = 최근 1시간 타임스탬프 목록 (IP별)
    len(창) >= 5 → 429 + 안내 메시지
    전역 일일 카운터 >= DAILY_REQUEST_CAP(기본 500) → 429  # 비용 캡
    상태는 data/ratelimit.json 에 영속:
        쓰기 = tmp 파일에 쓰고 os.replace (원자적), threading.Lock으로 직렬화
        # ponytail: 단일 uvicorn 워커 전제 — 수평 확장 시 외부 스토어로 교체
```

- 기존 세션의 후속 발화는 rate limit 카운트에 넣지 않는다(10턴 캡이 이미 상한). 429 응답은 사람이 읽을 안내문을 담는다.

## 체크리스트

- [x] app/ratelimit.py: IP당 1시간 슬라이딩 윈도우로 신규 대화 세션 5회 제한 (사용자 확정 2026-07-11: '5회'는 대화 세션 단위), 카운터를 data/ratelimit.json에 영속(재시작 내성) — 원자적 쓰기(tmp+rename)+프로세스 내 락, 단일 uvicorn 워커 전제 명시(# ponytail: 단일 워커 전제, 수평 확장 시 외부 스토어)
- [x] 클라이언트 IP 판별: TRUST_PROXY_HOPS env(기본 0 = 소켓 주소 직접 사용)로 XFF 신뢰 홉수 설정 — raw VM 직노출(0)과 PaaS 프록시(1)를 모두 안전하게 지원, 스푸핑 차단 테스트 포함
- [x] 전역 일일 요청 상한 env DAILY_REQUEST_CAP(기본 500) — API 비용 방어
- [x] TRUST_PROXY_HOPS=0인데 X-Forwarded-For 헤더가 관측되면 기동/요청 시 경고 로그 (프록시 뒤 미설정 오구성 감지)
- [x] 초과 시 429 + 안내 메시지
- [x] tests/test_ratelimit.py: 6번째 세션 차단·윈도우 경과 후 해제·일일 캡·TRUST_PROXY_HOPS별 XFF 스푸핑 차단 테스트 통과

## 영향 범위

main.py에 미들웨어/의존성 1곳 등록. Phase 5 UI가 429 응답을 표시하고, Phase 8 배포 체크리스트가 실환경 차단·독립 클라이언트 카운트를 재검증한다. Phase 3과 파일이 겹치지 않아 병렬 실행 가능.

## 검증

```bash
.venv/bin/python -m pytest tests/test_ratelimit.py -q
```

## 실행 결과

### 1회차 (2026-07-11 13:56 KST) — completed

**상태**: completed
**소요 시간**: 약 20분
**진행 모델**: Claude sonnet

#### 요약

`app/ratelimit.py`를 신규 작성해 `client_ip()`(TRUST_PROXY_HOPS 기반 XFF 신뢰 홉수 판별 + hops=0인데 XFF 관측 시 프로세스당 1회 경고 로그)와 `RateLimiter`(IP별 1시간 슬라이딩 윈도우 신규 세션 5회 제한 + 전역 일일 DAILY_REQUEST_CAP, data/ratelimit.json에 tmp+rename 원자적 쓰기 + threading.Lock으로 영속)를 구현했다. "신규 세션"은 RateLimiter 자체가 관리하는 `known_sessions` 맵으로 판별해 chat.py 내부 상태(`_sessions`)에 의존하지 않도록 분리했다 — Phase 3가 병렬로 chat.py를 수정 중이라 커플링을 피했다. main.py는 기존 `/api/chat` 라우트에 rate limit 체크를 추가만 했고(요청 검증 이후, chat.handle_message 호출 이전), 초과 시 429 + 안내 메시지를 반환한다. daily_cap은 매 요청 Settings.from_env()로 새로 읽어 기존 코드 패턴(테스트의 monkeypatch.setenv 방식)과 일관되게 유지했다.

#### 변경 파일

- `app/ratelimit.py` (+127/-0, 신규)
- `app/main.py` (+12/-4)
- `tests/test_ratelimit.py` (+112/-0, 신규)

#### 검증 결과

- `.venv/bin/python -m pytest tests/test_ratelimit.py -q` → 9 passed
- `.venv/bin/python -m pytest -q` (전체 스위트, Phase 3/5 병렬 산출물 포함) → 28 passed, 회귀 없음
- `git diff -- app/main.py` 확인 — 순수 additive, Phase 3/5와 충돌 없음

#### 추가 발견사항

- 없음(스코프 내 완결). data/ratelimit.json은 .gitignore에 이미 등록돼 있어 커밋 걱정 없음.

#### 질문 / 결정 사항

- 설계 문서의 "RateLimiter (신규 세션 시작 시에만 카운트)"라는 괄호 설명을 창(윈도우)과 일일 캡 둘 다에 적용되는 것으로 해석했다 — 즉 DAILY_REQUEST_CAP도 신규 세션 시작 시에만 증가하고 세션 내 후속 발화(최대 10턴)는 카운트하지 않는다. origin §6 의도(세션 5회 × 10턴 = 시간당 최대 50호출)와 일치하는 해석이라 판단해 사용자 확인 없이 진행. 다르게 의도했다면(예: 모든 메시지마다 daily_cap 소모) 후속 phase에서 조정 필요.
