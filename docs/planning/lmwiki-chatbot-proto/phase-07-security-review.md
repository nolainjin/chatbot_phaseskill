---
phase: 7
title: 보안 검토 + 하드닝
status: completed
depends_on: [6]
scope:
  - docs/security-review.md
  - app/
  - tests/test_security.py
intervention_likely: false
intervention_reason: ""
executor: opus
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

# Phase 7: 보안 검토 + 하드닝

> **범위**: Backend
> **난이도**: S
> **의존성**: Phase 6
> **영향 파일**: `docs/security-review.md` (신규), `app/` (지적사항 수정)

## 배경

origin §6: "보안상 추가 문제가 없는지 별도 검토. AI 검토뿐 아니라 필요하면 보안 개발자 의견도 확인." 배포(Phase 8) 직전에 전체 구현을 놓고 별도 검토 pass를 수행한다(CAP14). 검토가 "문제 없어 보인다" 한 줄로 뭉개지는 것이 적대적 플래그이므로, 점검 항목을 미리 고정하고 결과를 문서로 남긴다. executor를 opus로 올린 것은 보안 검토의 판단 품질 때문.

## 심볼 인벤토리

(없음)

## 설계

점검 고정 목록 (docs/security-review.md에 항목별 판정 기록):

```
1. 키 노출: 리포/히스토리/클라이언트 응답에 ANTHROPIC_API_KEY 흔적 없음 (git log -p 스캔)
2. 입력 검증: 길이 상한·타입 검증·비JSON content-type 거부가 실제 동작
3. 프롬프트 인젝션: 사용자 입력과 지식 문서가 시스템 지시를 덮어쓰지 못하는 경계 확인,
   지식 문서 출처가 신뢰 경계임을 문서화
4. rate limit 우회: XFF 스푸핑 시나리오 재점검 (TRUST_PROXY_HOPS 설정별)
5. 저장 데이터: 대화 JSON에 불필요한 식별자 저장 없음, data/ 접근이 앱 밖으로 안 새는지
   — 첫 도메인이 상담 초기 면담(사용자 확정 2026-07-11)이라 대화에 민감정보가 섞일 수 있음:
   이 항목을 가중 점검. 공개 서비스 전환 시 필요한 보존 기간·삭제 정책·고지 강화 항목을
   security-review.md에 후속 과제로 문서화 (현재는 내부 시연이라 비차단)
6. 의존성: pip 패키지 알려진 취약점 여부 (pip-audit 가용 시)
```

high/critical은 이 phase에서 즉시 수정한다. 수정하지 않기로 한 항목은 사유와 함께 리스크로 남기고, 사람 보안 개발자 검토가 필요한 항목은 권고로 표시한다(origin의 '필요하면 보안 개발자 의견' 조건 대응).

## 체크리스트

- [x] AI 보안 검토: 키 노출·입력 검증·프롬프트 인젝션(지식 문서/사용자 입력 경계)·rate limit 우회(XFF 스푸핑)·저장 데이터 취급 점검 → docs/security-review.md 기록
- [x] high/critical 항목 즉시 수정, 미수정 항목은 리스크+권고(보안 개발자 검토 필요 여부 포함)로 문서화
- [x] 리포 시크릿 스캔 통과 (git 히스토리 포함)
- [x] tests/test_security.py: 과길이 입력 거부·비JSON content-type 거부 등 경계 테스트 통과

## 영향 범위

app/ 전반에 소규모 하드닝 수정이 들어갈 수 있다(scope에 app/ 포함). 수정 후 Phase 6 스모크·전체 테스트 재실행으로 회귀 확인. 롤백 = 개별 수정 단위.

## 검증

```bash
.venv/bin/python -m pytest tests/test_security.py -q
```

## 실행 결과

### 1회차 (2026-07-11 22:30 KST) — completed

**상태**: completed
**소요 시간**: 약 20분
**진행 모델**: Claude opus

#### 요약

6개 고정 점검 항목을 실증 검토하고 `docs/security-review.md`에 항목별 판정으로 기록했다. high/critical급 취약점은 없었고, 발견한 유일한 실질 하드닝 항목(잘못된 session_id가 API 경계를 지나 storage 층에서 500으로 새던 입력 검증 갭)을 즉시 수정했다. 나머지는 PASS이거나, 코드로 못 막는 잔여 위험(LLM 프롬프트 인젝션) 및 공개 서비스 전환 시 필요한 후속 과제(상담 데이터 보존/삭제/암호화)로 문서화했다.

핵심 수정: `storage.valid_session_id()` 공개 헬퍼를 추가해 `main.py`(API 경계)와 `storage.append_turn`(저장 층)이 같은 화이트리스트 규칙 하나를 공유하도록 했다. 경계에서 불합격이면 400을 반환해 downstream 500 누출을 막는다.

#### 변경 파일

- `docs/security-review.md` (신규, +90/-0) — 6개 항목 판정 + XSS 참고 + 요약
- `app/main.py` (+5/-3) — session_id 화이트리스트 검증을 API 경계로 상향, 400 반환
- `app/storage.py` (+6/-1) — `valid_session_id()` 공개 헬퍼 추출, `append_turn`이 재사용
- `tests/test_security.py` (신규, +82/-0) — 과길이 입력·비JSON content-type·session_id 화이트리스트 경계 테스트 7건

#### 검증 결과

- `.venv/bin/python -m pytest tests/test_security.py -q` → **7 passed**
- 전체 스위트 `.venv/bin/python -m pytest -q` → **37 passed** (기존 30 + 신규 7), 회귀 없음
- 시크릿 스캔: `git rev-list --all` 전체 대상 `sk-ant-...` 매치 0건, `.env`/`data/` 히스토리 추적 이력 0건 → 통과
- 비JSON content-type: form-urlencoded·text/plain·빈 본문 실측 422 확인
- session_id 하드닝 전/후: `../../etc/passwd`·200자 입력이 수정 전 500 → 수정 후 400 확인

#### 추가 발견사항

- static/app.js는 `textContent`로만 렌더(innerHTML 미사용) → LLM 응답발 XSS 없음. scope 밖이라 수정 없이 관측만 기록(security-review.md 말미).
- `requirements.txt` 버전 미고정 + pip-audit 미설치 → 취약점 자동 조회 불가. 버전 핀 고정 + Phase 8(배포)에서 pip-audit 정기 실행을 권고로 문서화.
- 상담 도메인 민감정보: 현재 평문 저장·암호화 없음. 내부 시연이라 비차단, 공개 전환 시 보존기간/삭제/고지/암호화 + 사람 보안·법무 검토를 FOLLOW-UP/권고로 남김.

#### 질문 / 결정 사항

없음. 모든 항목 비차단 처리. 사람 보안 개발자 검토는 "공개 서비스 전환 시"로 조건부 권고(현재 내부 시연이라 불필요).

#### Commit
- `e2047df` fix(security): Phase 7 — 보안 검토 + session_id 경계 하드닝 (review pass — 시크릿 스캔·경계 하드닝 독립 재현, simplify 변경 0, 검증 재실행 pass)
