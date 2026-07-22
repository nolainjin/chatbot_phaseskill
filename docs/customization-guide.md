# 커스터마이징 가이드

이 가이드는 `knowledge-alt`를 복사해 새 교육용 챗봇 pack을 만드는 절차다.
기본 전제는 `MODEL=fake`, synthetic data, localhost-only, no-PII,
non-production 교육 환경이다.

## 1. starter pack 복사

```bash
cp -R knowledge-alt knowledge-my-demo
```

새 pack 이름은 `KNOWLEDGE_DIR`로 지정한다.

```bash
MODEL=fake KNOWLEDGE_DIR=knowledge-my-demo \
  .venv/bin/python -m uvicorn app.main:app --reload
```

## 2. 파일 역할

공통 필수 파일:

- `_persona.md`: 챗봇 역할과 금지 범위
- `_tone.md`: 응답 말투
- `_safety_protocol.md`: 교육용 경계, 개인정보 금지, 인젝션 대응

접수 모드에서만 필요한 파일:

- `_intake_schema.md`: 수집할 슬롯, 질문 순서, fake 신호어
- `_validation_scenario.json`: validator가 실행할 대표 fake 대화

추천 파일:

- 도메인 지식 문서 `*.md`: frontmatter와 H1 제목을 포함한 합성 문서

선택 파일:

- `docs/`의 운영 설명 문서
- `scripts/gui-smoke`의 브라우저 검증 스크린샷

## 3. 모드와 schema 수정

`_intake_schema.md`를 넣으면 접수 모드가 활성화된다. 실제 지식 전달이나 코칭이
목적이면 이 파일을 만들지 않고, 문서 검색 결과와 `_persona.md`의 코칭 지시를
그대로 사용한다.

`_intake_schema.md`의 슬롯 `id`, `label`, `values`, `signals`, `ask`를 새
도메인에 맞게 수정한다. `when`과 `unless`는 `slot=value` 형식이어야 하며,
참조하는 slot id와 value가 실제로 존재해야 한다.

`_validation_scenario.json`에는 fake mode에서 모든 활성 슬롯이 채워지는
대표 메시지를 넣는다.

```json
{
  "session_id": "knowledge-alt-validator",
  "model": "fake",
  "messages": ["드립 커피를 처음 배워보고 싶어요."],
  "expect_unfilled_empty": true
}
```

## 4. 검증 명령

```bash
.venv/bin/python scripts/check_dependencies.py
.venv/bin/python scripts/validate_knowledge_pack.py knowledge-alt --json
MODEL=fake .venv/bin/python scripts/validate_knowledge_pack.py knowledge-alt --exercise
.venv/bin/python -m pytest -q
```

외부 cwd와 포트 변경 smoke:

```bash
(cd /tmp && bash /Volumes/부부공용/worknote/lmwiki-chatbot/scripts/smoke_local.sh)
PORT=8944 bash scripts/smoke_local.sh --pack knowledge-alt
```

브라우저 smoke:

```bash
cd scripts/gui-smoke
node gui-smoke.mjs
```

`MODEL=fake`는 결정론 상태·안전 계약의 gate이지 모델 자연어 품질의 증명이 아니다.
실제 모델은 12~20개 표본만 별도 실행하고, `knowledge-math` 150명 fake gate는 기존
`scripts/math_student_eval.py --out` 명령을 그대로 사용한다.

## 5. 운영 경계

이 repo의 기본 pack은 교육용이다. 실제 개인정보, 주문, 결제, 의료·법률 판단,
공개 서비스 배포에는 별도 보안 검토, 동의 절차, 로그 보존 정책, 접근 통제,
전문가 검토가 필요하다. `_safety_protocol.md`는 승인서가 아니라 데모 경계
문서다.
