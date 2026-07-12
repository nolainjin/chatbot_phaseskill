# gui-uplift — GUI 업리프트 (참조 이미지 수준 재스타일)

재활병원 의사 시연용 접수 면담 챗봇의 GUI를 `docs/design/gui-reference.png` 수준으로
재스타일한다. 직전 커밋 b90f71f의 슬롯 진행 패널(API additive intake 필드)을 기반으로
확장 — 딥틸 비주얼 전면(Phase 2), intake 파생 3단계 스테퍼(Phase 3), 첫 턴 퀵리플라이
칩(Phase 4), playwright 브라우저 스모크(Phase 5).

## 핵심 결정

- **GET /api/config 추가** (사용자 승인 2026-07-12): 첫 턴 칩·스테퍼 노출 판단(스키마
  유무)을 로드 시점에 알아내는 읽기 전용 프로브. 엔진 수정은 이것 하나로 한정.
- **스테퍼 ③ 검증 방식**: fake 추출기는 signals 없는 슬롯(chief_complaint)을 못 채워
  fake 라이브에서 ③ 도달 불가(코드 확증) — 파생 규칙을 순수 함수
  `window.lmwikiDeriveStep`으로 노출하고 playwright 합성 단언으로 3상태 전부 커버.
  실모드는 스키마 계약상 ③ 도달 가능.
- **fail-closed**: config fetch 실패 시 스테퍼·칩 미노출 유지(공유 플래그
  intakeSchemaActive 기본 false) — knowledge-alt 스왑 회귀와 동일 상태로 수렴.

## 불변 제약

- API 계약 {reply, turn, limit_reached} 무변경, intake 필드 additive 유지
- knowledge-alt(스키마 없는 지식셋)에서 패널·스테퍼·칩 미노출
- 원칙적으로 static/ 3파일만 수정 (예외: 승인된 /api/config + tests)
- 봇 말투·이모지는 _persona.md 소유 — 불가침

## 검증 환경

- 테스트: `.venv/bin/python -m pytest` (시스템 pytest는 수집 에러)
- 구동: `MODEL=fake KNOWLEDGE_DIR=knowledge .venv/bin/python -m uvicorn app.main:app`
- rate limit: IP당 신규 세션 5개/시간(디스크 영속) — 브라우저 검증은 sessionStorage
  `lmwiki_session_id` 고정값 재사용
- 스크린샷: playwright chromium-1228(~/.claude 캐시) + 스크래치패드 npm i playwright
