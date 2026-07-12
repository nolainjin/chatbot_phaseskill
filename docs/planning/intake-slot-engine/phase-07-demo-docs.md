---
phase: 7
title: 데모 시나리오 문서 + README + 부모 supersede 메모
status: completed
depends_on: [6]
scope:
  - docs/demo-scenario.md
  - README.md
  - docs/planning/lmwiki-chatbot-proto/checklist.md
intervention_likely: false
intervention_reason: ""
executor: haiku
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

# Phase 7: 데모 시나리오 문서 + README + 부모 supersede 메모

> **범위**: 문서 전용
> **난이도**: XS
> **의존성**: Phase 6
> **영향 파일**: `docs/demo-scenario.md` [NEW], `README.md`

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 배경

의사 시연용 데모 대본을 리포 문서로 남기고(위치는 사용자 결정 2026-07-12: docs/demo-scenario.md + README 링크), 부모 task 정리를 마감한다. origin이 요구한 bookkeeping — "기존 Phase 10(선형 단계 스크립트, D10)은 미실행 상태로 이 요청이 대체(supersede)한다. 기존 task checklist의 cross-phase 메모에 supersede 기록을 남길 것" — 은 코드 작업에 밀려 조용히 누락되기 쉬운 항목(CAP25 어드버서리얼)이라 체크리스트+grep 검증으로 강제한다.

E2E 카탈로그 부재 — e2e_refs 빈 값(사용자 승인 2026-07-12).

## 심볼 인벤토리

(없음)

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 설계

docs/demo-scenario.md 구성:

1. 준비: fake 모드 구동법 (MODEL=fake, API 키 불필요)
2. 시연 순서: 정서 → 관계 → 위기(레드플래그 우선 질문 시연) → 혼합 발화(다중 슬롯 동시 채움) → 10턴 요약 JSON 확인
3. 재활병원 프리뷰 포인트: 이 3-트랙(정서/관계/위기) 분기 구조가 재활병원 버전(암재활/근골격/자율신경)의 프리뷰임을 시연 중 언급할 지점 명시 (CAP15)
4. 마지막 지식 교체 시연: KNOWLEDGE_DIR=knowledge-alt 스왑 → 같은 코드가 커피 Q&A 봇으로 동작 (CAP19)
5. 민감정보 주의 1줄: 위기 슬롯 응답이 평문 JSON으로 저장되므로 시연 데이터는 가상 사례만 사용

README.md: 데모 문서 링크 + fake 모드 구동법 추가 (부모 task Phase 3 회고 — 문서화 요구는 scope에 README 포함).

부모 checklist(docs/planning/lmwiki-chatbot-proto/checklist.md) `## Cross-Phase 메모`에 append:
"cross-phase (실행일 기입): Phase 10(D10 선형 단계 스크립트)은 미실행 상태로 intake-slot-engine task가 supersede — 스키마 선언 기반 문진 엔진이 선형 단계 스크립트 접근을 대체"

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 체크리스트

- [x] docs/demo-scenario.md 작성 — 시연 순서·재활 3-트랙(암재활/근골격/자율신경) 프리뷰 포인트·knowledge-alt 지식 교체 시연·민감정보 주의 포함
- [x] README.md에 데모 문서 링크 + fake 모드 구동법 추가
- [x] docs/planning/lmwiki-chatbot-proto/checklist.md Cross-Phase 메모에 Phase 10(D10) supersede 기록 append
- [x] supersede 메모 문구에 Phase 10·D10·intake-slot-engine 명시

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 영향 범위

문서 3파일만 — 코드·테스트 무변경. 부모 checklist는 Cross-Phase 메모 append만 허용(기존 행·상태 무수정). 롤백 = diff revert.

<!-- Parser-required structural heading: keep this exact heading text. Localize only the prose inside the section. -->
## 검증

```bash
# edge-skip: docs-only phase — 실패 경로 없음
grep -n 'supersede' docs/planning/lmwiki-chatbot-proto/checklist.md
grep -n 'demo-scenario' README.md
```

## 실행 결과

### 1회차 (2026-07-12 12:30 KST) — completed
**상태**: completed
**소요 시간**: 약 15분
**진행 모델**: Claude Haiku 4.5

#### 요약
데모 시나리오 문서 작성 완료. 정서/관계/위기 3-트랙 분기 구조, 레드플래그 우선화, 다중 슬롯 동시 채움, 지식 교체 시연, 민감정보 주의사항 등을 포함. README에 데모 링크 및 fake 모드 구동법 추가. 부모 checklist에 Phase 10(D10) supersede 메모 append 완료.

#### 변경 파일
- `docs/demo-scenario.md` (new, +261 lines)
- `README.md` (modified, +11/-0 lines)
- `docs/planning/lmwiki-chatbot-proto/checklist.md` (modified, +1/-0 lines)

#### 검증 결과
- [x] `grep -n 'supersede' docs/planning/lmwiki-chatbot-proto/checklist.md` → pass (line 79)
- [x] `grep -n 'demo-scenario' README.md` → pass (line 41)

#### 추가 발견사항
None

#### 질문 / 결정 사항
None
