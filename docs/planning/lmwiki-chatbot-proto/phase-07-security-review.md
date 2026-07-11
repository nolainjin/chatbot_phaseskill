---
phase: 7
title: 보안 검토 + 하드닝
status: pending
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
6. 의존성: pip 패키지 알려진 취약점 여부 (pip-audit 가용 시)
```

high/critical은 이 phase에서 즉시 수정한다. 수정하지 않기로 한 항목은 사유와 함께 리스크로 남기고, 사람 보안 개발자 검토가 필요한 항목은 권고로 표시한다(origin의 '필요하면 보안 개발자 의견' 조건 대응).

## 체크리스트

- [ ] AI 보안 검토: 키 노출·입력 검증·프롬프트 인젝션(지식 문서/사용자 입력 경계)·rate limit 우회(XFF 스푸핑)·저장 데이터 취급 점검 → docs/security-review.md 기록
- [ ] high/critical 항목 즉시 수정, 미수정 항목은 리스크+권고(보안 개발자 검토 필요 여부 포함)로 문서화
- [ ] 리포 시크릿 스캔 통과 (git 히스토리 포함)
- [ ] tests/test_security.py: 과길이 입력 거부·비JSON content-type 거부 등 경계 테스트 통과

## 영향 범위

app/ 전반에 소규모 하드닝 수정이 들어갈 수 있다(scope에 app/ 포함). 수정 후 Phase 6 스모크·전체 테스트 재실행으로 회귀 확인. 롤백 = 개별 수정 단위.

## 검증

```bash
.venv/bin/python -m pytest tests/test_security.py -q
```
