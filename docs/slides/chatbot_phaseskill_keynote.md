# chatbot_phaseskill — 내일 발표 준비 패키지

- 주인공은 하나: `lmwiki-chatbot`(①)만 본 발표의 중심에 둔다.
- ②/③/④는 비교·부록·Q&A에서만 짧게 꺼낸다.
- 순서: “어떻게 만들었는가” → “처음 동작한 봇” → “모델/비용 경계” → “안전·테스트·레드팀 repair loop”.
- 설문·비교·운영 로그는 모두 집계·요약만 사용한다. 이름, 전화번호, 응답자 ID, 연락처, 행 단위 답변은 발표자료에 넣지 않는다.

---

## 0. 발표 원칙

1. **입문자 우선**: “LLM”, “slot”, “red-team”은 처음 한 번 쉬운 말로 풀고, 코드명은 뒤에 붙인다.
2. **제작 과정 우선**: 안전·테스트는 무섭게 시작하는 강의가 아니라, 실수하고 고친 증거로 후반에 보여준다.
3. **하나의 이야기**: “상담 접수 챗봇 하나를 만들며 배운 제작법”으로 고정한다.
4. **모델/비용 정직성**: `MODEL=fake`는 무료·결정론 데모이고, Codex/Claude CLI·Anthropic API는 실제 외부 모델 경로다.
5. **개인정보 최소화**: 합성 데이터와 집계만 사용한다. 실제 상담·설문 raw는 말하지 않는다.

## 0.5. 이번 개편에서 실제로 달라진 점

| 기존 자료의 약점 | 이번 발표용으로 바꾼 점 | 발표자가 말할 문장 |
|---|---|---|
| 네 챗봇 비교가 앞에 나와 초보자가 따라갈 중심축이 흐림 | `lmwiki-chatbot` 하나를 제작기로 세우고 ②/③/④는 Q&A 비교표로 격리 | “오늘은 네 봇 경진대회가 아니라, 한 봇을 고쳐간 기록입니다.” |
| 테스트 숫자가 성과 자랑처럼 보임 | 실패 사례 → 레드팀 → 패치 → 재검사 영수증 순서로 재구성 | “검사는 자랑이 아니라 실수 회수 장치입니다.” |
| 모델 비용 질문에 답이 흐림 | `MODEL=fake`, CLI 모델 경로, Claude/GPT API, 운영 후보를 분리 | “운영은 비싼 모델을 고르는 문제보다, 호출을 어디까지 줄일지 정하는 문제입니다.” |
| 팀 피드백이 부록처럼 보임 | 팀/리뷰가 실제로 바꾼 문제 해결 방식과 issue #1 개선 영수증을 본편에 배치 | “AI 팀은 코드를 더 많이 쓰게 한 것이 아니라, 빠진 기준을 밖으로 꺼내게 했습니다.” |
| 복사본 전달 시 이미지 자산 누락 가능 | `screenshots/07-chatbot-only.png`까지 결과 폴더에 같이 둔다 | “완료는 파일이 열리고 이미지가 보일 때 완료입니다.” |

---

## 1. Evidence map — 상세 슬라이드 편집 전 근거표

| source | claim | confidence | audience layer | slide/use | privacy class |
|---|---|---:|---|---|---|
| `/Volumes/부부공용/worknote/lmwiki-chatbot/README.md:95-140`, `.env.example:7-15`, `app/llm.py:154-160,309-320` | `MODEL=fake`는 API 없이 결정론 테스트용이고, `MODEL=auto`/`MODEL_CHAIN=codex-cli:gpt-5.4,claude-cli,fake`는 Codex CLI → Claude CLI → fake 순서로 폴백한다. Codex/Claude CLI는 로컬 명령이지만 완전한 오프라인 로컬 모델이 아니다. | 높음 | 입문+실무 | 모델 모드, 비용/연결 Q&A | repo-public/no-PII |
| `https://github.com/nolainjin/chatbot_phaseskill/issues/1` | GitHub issue #1은 “교육용 커스터마이징 프로토타입” 기준을 제시했고, 댓글에서 `knowledge-math` starter pack, UI schema extension, `pytest 147 passed`가 완료됐으며 guide/validator/smoke/dependency 항목은 남은 일로 기록됐다. | 높음 | 실무 | Phase-skill, GJC-team, 이슈 기반 개선 | public issue/no survey rows |
| `/Volumes/부부공용/worknote/lmwiki-chatbot/.omo/evidence/final-quality-gates.json:1-40` | 최종 품질 게이트는 PASS: pytest 209 passed, math 150/150, legacy/fallback browser PASS, external gpt54 sample·Spark PASS. | 높음 | 실무+Q&A | 레드팀/한계, repair loop 증거 | repo evidence/no-PII |
| `/Volumes/부부공용/worknote/lmwiki-chatbot/.omo/evidence/task-3-voice-local-demo-verifier.json:150-159,213-225`, `task-3-voice-local-demo-verifier-final.json:127-149,285-291,315-320` | verifier가 raw 500 provider prediction timeout을 잡았고, 이후 안정적인 503 `provider_timeout`으로 고쳤다. 발표에서는 “실수 → 검증자 → 수정” 한 장짜리 repair-loop 사례로만 쓴다. | 높음 | 실무 | 안전/tests/red-team repair loop | repo evidence/no audio/raw transcript |
| `/Volumes/부부공용/worknote/직장/빅션/92_작업중/챗봇-비교/2026-07-19_챗봇-4종-비교평가.md:37-42,156-163,209-217`, `2026-07-20_빅션봇-대화품질-개선안.md:22-35,90-96` | ①이 발표 주력이다. ②는 386/386식 검증과 품질 개선이 있었지만 conversation-quality ceiling이 남아 appendix/Q&A 비교로 둔다. | 높음 | Q&A | comparison/limits/what to copy | internal comparison/no raw customer rows |
| 사전 설문 CSV 집계(행 단위 비공개) | 집계 테마: 모델/API 비용과 연결, 안전·테스트·레드팀, 팀·피드백·이슈 기반 개선, 초보자 설명, 도메인·사업 적용. 행·연락처·이름은 사용하지 않는다. | 중간 | 입문+Q&A | 왜 이 챗봇인가, 질문 예상 | aggregate-only/no row-level |
| `/Volumes/부부공용/worknote/troubleshooting-log.md:34-38` | `완료≠전달`: sub-agent가 완료했어도 결과 전달이 안 되면 1회 재요청과 반환값 명시가 필요하다. | 높음 | 실무 | GJC-team 운영 카드 1 | local ops/no PII |
| `/Volumes/부부공용/worknote/troubleshooting-log.md:42-78` | `완전 회수 강박`: 자료 전체 회수보다 현재 증거 범위로 산출물을 먼저 만들고 한계를 표시해야 한다. | 높음 | 입문+실무 | 제작 과정/컷 규칙 카드 2 | local ops/no PII |
| `/Volumes/부부공용/worknote/바이브선생/2026-03-16/growth-detail-dashboard-2026-03-16.md:32-46`, `/Volumes/부부공용/worknote/troubleshooting-log.md:83-129` | `도구/스킬 실패 진단`: “Unknown skill”이나 도구 표면 불일치는 성공 문구가 아니라 실제 산출물·경로·권한으로 확인해야 한다. | 높음 | 실무 | repair loop 카드 3 | local ops/no PII |

---

## 2. Source-to-slide map

| source group | primary slide/use | 말할 문장 |
|---|---|---|
| README/app model docs | 모델 모드 | “fake는 공짜 품질 모델이 아니라, 대화 흐름을 안전하게 확인하는 자동응답 모드입니다.” |
| GitHub issue #1 | Phase-skill 방식 | “이슈는 할 일 목록이 아니라, 교육용 전달 품질 기준을 밖으로 꺼낸 계약서였습니다.” |
| final-quality-gates | 레드팀/한계 | “테스트 숫자는 앞에서 자랑하지 않고, 뒤에서 ‘어떻게 고쳤는지’ 증거로 씁니다.” |
| voice verifier artifacts | safety repair loop | “초록 테스트만 믿지 않고, 검증자가 직접 raw 500을 잡아낸 사례입니다.” |
| 비교 문서 | comparison/limits | “②는 운영 통제가 강하지만 대화 품질 천장이 있어 오늘 주인공은 ①입니다.” |
| 설문 CSV 집계 | 왜/모델/Q&A | “질문은 비용, 연결, 안전, 팀 작업, 사업 적용으로 몰릴 겁니다.” |
| troubleshooting/growth logs | 제작 과정 카드 | “완료와 전달, 전체 회수와 발표 산출물, 도구 성공 문구를 구분합니다.” |

---

## 3. Checked/no-hit/deferred 근거 감사

| candidate path | status | use | note |
|---|---|---|---|
| `/Volumes/부부공용/worknote/troubleshooting-log.md` | checked / used | 카드 1~3 일부 | lines 34-38, 42-78, 83-129만 사용. |
| `/Volumes/부부공용/worknote/troubleshooting-log_v2.md` | checked / deferred | 구조 참고만 | v2는 원본 사건 본문을 바꾸지 않는 재분류본이라고 밝힘(`troubleshooting-log_v2.md:1-6`); 상세 인용은 원본으로 고정. |
| `/Volumes/부부공용/worknote/troubleshooting-index.md` | checked / deferred | 태그 색인 참고 | 자동 태그 인덱스(`troubleshooting-index.md:1-35`)라 발표 근거 본문으로는 쓰지 않음. |
| `/Volumes/부부공용/worknote/에이전트_핸드오프_코코님.md` | no-hit | 사용 안 함 | canonical root path는 현재 확인 경로에 없음. archive 대체본을 임의로 쓰지 않음. |
| `/Volumes/부부공용/worknote/바이브선생/2026-03-16/growth-detail-dashboard-2026-03-16.md` | checked / used | 카드 3 | `Unknown skill: omc-plan` 패턴만 인용. |
| `/Volumes/부부공용/worknote/바이브선생/2026-03-16/growth-detail-stock-2026-03-16.md` | checked / deferred | Q&A 예비 | 다중 모델 피드백·fallback·반복 실패 원인 추적 사례가 있으나, 본편 3카드 제한 때문에 사용하지 않음. |
| `/Volumes/부부공용/worknote/바이브선생/2026-03-16/growth-detail-vibe-basic-2026-03-16.md` | checked / deferred | Q&A 예비 | 팀·도구·컨텍스트 성장 사례로 좋지만 본편 근거 카드가 과밀해 appendix 후보로만 둠. |
| `/Volumes/부부공용/worknote/바이브선생/2026-03-22/01-project-patterns.md` | checked / deferred | Q&A 예비 | 도구 활용·원인 분석 성장 흐름 확인. 오늘 본편은 `lmwiki-chatbot` 하나에 집중하므로 확장하지 않음. |
| `/Volumes/부부공용/worknote/.claude/rules-details/qa-gate-details.md`, `llm-observation-details.md`, `bot-outsource-validation.md`, `sub-agent-validation.md` | checked / framing only | 운영 프레임 | QA gate는 “UI/DOM 존재≠기능 성공”, sub-agent validation은 산출물 위치·실측 출력 인용 의무를 강조한다. 제품 기능 증거로는 쓰지 않음. |

---

## 4. 50분 운영표

| 시간 | 내용 | 핵심 메시지 | 보조 자료 |
|---:|---|---|---|
| 0–5 | why/process | “챗봇은 모델 붙이기가 아니라 접수 흐름을 안전하게 제품화하는 일이다.” | 왜 이 챗봇인가 |
| 5–15 | first working bot + phase-skill | “처음 동작하는 작은 봇을 만들고 phase별로 고쳤다.” | 전체 흐름, Phase-skill |
| 15–25 | prompts/skills/GJC-team/GitHub issue | “프롬프트·스킬·이슈를 작업 계약으로 바꾸면 혼자 해도 팀처럼 점검할 수 있다.” | issue #1, 운영 카드 |
| 25–31 | model chain/cost/fake | “fake는 무료 결정론 데모, CLI/API는 실제 모델 경로다.” | 모델 모드 |
| 31–32 | trust boundary | 아래 사전 문구를 그대로 읽는다. | 신뢰 경계 |
| 32–35 | 3-minute demo | “엉뚱한 말 → 접수 복귀, 인젝션 → 차단, 통계 확인.” | 시연 순서 |
| 35–45 | safety/tests/red-team repair loops | “테스트는 자랑이 아니라 실수 회수 장치다.” | final gates, voice verifier |
| 45–50 | limits/what to copy | “복사할 것은 코드보다 책임 분리와 검증 루프다.” | 마무리 메시지 |
| 50–80 | Q&A/full demo | 질문에 따라 모델 비용, 도메인 교체, 운영 전환, 전체 데모를 선택한다. | appendix prompts |

### 31–32분 pre-demo trust boundary wording

> 지금 시연은 `MODEL=fake` 중심의 교육용 데모입니다. 실제 개인정보는 넣지 않고, 같은 입력에 같은 경로로 흐르는 deterministic guardrail을 확인합니다. 서버나 브라우저가 흔들리면 no-server fallback으로 흐름만 설명합니다. 레드팀 문장은 제가 준비한 controlled input이며, 이 화면은 공개 서비스나 임상·상담 품질 보증이 아닙니다.

---

## 5. 상세 슬라이드 원고 — 기존 섹션 병합본

### 1. 왜 이 챗봇인가

**키 메시지**: 상담 전 “첫 접수”는 긴 대화가 아니라, 빠뜨리면 안 되는 정보를 안전하게 정리하는 일이다.

**입문자 설명**
- 우리가 만드는 것은 “사람 대신 상담하는 AI”가 아니다.
- 사용자의 첫 이야기를 듣고, 필요한 항목을 하나씩 채우고, 위험 신호가 있으면 사람/전문기관으로 넘기는 접수 도구다.
- 설문 집계에서도 초보자 설명, 비용, 안전, 도메인 적용 질문이 반복될 가능성이 높다. raw 설문 행은 쓰지 않는다.

**발표자 bullet**
- “챗봇을 만들었다”보다 “접수 흐름을 만들었다”로 시작.
- 사용자는 길게 말한다. 운영자는 트랙, 위험 신호, 요약, 저장을 놓치면 안 된다.
- 오늘의 주인공은 `lmwiki-chatbot` 하나다. ②/③/④는 뒤에서 비교만 한다.

**근거**
- README의 목적과 비진단 경계: `/Volumes/부부공용/worknote/lmwiki-chatbot/README.md:3-11`
- 책임 분리 문장: `/Volumes/부부공용/worknote/lmwiki-chatbot/README.md:24-26`

---

### 2. 핵심 설계

**키 메시지**: 판단은 코드, 표현은 모델.

**초보자 번역**
- 모델은 말투 담당이다.
- 코드와 스키마는 “다음에 무엇을 물어볼지”, “무엇을 저장할지”, “위험하면 어디로 보낼지”를 담당한다.
- 이렇게 나누면 모델이 말을 조금 다르게 해도 접수 순서와 안전 경계는 흔들리지 않는다.

**발표자 bullet**
- “LLM에게 다 맡기지 않았다”를 강조.
- 질문 순서, 위기 우선순위, 기관 전화번호, 저장 형식은 모델의 즉흥 판단 밖에 둔다.
- 이 한 줄이 전체 설계의 기준이다.

**근거**
- README 책임 분리: `/Volumes/부부공용/worknote/lmwiki-chatbot/README.md:73-83`
- README 1분 흐름: `/Volumes/부부공용/worknote/lmwiki-chatbot/README.md:13-26`

---

### 3. 전체 흐름

**키 메시지**: 브라우저 → API → 대화 엔진 → 저장 → 통계가 한 바퀴 돈다.

**발표자 bullet**
1. 브라우저가 `session_id`와 `participant_id`를 만든다.
2. FastAPI가 입력 검증, rate limit, safety filter를 먼저 본다.
3. Chat loop가 지식 검색, 슬롯 상태, 모델 응답을 엮는다.
4. JSON 로그가 남고, SQLite로 적재된다.
5. `/stats.html`에서 집계와 트리아지를 본다.

**초보자 비유**
- 카페 주문으로 치면, 손님 말은 자유롭지만 주문표 칸은 정해져 있다.
- 챗봇은 손님 말을 주문표에 맞게 정리하는 직원이다.

**근거**
- 저장·통계 흐름: `/Volumes/부부공용/worknote/lmwiki-chatbot/README.md:263-312`
- 프로젝트 지도: `/Volumes/부부공용/worknote/lmwiki-chatbot/README.md:351-365`

---

### 4. Phase-skill 방식

**키 메시지**: 큰 챗봇을 한 번에 만든 게 아니라, phase마다 “완료 조건”을 세워 고쳤다.

**발표자 bullet**
- phase는 “작업을 나눈 칸”이다.
- skill은 “그 칸에서 반복해 쓰는 작업 방식”이다.
- GitHub issue #1은 교육용 전달 품질 기준을 외부 이슈로 꺼낸 사례다.
- `knowledge-math` starter pack과 UI schema extension은 완료됐고, guide/validator/smoke/dependency는 남은 일로 기록됐다.
- GJC-team처럼 여러 역할을 썼지만, 발표에서는 결과물을 하나의 `lmwiki-chatbot`으로 합쳐 보여준다.

**Orca 운영 카드**
- 완료≠전달: sub-agent가 끝냈다고 해도 발표자가 받을 결과물이 도착했는지 확인한다.
- 완전 회수 강박 금지: 모든 자료를 다 긁기보다, 근거 범위와 한계를 적고 발표 산출물을 먼저 만든다.
- 도구/스킬 실패 진단: “성공” 문구보다 실제 산출물과 경로를 본다.

**근거**
- GitHub issue #1: `https://github.com/nolainjin/chatbot_phaseskill/issues/1`
- 완료≠전달: `/Volumes/부부공용/worknote/troubleshooting-log.md:34-38`
- 완전 회수 강박: `/Volumes/부부공용/worknote/troubleshooting-log.md:42-78`
- 도구/스킬 실패: `/Volumes/부부공용/worknote/바이브선생/2026-03-16/growth-detail-dashboard-2026-03-16.md:32-46`

---

### 5. 대화 엔진

**키 메시지**: 자연스러운 말은 모델이 만들지만, 접수 상태는 deterministic slot engine이 관리한다.

**발표자 bullet**
- `knowledge/_intake_schema.md`: 트랙, 슬롯, 질문, 신호어, red flag 선언.
- `app/intake.py`: deterministic slot extraction.
- `app/chat.py`: 상태 관리, 질문 순서, LLM 프롬프트 구성.
- 같은 질문 반복 방지: 직전 질문의 free-text 답변을 슬롯으로 수용.
- ①의 강점은 한 발화에서 여러 정보를 뽑고, 트랙에 맞춰 질문이 바뀌는 점이다.

**초보자 설명**
- slot은 빈칸이다. “언제부터?”, “무엇이 힘든가?”, “위험 신호가 있는가?” 같은 칸을 하나씩 채운다.
- 좋은 챗봇은 “말을 잘하는 것”보다 “이미 말한 걸 또 묻지 않는 것”에서 체감이 난다.

**근거**
- README 책임 분리: `/Volumes/부부공용/worknote/lmwiki-chatbot/README.md:73-83`

---

### 6. 모델 모드

**키 메시지**: `MODEL=fake`와 실제 모델 경로는 완전히 다르게 말해야 한다.

**입문자 설명**
- `MODEL=fake`: 인터넷 모델을 부르지 않는 자동응답 테스트 모드. 무료이고 빠르며 같은 입력에 같은 식으로 움직인다. 자연어 품질을 증명하지 않는다.
- `MODEL=codex-cli` / `codex-cli:gpt-5.4`: 내 컴퓨터의 Codex CLI 프로그램을 통해 실제 모델을 호출한다. 로컬 명령이지만 오프라인 모델은 아니다.
- `MODEL=claude-cli`: 내 컴퓨터의 Claude CLI 프로그램을 통해 실제 모델을 호출한다. 역시 오프라인 모델이 아니다.
- Anthropic 모델명: `ANTHROPIC_API_KEY`로 직접 API를 호출한다. 비용·키·한도 관리가 필요하다.
- `MODEL=auto`: `MODEL_CHAIN` 순서대로 시도한다. 기본 체인은 `codex-cli:gpt-5.4,claude-cli,fake`다. 그래서 `auto` 결과는 “진짜 모델이 답했다”고 단정하지 말고 어떤 backend가 실제로 썼는지 구분해야 한다.

**발표자 bullet**
- “fake는 무료 모델이 아니라 테스트용 대역 배우입니다.”
- “CLI는 내 노트북에서 명령을 치지만, 뇌가 노트북 안에 있는 건 아닙니다.”
- “비용 질문이 나오면 fake / CLI subscription / API key 세 층으로 분리해 답합니다.”

**근거**
- fake 실행: `/Volumes/부부공용/worknote/lmwiki-chatbot/README.md:95-104`
- provider table 및 오프라인 아님: `/Volumes/부부공용/worknote/lmwiki-chatbot/README.md:126-140`
- `MODEL_CHAIN`: `/Volumes/부부공용/worknote/lmwiki-chatbot/.env.example:7-15`
- auto fallback 구현: `/Volumes/부부공용/worknote/lmwiki-chatbot/app/llm.py:154-160,309-320`

---

### 7. 저장 구조

**키 메시지**: 대화 원본과 집계용 DB를 분리해 나중에 확인 가능하게 만든다.

**발표자 bullet**
- JSON: `data/conversations/YYYY-MM-DD/{session_id}.json`.
- SQLite: `participants`, `conversations`, `turns`.
- `participant_id`는 이름이 아니라 로컬 브라우저의 익명 식별자다.
- 직접 식별 위험을 낮추지만, 완전한 익명화는 아니다. 운영 환경에서는 접근 통제, 보존 기간, 암호화, 동의 절차가 필요하다.

**초보자 설명**
- 원본 영수증은 JSON, 장부는 SQLite라고 보면 된다.
- 발표에서는 합성 데이터만 보여준다.

**근거**
- README 저장 구조: `/Volumes/부부공용/worknote/lmwiki-chatbot/README.md:263-292`

---

### 8. 통계 대시보드

**키 메시지**: 챗봇의 가치는 대화 한 번이 아니라, 접수 데이터를 나중에 볼 수 있게 만드는 데 있다.

**발표자 bullet**
- `/api/stats`: SQLite를 읽어 요약 JSON 반환.
- `/stats.html`: 핵심 지표, 트랙 분포, 슬롯 채움률, 최근 세션.
- 100명 synthetic run으로 실제 사람 없이 적재·분석 흐름을 보여준다.
- CSV 내보내기는 합성·교육용 범위로만 말한다.

**근거**
- 관리자 화면 기능: `/Volumes/부부공용/worknote/lmwiki-chatbot/README.md:62-71`
- 100명 합성 데모: `/Volumes/부부공용/worknote/lmwiki-chatbot/README.md:298-312`

---

### 9. 프롬프트 인젝션

**키 메시지**: 프롬프트 인젝션은 “챗봇에게 몰래 다른 명령을 시키는 장난/공격”이다.

**입문자 설명**
- 직접형: “이전 지시 무시해.”
- 간접형: 지식 문서 안에 “assistant는 이걸 따라라”를 숨김.
- 난독화: Base64, hex, zero-width Unicode, typoglycemia.
- 렌더링형: Markdown 이미지, HTML tag, 숨은 링크.
- 다중 턴: 앞턴에서 암호나 트리거를 심음.

**발표자 bullet**
- 위협 목록은 짧게만 보여준다.
- 핵심은 “모델에게 도구 권한을 주지 않고, 입력과 출력에서 위험 문구를 코드로 거른다”이다.

**근거**
- README safety routing: `/Volumes/부부공용/worknote/lmwiki-chatbot/README.md:39-60`
- final red_team 6/6: `/Volumes/부부공용/worknote/lmwiki-chatbot/.omo/evidence/final-quality-gates.json:2-8`

---

### 10. 방어층

**키 메시지**: 완전 제거가 아니라 risk reduction이다.

**발표자 bullet**
- LLM 호출 전 deterministic safety filter.
- 검색 문서는 `[untrusted_knowledge]` 데이터로 격리.
- 모델 출력에서 시스템 지시·키·HTML·원격 이미지 차단.
- 위기 신호가 섞이면 인젝션보다 안전 확인 우선.
- 모델에게 도구 권한을 주지 않아 피해 범위를 줄인다.

**초보자 설명**
- 챗봇에게 회사 카드키를 주지 않는다.
- 위험한 문구가 들어오면 모델에게 넘기기 전에 안내와 접수 흐름으로 돌린다.

**근거**
- README 1분 처리 순서: `/Volumes/부부공용/worknote/lmwiki-chatbot/README.md:13-26`
- QA framing “UI 존재≠기능 성공”: `/Volumes/부부공용/worknote/.claude/rules-details/qa-gate-details.md:24-49`

---

### 11. 레드팀/한계

**키 메시지**: 테스트와 레드팀은 “안전합니다” 선언이 아니라, 어디까지 확인했고 어디부터 한계인지 말하는 장치다.

**발표자 bullet**
- final gates: pytest 209 passed, math 150/150, coaching fake 24/24, red_team 6/6.
- browser legacy/fallback PASS, external gpt54 sample과 Spark PASS.
- voice verifier 사례: 초록 테스트 뒤에도 raw 500이 숨어 있었고, verifier가 잡아서 503 `provider_timeout`으로 고쳤다.
- 공개 서비스 전환 전에는 보존 기간, 삭제 요청, 암호화, provider 분리, 사람 보안 검토가 필요하다.
- 상담·중독 라우팅은 임상 진단을 대체하지 않는다.

**근거**
- final gates: `/Volumes/부부공용/worknote/lmwiki-chatbot/.omo/evidence/final-quality-gates.json:1-40`
- voice raw 500 finding: `/Volumes/부부공용/worknote/lmwiki-chatbot/.omo/evidence/task-3-voice-local-demo-verifier.json:150-159,213-225`
- voice fixed 503: `/Volumes/부부공용/worknote/lmwiki-chatbot/.omo/evidence/task-3-voice-local-demo-verifier-final.json:127-149,285-291,315-320`
- README 한계: `/Volumes/부부공용/worknote/lmwiki-chatbot/README.md:368-376`

---

### 12. 시연 순서

**키 메시지**: 3분 데모는 성공 장면보다 경계 장면을 보여준다.

**3분 demo script**
1. 챗봇에서 엉뚱한 말 → 접수 흐름으로 복귀.
2. 프롬프트 인젝션 → 내부 지시 비공개.
3. 위기 혼합 발화 → 안전 확인과 109/1588-9191 안내.
4. 합성 데이터 통계 → SQLite 적재 결과 확인.
5. `/stats.html`에서 트랙·슬롯·위기 세션 확인.

**실패 fallback**
- 서버/브라우저가 안 뜨면 no-server fallback: 위 5단계를 말로 설명하고, 모델 모드/저장 구조/통계 흐름 슬라이드로 이동.
- real CLI가 느리거나 실패하면 `MODEL=fake`로 남는다. 이때 “실제 모델 품질 시연이 아니라 guardrail 시연”이라고 말한다.

**시연 전 신뢰 경계**
- “실제 개인정보 없음.”
- “fake 중심, deterministic guardrail 확인.”
- “red-team input은 통제된 문장.”
- “production/clinical assurance 아님.”

---

### 13. 참고 자료

**공개 참고**
- OWASP LLM Prompt Injection Prevention Cheat Sheet.
- Microsoft: Defend against indirect prompt injection attacks.
- Microsoft Semantic Kernel: unsafe content encoded by default.
- NIST CSRC: indirect prompt injection glossary.
- NCSC: Prompt injection is not SQL injection.
- OpenAI: Understanding prompt injections.

**로컬 참고**
- README: `/Volumes/부부공용/worknote/lmwiki-chatbot/README.md`
- 모델 체인: `/Volumes/부부공용/worknote/lmwiki-chatbot/.env.example`
- 최종 게이트: `/Volumes/부부공용/worknote/lmwiki-chatbot/.omo/evidence/final-quality-gates.json`
- 비교 문서: `/Volumes/부부공용/worknote/직장/빅션/92_작업중/챗봇-비교/`
- 운영 로그 카드: `/Volumes/부부공용/worknote/troubleshooting-log.md`

---

## 6. Appendix/Q&A prompts

| 예상 질문 | 짧은 답 | 길게 갈 때 |
|---|---|---|
| “이거 공짜인가요?” | fake 데모는 API 비용이 없다. 실제 Codex/Claude CLI나 API는 계정·한도·비용이 걸린다. | `MODEL=fake`, CLI, direct API 세 층을 화이트보드로 분리. |
| “CLI면 로컬 모델인가요?” | 아니다. 로컬 프로그램을 실행하지만 모델 추론은 외부 서비스 경로다. | README와 `.env.example`의 provider 설명을 보여준다. |
| “내 업종으로 바꿀 수 있나요?” | `KNOWLEDGE_DIR`와 pack 문서를 바꾸는 방식이다. | issue #1의 `knowledge-math` starter pack과 customization guide 미완료 항목 설명. |
| “안전하다고 볼 수 있나요?” | 교육용 guardrail을 검증한 것이지 공개 서비스 보증은 아니다. | final gates와 voice verifier repair loop, 운영 전 필요한 보존/삭제/암호화/사람 검토 설명. |
| “② bigtion은 왜 안 보여주나요?” | ②는 운영 통제 설명용이다. 오늘 대화 데모 주인공은 ①이다. | ②의 386/386식 개선과 남은 conversation-quality ceiling을 appendix로 설명. |
| “설문에서 사람들이 뭘 궁금해했나요?” | 비용·연결, 안전·테스트, 팀 작업, 초보 설명, 사업 적용이 집계 테마다. | raw 행·이름·연락처는 보지 않고 집계만 사용한다고 다시 고지. |
| “진짜 상담에 써도 되나요?” | 아니다. 접수 보조 데모이며 임상 판단을 대체하지 않는다. | README 비진단 경계와 한계 섹션을 보여준다. |

---

## 7. Cut rules

1. 시간이 밀리면 프롬프트 인젝션 종류 목록을 줄이고, 모델 모드와 신뢰 경계는 자르지 않는다.
2. 비교 봇 ②/③/④ 설명은 45분 이후 또는 Q&A로 미룬다.
3. 테스트 숫자는 35분 전에는 길게 말하지 않는다. 앞부분은 제작 과정과 첫 working bot 중심.
4. 실시간 서버가 흔들리면 즉시 no-server fallback으로 전환한다.
5. 설문 raw, 개인 사례, 연락처, 행 단위 답변은 어떤 질문이 나와도 말하지 않는다.
6. `MODEL=auto` 결과를 실제 모델 품질 증거로 말하지 않는다. fallback 가능성을 함께 말한다.
7. “완성된 제품”이라는 표현 대신 “교육용 프로토타입, 공개 운영 전 추가 검토 필요”라고 말한다.

---

## 8. Rehearsal checklist

- [ ] 31–32분 trust boundary 문구를 한 번에 읽는다.
- [ ] `MODEL=fake` 설명을 20초 안에 말한다.
- [ ] `MODEL_CHAIN=codex-cli:gpt-5.4,claude-cli,fake`를 “순서대로 시도하는 보험”으로 설명한다.
- [ ] demo 3분 안에 끊는 연습: 엉뚱한 말, 인젝션, 위기 혼합, 통계.
- [ ] red-team은 통제 입력만 사용하고 즉흥 공격문을 받지 않는다.
- [ ] 비교 질문이 나오면 “① 주인공, ② appendix, ③/④ Q&A”로 정리한다.
- [ ] 설문 질문은 집계 테마만 말한다.
- [ ] 마지막 1분: “복사할 것은 코드보다 책임 분리와 검증 루프”로 닫는다.

---

## 9. Verification ownership — executor-checkable vs presenter/manual

| 항목 | owner | 여기서의 상태 |
|---|---|---|
| Markdown에 요구 섹션 포함 | executor-checkable | 이 파일 안에 섹션으로 반영. |
| evidence map column 이름 | executor-checkable | `source`, `claim`, `confidence`, `audience layer`, `slide/use`, `privacy class`로 작성. |
| raw survey row/PII 미노출 | executor-checkable | raw 행·이름·전화·연락처·응답자 ID를 넣지 않음. |
| HTML/Keynote 렌더 확인 | presenter/manual | 이 작업 범위 밖. browser 실행 없이 placeholder만 둠. |
| live demo 서버 상태 | presenter/manual | 발표 전 사람이 확인. 이 문서는 no-server fallback 포함. |
| 실제 모델 비용·계정 상태 | presenter/manual | CLI/API 계정 상태는 발표자가 현장 전에 확인. |
| tests/lint/formatter/build/server/browser | parent/manual if needed | 이 문서 편집에서는 실행하지 않는 범위. |

---

## 10. Acceptance crosswalk

| 요구 | 반영 위치 |
|---|---|
| evidence map table before detailed slide edits | §1 |
| 지정 evidence facts with citations only | §1, §5 각 슬라이드 근거 |
| survey aggregate-only, no rows/contact data | §1, §6, §7, §12 |
| bounded Orca/multi-repo max 3 cards | §1, §3, §5-4 |
| checked/no-hit/deferred table | §3 |
| 50-minute timing table | §4 |
| slide-by-slide key messages and speaker bullets | §5 |
| one primary protagonist `lmwiki-chatbot` | §0, §4, §5, §7 |
| ②/③/④ appendix/Q&A only | §0, §6, §7 |
| `MODEL=fake` vs real CLI/API distinction | §5-6, §6 |
| pre-demo trust boundary wording | §4, §5-12 |
| source-to-slide map | §2 |
| appendix/Q&A prompts | §6 |
| cut rules | §7 |
| rehearsal checklist | §8 |
| verification ownership | §9 |
| markdown merge audit | §11 |
| HTML no-browser checklist placeholder | §12 |
| privacy rule | §13 |

---

## 11. Markdown merge audit

| 기존 섹션 | 병합 위치 | 변경 이유 |
|---|---|---|
| 왜 이 챗봇인가 | §5-1 | beginner-first 목적 설명과 설문 집계 테마 추가. |
| 핵심 설계 | §5-2 | “판단은 코드, 표현은 모델”로 확장. |
| 전체 흐름 | §5-3 | 브라우저→API→엔진→저장→통계 흐름 보존. |
| Phase-skill 방식 | §5-4 | GitHub issue #1, GJC-team, 운영 카드 연결. |
| 대화 엔진 | §5-5 | slot engine을 초보자 언어로 설명. |
| 모델은 교체 가능해야 한다 | §5-6 모델 모드 | `MODEL=fake`, `MODEL=auto`, `MODEL_CHAIN`, CLI/API 비용 경계로 재구성. |
| 저장 구조 | §5-7 | JSON/SQLite/participant_id와 개인정보 한계 보존. |
| 통계 대시보드 | §5-8 | 합성 100명 데모와 CSV 경계 추가. |
| 프롬프트 인젝션 | §5-9 | 위협 유형을 입문자 언어로 보존. |
| 현재 방어층 | §5-10 방어층 | deterministic filter와 untrusted knowledge 경계 보존. |
| 레드팀과 한계 | §5-11 레드팀/한계 | final gates와 voice verifier repair loop 추가. |
| 시연 순서 | §5-12 | 3분 데모와 no-server fallback 추가. |
| 참고 자료 | §5-13 | 공개 참고와 로컬 evidence를 분리. |

---

## 12. HTML 통합 체크 결과

> Parent 검증에서 `chatbot_development_story_keynote.html`의 소스 구조 검사와 headless browser 상호작용 확인을 모두 수행했다. 발표 시간 리허설과 현장 라이브 준비 상태는 여전히 발표자 수동 항목이다.

- [x] Section IDs: 18개 slide section이 있고 duplicate ID가 없다.
- [x] Nav hrefs: 11개 nav anchor가 모두 실제 section으로 연결된다.
- [x] `data-no`: section은 `01 / 18`부터 `18 / 18`까지 유지하고, nav는 11개 main/cut-flow anchor로 압축했다.
- [x] Retained controls/dialogs: screenshot dialog가 열리고 닫히며, test-runner button은 `209 passed · 0 failed`까지 도달한다.
- [x] JS selectors retained: `.metrics .value`, `.who-chip`, `#dotGrid`, `.finale`, `.slide`, `.screenshot-scroll`, `#s7ImageDialog`, `#runTestsBtn`, `#runnerFill`, `#runnerStatus`, `#runnerLog`.
- [x] Accessibility basics: nav aria-label, dialog aria-labelledby, live runner log, screenshot alt text, details/summary card가 있다.
- [x] Appendix/cut-flow: s16–s18은 appendix/Q&A로 표시되어 있고, final note에서 Q&A 때만 사용한다고 안내한다.
- [x] Privacy/source scan: 설문은 집계 테마만 사용했고, 최종 산출물에서 연락처형 전화번호·이메일·응답자 토큰 hit가 없다.

---

## 13. Privacy rule

1. 발표자료에는 합성 데이터와 집계 테마만 사용한다.
2. 설문 CSV는 aggregate-only로 다룬다. 이름, 전화번호, 응답자 ID, 연락처, 행 단위 답변, 원문 인용을 넣지 않는다.
3. 데모 입력도 실제 개인 사연이 아니라 통제된 예시 문장만 쓴다.
4. `participant_id`는 직접 식별자가 아니지만 완전 익명화가 아니므로, 운영 환경에서는 접근 통제·보존 기간·삭제 요청·암호화·동의 절차를 별도 설계해야 한다.
5. 공개 발표에서는 “상담·의료 진단/치료 서비스가 아님”을 명시한다.
