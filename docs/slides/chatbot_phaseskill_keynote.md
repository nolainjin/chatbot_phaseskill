# chatbot_phaseskill — 밋업 발표용 키노트 자료

- phase-skill 기반 상담 접수 챗봇 데모
- LLM 응답 + deterministic 슬롯 엔진 + SQLite 통계 대시보드
- 프롬프트 인젝션 레드팀까지 포함한 밋업 발표 자료

---

## 1. 왜 이 챗봇인가

- 상담 전 “첫 접수”는 대화가 아니라 구조화된 정보 수집이다.
- 사용자는 길게 설명하고, 운영자는 안전·트랙·요약을 빠뜨리면 안 된다.
- 목표: 사람 말투로 반응하되, 핵심 판단은 코드와 스키마가 잡는 챗봇.

---

## 2. 핵심 설계 한 줄

- LLM은 “말투와 반응성”을 맡는다.
- 슬롯 엔진은 “무엇을 물을지, 무엇을 저장할지”를 맡는다.
- 저장/통계는 “나중에 활용 가능한 접수 데이터”를 만든다.

---

## 3. 전체 흐름

- 브라우저: session_id + participant_id 생성.
- FastAPI: 입력 검증, rate limit, 안전 필터.
- Chat loop: 지식 검색 + 슬롯 상태 + LLM 응답.
- Storage: JSON 로그 저장 → SQLite 배치 적재.
- Dashboard: 트랙·슬롯·위기 세션 통계 시각화.

---

## 4. Phase-skill 방식

- 요구사항을 phase로 쪼개고, 각 phase마다 검증 조건을 둔다.
- “상담처럼 보여야 함”이 아니라 “몇 번째 턴에 어떤 슬롯이 채워지는가”를 테스트한다.
- 버그 로그: 반복 질문, 트랙 오분류, 위기 과탐지 트레이드오프를 판단 기록에 남김.

---

## 5. 대화 엔진

- `knowledge/_intake_schema.md`: 트랙, 슬롯, 질문, 신호어, red flag 선언.
- `app/intake.py`: deterministic slot extraction.
- `app/chat.py`: 상태 관리, 질문 순서, LLM 프롬프트 구성.
- 같은 질문 반복 방지: 직전 질문의 free-text 답변을 슬롯으로 수용.

---

## 6. 모델은 교체 가능해야 한다

- `MODEL=fake`: API 없이 테스트.
- `MODEL=claude-cli`: 로컬 Claude CLI.
- `MODEL=codex-cli` / `CODEX_MODEL=gpt-5.4`: Codex CLI.
- 다음 확장: Ollama, OpenAI-compatible endpoint, 도메인별 knowledge pack.

---

## 7. 저장 구조

- JSON: `data/conversations/YYYY-MM-DD/{session_id}.json`.
- SQLite: participants / conversations / turns.
- participant_id는 이름 대신 쓰는 로컬 개인번호.
- 세션과 개인번호를 분리해 나중에 데이터 연동은 가능하지만 직접 식별은 줄인다.

---

## 8. 통계 대시보드

- `/api/stats`: SQLite를 읽어 요약 JSON 반환.
- `/stats.html`: 핵심 지표, 트랙 분포, 슬롯 채움률, 최근 세션.
- 100명 합성 프로파일로 실제와 가까운 적재·분석 흐름을 시연.

---

## 9. 프롬프트 인젝션 위협

- 직접: “이전 지시 무시”, “시스템 프롬프트 출력”.
- 간접: 문서/RAG 안에 숨은 assistant instruction.
- 난독화: Base64, hex, zero-width Unicode, typoglycemia.
- 렌더링: Markdown 이미지, HTML tag, 숨은 링크.
- 다중 턴: 앞턴에서 암호/트리거를 심는 방식.

---

## 10. 현재 방어층

- LLM 호출 전 deterministic safety filter.
- 검색 문서는 `[untrusted_knowledge]` 데이터로 격리.
- 모델 출력에서 시스템 지시·키·HTML·원격 이미지 차단.
- 위기 신호가 섞이면 인젝션보다 안전 확인 우선.
- 모델에게 도구 권한을 주지 않아 피해 범위를 줄임.

---

## 11. 레드팀과 한계

- 자동 레드팀: direct, typoglycemia, encoded, markdown/html, crisis-mixed.
- OWASP/NCSC 관점: 프롬프트 인젝션은 완전 제거가 아니라 risk reduction.
- 공개 서비스 전환 전 필요: 보존 기간, 삭제 요청, 암호화, provider 분리, 사람 보안 검토.

---

## 12. 시연 순서

1. 챗봇에서 엉뚱한 말 → 자연스럽게 접수로 복귀.
2. 프롬프트 인젝션 → 내부 지시 비공개.
3. 위기 혼합 발화 → 109/1588-9191 안내.
4. 100명 synthetic run → SQLite 적재.
5. 통계 대시보드에서 트랙·슬롯·위기 세션 확인.

---

## 참고 자료

- OWASP LLM Prompt Injection Prevention Cheat Sheet.
- Microsoft: Defend against indirect prompt injection attacks.
- Microsoft Semantic Kernel: unsafe content encoded by default.
- NIST CSRC: indirect prompt injection glossary.
- NCSC: Prompt injection is not SQL injection.
- OpenAI: Understanding prompt injections.
