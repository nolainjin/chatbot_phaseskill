# chatbot_phaseskill

마크다운 지식 폴더와 LLM 제공자만 바꿔 여러 업종의 **초기 접수 챗봇**으로
재사용할 수 있는 데모입니다. 현재 예시는 상담기관의 첫 면담이며, 대화 UI,
안전 라우팅, 구조화 저장, SQLite 적재, 관리자 통계 화면까지 한 흐름으로
동작합니다.

> 이 프로젝트는 상담·의료 진단이나 치료를 제공하는 서비스가 아닙니다.
> 사용자의 첫 설명을 정리하고, 위기 또는 중독처럼 별도 도움이 필요한 경우
> 적절한 전문기관 정보를 안내하는 접수 도구입니다.

## 1분 안에 이해하기

사용자가 메시지를 보내면 다음 순서로 처리합니다.

1. 프롬프트 인젝션과 자해·자살 위험을 먼저 확인합니다.
2. 규칙 기반 슬롯 엔진이 위기·중독·관계·정서 트랙과 다음 질문을 정합니다.
3. 첫 안내문과 안전·전문기관 정보는 검증된 고정 문구로 제공합니다.
4. 일반 접수 대화의 짧은 반영과 자연스러운 질문 표현은 선택한 LLM이 만듭니다.
5. 대화와 접수 결과를 익명 식별자로 저장하고 관리자 대시보드에서 집계합니다.

핵심은 **“판단은 코드, 표현은 모델”**로 책임을 나눈 것입니다. 모델이 매번
다르게 말할 수는 있지만 질문 순서, 위기 우선순위, 기관 전화번호, 저장 형식은
모델의 즉흥 판단에 맡기지 않습니다.

## 구현된 기능

### 사용자 화면

- 상담 전 고정 안내문과 비밀보장 예외 고지
- 한 번에 질문 하나씩 진행하는 10턴 접수 흐름
- 큰 빠른 답변 버튼과 질문 단계별 추천 답변
- 자동 높이 입력창, Enter 전송, Shift+Enter 줄바꿈
- 중복 전송 차단, 응답 작성 표시, 새 대화 시작
- 현재 확인된 접수 항목과 다음 질문 표시

### 안전과 전문기관 연결

라우팅 우선순위는 **위기 > 중독 > 관계 > 정서**입니다.

- 자해·자살 위험: 현재 계획·수단을 먼저 확인하고 자살예방상담전화 109,
  생명의전화 1588-9191을 안내합니다.
- 중독 문제: 이 챗봇에서 일반 상담을 계속하지 않습니다.
  - 의식 저하·호흡 이상·경련·과다복용·심한 금단: 119 또는 응급실 우선
  - 반복 사용·통제 상실·금단·생활 손상: 중독 전문기관으로 신속 연결
  - 초기 우려: 중독 여부를 단정하지 않고 전문기관 평가 정보 제공
  - 공통: 가까운 중독관리통합지원센터
  - 도박: 1336
  - 마약류: 1342
  - 인터넷·스마트폰·게임 과의존: 1599-0075
- 프롬프트 인젝션: 모델에 전달하기 전에 차단하고 접수 흐름으로 돌아옵니다.

중독 안내 기준과 공식 출처는
[`knowledge/중독-초기면담-전문기관-연결.md`](knowledge/중독-초기면담-전문기관-연결.md)에
정리되어 있습니다.

### 관리자 화면

`/stats.html`에서 다음 기능을 제공합니다.

- 전체 현황 / 관리 대상 / 위기 우선 탭
- 위기, 중독 연결, 긴급, 주의, 지지체계, 미확인, 조기이탈 필터
- 개인번호·세션·주 호소 검색
- 우선순위·개인번호·트랙 정렬
- 개인별 특이 사항 상세 보기
- 현재 조회 결과 CSV 내보내기

## 책임 분리

| 영역 | 담당 | 이유 |
|---|---|---|
| 질문 순서와 슬롯 상태 | `app/intake.py`, `_intake_schema.md` | 반복 질문과 모델 편차 방지 |
| 위기·중독·인젝션 라우팅 | 결정론 코드 | 안전 규칙과 기관 정보를 고정 |
| 상담 문장의 자연스러운 표현 | 선택한 LLM | 사용자 발화에 맞춘 실시간 반응 |
| 도메인 지식 | `KNOWLEDGE_DIR`의 마크다운 | 코드 변경 없이 분야 교체 |
| 대화 저장 | JSON → SQLite 배치 | 원본 로그와 조회용 DB 분리 |
| 화면 | 정적 HTML/CSS/JS | 설치와 배포 단순화 |

## 빠른 시작

요구 사항은 Python 3.11 이상입니다.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

### API 호출 없이 기능 확인

`fake`는 LLM 품질 시연용이 아니라 슬롯·저장·UI 테스트용 결정론 모드입니다.
기본 데모는 synthetic data, localhost-only, no-PII, non-production 교육 환경을
전제로 합니다.

```bash
MODEL=fake KNOWLEDGE_DIR=knowledge \
  .venv/bin/python -m uvicorn app.main:app --reload
```

브라우저에서 다음 주소를 엽니다.

- 챗봇: http://127.0.0.1:8000/
- 관리자 통계: http://127.0.0.1:8000/stats.html

### Codex GPT로 대화 시연

첫 안내문은 고정 문구이고, 이후 일반 접수 응답은 Codex GPT가 생성합니다.
위기·중독·인젝션 응답은 모델을 호출하지 않는 안전 경로를 사용합니다.

```bash
MODEL=codex-cli CODEX_MODEL=gpt-5.4 KNOWLEDGE_DIR=knowledge \
  .venv/bin/python -m uvicorn app.main:app --reload
```

### 모델 제공자

`MODEL` 값으로 응답 백엔드를 고릅니다.

| 설정 | 용도 |
|---|---|
| `auto` | Codex CLI gpt-5.4를 먼저 시도하고 실패 시 Claude CLI, 둘 다 실패하면 fake |
| `fake` | API 없이 테스트하는 결정론 스텁 |
| `codex-cli` 또는 `codex-cli:<model>` | 로컬에 로그인된 Codex CLI 호출 |
| `claude-cli` | 로컬에 로그인된 Claude CLI 호출 |
| Anthropic 모델명 | `ANTHROPIC_API_KEY`를 사용하는 Anthropic API 호출 |

Codex CLI와 Claude CLI는 로컬 명령을 사용하지만 **완전한 오프라인 로컬 모델은
아닙니다**. Ollama, llama.cpp 같은 로컬 추론기를 붙이려면 `app/llm.py`에
동일한 `ask()` 계약을 구현하면 됩니다. 접수 엔진, DB, UI는 그대로 재사용할 수
있습니다.

## 다른 업종으로 바꾸는 방법

모델을 재학습할 필요 없이 `KNOWLEDGE_DIR`의 문서와 접수 스키마를 교체합니다.
실제 복사·수정·검증 절차는 [`docs/customization-guide.md`](docs/customization-guide.md)를
따르세요.

```bash
MODEL=fake KNOWLEDGE_DIR=knowledge-alt \
  .venv/bin/python -m uvicorn app.main:app --reload
```

- `knowledge/`: 상담 초기면담 예시
- `knowledge-alt/`: 커피 브루잉 지식으로 만든 비민감 교육용 starter pack
- `knowledge-math/`: PNK 수학 학습 코칭 — 스키마·페르소나·말투·개인정보 경계까지 전부 교체한 완전한 예제
- `_intake_schema.md`: 수집할 항목, 분류값, 질문 의도, 조건부 슬롯, 화면 문구(`ui` 섹션)
- `_persona.md`: 역할과 금지사항
- `_tone.md`: 말투 규칙
- `_safety_protocol.md`: 안전·인젝션 대응 규칙

학원 초기접수, 병원 문진, 자영업자 등록 등으로 바꿀 때는 새 지식 폴더에 해당
도메인의 문서와 `_intake_schema.md`를 두고 `KNOWLEDGE_DIR`만 변경합니다.
의료·법률처럼 위험도가 높은 분야는 별도의 전문 안전 규칙과 사람 검토가
추가로 필요합니다.

### knowledge pack 검증

runtime `app.intake.load_schema()`는 오류가 있어도 기존 fallback을 유지하기 위해
`None`을 반환합니다. 배포 전 검증은 별도 strict validator로 실행합니다.

```bash
.venv/bin/python scripts/validate_knowledge_pack.py knowledge-alt
.venv/bin/python scripts/validate_knowledge_pack.py knowledge-alt --json
MODEL=fake .venv/bin/python scripts/validate_knowledge_pack.py knowledge-alt --exercise
```

schema-less fallback은 `tests/fixtures/knowledge-fallback/`에서 회귀 테스트로
보존합니다.

### 수학 학습 코치로 실행 (완전 교체 예제)

`knowledge-math/`는 PNK 수학 방법론 문서 21편에 접수 스키마, 페르소나, 말투,
개인정보·인젝션 대응 규칙, 화면 문구까지 전부 교체한 예제입니다.

```bash
MODEL=fake KNOWLEDGE_DIR=knowledge-math \
  .venv/bin/python -m uvicorn app.main:app --reload
```

- 트랙: 개념 > 문제풀이 > 학습습관. 수학학원 데모 화면에는 보호자·전문기관
  공유 고지나 상담형 위기 접수 질문을 노출하지 않습니다.
- 제목·인사말·빠른 선택 칩 같은 화면 고정 문구는 스키마의 `ui` 섹션이
  소유합니다. `/api/config`가 내려주고, `ui`가 없는 지식셋(`knowledge/`)은
  기존 상담 문구를 그대로 씁니다.
- 관리자 통계 화면(`/stats.html`)의 문구는 아직 상담 도메인 고정입니다.

### 지식 문서 형식

```yaml
---
type: concept
aliases: ["별칭1", "별칭2"]
author: "작성자"
date: 2026-01-01
tags: [tag1, tag2]
cluster: optional-cluster-name
---

# 문서 제목
```

제목은 본문 첫 H1에서 읽고, H1이 없으면 파일명을 사용합니다. 정의되지 않은
프론트매터 키도 `Document.meta`에 보존됩니다.

## 말투 프로필과 개인정보 경계

`_tone.md` v2는 제작자의 비공개 로컬 글에서 **문장 자체가 아니라 말투의 작동
원리만 추출해 다시 작성한 프로필**입니다.

레포에 포함되는 것:

- 짧은 반영 뒤 질문 하나로 좁히는 응답 구조
- 단정하지 않고 여지를 두는 표현 원칙
- 합성 예시와 품질 점검 기준

레포에 포함되지 않는 것:

- 원문 문장과 개인 대화
- 원본 파일 경로
- 실제 사건·인물·관계 정보
- 비공개 글 전체나 임베딩 인덱스

따라서 현재 구현은 모델 가중치를 학습한 파인튜닝이나 비공개 문서 전체 RAG가
아닙니다. 매 요청에서 정제된 말투 프로필을 시스템 지시로 읽는 방식입니다.
말투 평가는 비공개 원문을 읽지 않는 합성 문장만 사용합니다.

```bash
.venv/bin/python scripts/voice_eval.py --model codex-cli:gpt-5.4
```

## 데이터 저장 구조

브라우저는 두 개의 무작위 식별자를 사용합니다.

- `session_id`: 한 번의 대화
- `participant_id`: 같은 로컬 브라우저의 여러 세션을 연결하는 익명 개인번호

이 값은 이름이나 전화번호가 아니므로 직접 식별 위험을 낮추지만, 그 자체로 완전한
익명화를 보장하지는 않습니다. 운영 환경에서는 접근 통제, 보존 기간, 암호화,
동의 절차를 별도로 적용해야 합니다.

대화는 먼저 다음 JSON 경로에 저장됩니다.

```text
data/conversations/YYYY-MM-DD/{session_id}.json
```

이후 배치 스크립트가 SQLite에 UPSERT합니다.

```bash
.venv/bin/python scripts/load_to_sqlite.py --date YYYY-MM-DD
```

테이블 구조:

- `participants(participant_id)`
- `conversations(date, session_id, participant_id)`
- `turns(date, session_id, seq)`

운영 서버에서 하루 한 번 실행하는 예시:

```cron
0 3 * * * cd /path/to/repo && .venv/bin/python scripts/load_to_sqlite.py
```

## 100명 합성 데모

실제 인물이나 실제 상담 기록 없이 100명의 합성 프로파일, 대화 로그, 통계 DB를
생성합니다.

```bash
.venv/bin/python scripts/generate_demo_population.py --count 100 --reset
```

생성물:

- `docs/demo-100-profiles.md`
- `data/conversations/YYYY-MM-DD/demo-session-###.json`
- `data/chatlog.db`
- `/stats.html`의 집계와 개인별 특이 사항

## 테스트

### 전체 Python 테스트

```bash
.venv/bin/python -m pytest -q
```

### 브라우저 회귀

```bash
cd scripts/gui-smoke
npm install
npx playwright install chromium   # 최초 1회
node gui-smoke.mjs
```

스테퍼, 빠른 답변, 접수 패널, 지식 폴더 교체 시 UI 비활성화를 검증합니다.
스크린샷은 Git 추적에서 제외됩니다.

### 400회 결정론 회귀

구독 한도 없이 안전·트랙 회귀를 먼저 확인합니다.

```bash
.venv/bin/python scripts/persona_eval.py \
  --runs 20 --workers 8 --patient-mode scripted --bot-model fake
```

실모델 평가는 비용과 사용량을 통제하기 위해 작은 파일럿으로 분리합니다.

```bash
.venv/bin/python scripts/persona_eval.py \
  --runs 1 --workers 1 --persona crisis-hidden \
  --patient-mode codex --patient-model gpt-5.6-luna --bot-model fake
```

## 프로젝트 지도

```text
app/
  chat.py          대화 오케스트레이션
  intake.py        슬롯 스키마 파서와 상태 엔진
  addiction.py     중독 심각도·유형별 전문기관 라우팅
  safety.py        프롬프트 인젝션 탐지와 출력 검증
  llm.py           모델 제공자 어댑터
  storage.py       JSON 대화 저장
  stats.py         관리자 통계 집계
knowledge/         상담 도메인 지식과 운영 규칙
static/            챗봇·통계 화면
scripts/           평가, 합성 데이터, SQLite 적재, 슬라이드 생성
tests/             단위·통합 회귀 테스트
```

## 현재 한계

- 프로토타입은 단일 프로세스 메모리에 세션 상태를 보관하므로 재시작 시 진행 상태가
  복구되지 않습니다. 대화 로그는 JSON에 남습니다.
- Codex/Claude CLI 모드는 턴마다 외부 프로세스를 실행해 API 직접 호출보다 느립니다.
- LLM 응답은 서버에서 완성된 뒤 브라우저가 점진적으로 표시합니다. 실제 토큰
  스트리밍은 아닙니다.
- 익명 개인번호만으로 개인정보 보호가 완성되지는 않습니다.
- 상담·중독 라우팅 기준은 제품 안전장치이며 임상 진단을 대체하지 않습니다.

## 추가 문서

- [데모 시나리오](docs/demo-scenario.md)
- [보안 검토](docs/security-review.md)
- [배포 안내](deploy/README.md)
- [배포 체크리스트](deploy/checklist.md)
- [발표 슬라이드 원고](docs/slides/chatbot_phaseskill_keynote.md)
- [Keynote에서 열 수 있는 PPTX](docs/slides/chatbot_phaseskill_keynote.pptx)
