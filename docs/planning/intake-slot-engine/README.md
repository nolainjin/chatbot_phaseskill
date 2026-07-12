# intake-slot-engine — 슬롯 스키마 문진 엔진 + 상담 접수면담 데모

부모 task `lmwiki-chatbot-proto`의 후속. 미실행 Phase 10(D10 선형 단계 스크립트)을 supersede한다.

## 무엇을 만드나

지금 봇은 `_persona.md` 산문 정책만으로 10턴 면담을 자유 진행해 필수 항목 누락을 막을 장치가 없다. 이 task는 "무엇을 수집할지"를 코드가 아닌 knowledge 데이터로 선언하는 도메인 무관 문진 엔진을 추가한다:

- `knowledge/_intake_schema.md` (언더스코어 예약 파일)에 수집 슬롯 선언 — 공통/조건부(활성 조건)/필수·선택/우선순위/레드플래그/signals
- 매 턴 시스템 프롬프트에 채워진/미충족 슬롯(우선순위순) 주입, 한 발화 다중 슬롯 동시 추출, 레드플래그 우선 질문, 10턴 예산 소비
- 종료 시 intake_summary를 구조화 JSON으로 저장 (미확인 슬롯 표기)
- 스키마 부재·형식 오류 → 기존 페르소나/Q&A 폴백 (knowledge-alt 스왑 invariant 유지)
- 기존 상담 지식 6종에서 도출한 3-트랙(정서/관계/위기) 스키마 + fake 모드(API 키 불필요) 의사 시연 데모

최종 고객은 재활병원 의사(초진 문진, 트랙: 암재활/근골격/자율신경)지만 엔진은 범용 — 재활 지식셋(knowledge-rehab/) 제작은 시연 후 후속 task로 명시적 scope 제외.

## Phase 구성 (7개, 직렬)

1. 스키마 파서 + 슬롯 모델 (`app/intake.py`)
2. 상담 3-트랙 스키마 + 페르소나 소유권 정리
3. fake 슬롯 루프 통합 (`app/chat.py` 배선)
4. 실모드 단일 호출 추출 + 신뢰 경계 검증 (D02)
5. 구조화 JSON 요약 + 기존 테스트 정합
6. fake e2e 4종 + 스왑 회귀
7. 데모 시나리오 문서 + README + 부모 supersede 메모

성공 기준: fake e2e 4종(정서/관계/위기 레드플래그 우선/혼합 다중 슬롯) 통과 + knowledge-alt 스왑 회귀 없음 + 전체 pytest 통과. CAP 원장 25종은 [capabilities.md](./capabilities.md), 리뷰 이력은 [spec-review.md](./spec-review.md) 참조.

## 실행

```bash
/phase-run intake-slot-engine
```
