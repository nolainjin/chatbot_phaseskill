# chatbot_phaseskill

마크다운 지식 폴더와 LLM 제공자만 바꿔 여러 업종의 **지식 기반 대화 챗봇**으로
재사용할 수 있는 데모입니다. 지식셋에 `_intake_schema.md`가 있으면 구조화된
접수 모드로, 없으면 문서 기반 코칭·질의응답 모드로 동작합니다. 현재 기본 예시는
상담기관의 첫 면담이며, 대화 UI, 안전 라우팅, 구조화 저장, SQLite 적재, 관리자
통계 화면까지 한 흐름으로 동작합니다.

> 이 프로젝트는 상담·의료 진단이나 치료를 제공하는 서비스가 아닙니다.
> 사용자의 첫 설명을 정리하고, 위기 또는 중독처럼 별도 도움이 필요한 경우
> 적절한 전문기관 정보를 안내하는 접수 도구입니다.

## 1분 안에 이해하기

사용자가 메시지를 보내면 다음 순서로 처리합니다.

1. 프롬프트 인젝션과 자해·자살 위험을 먼저 확인합니다.
2. 접수 스키마가 있으면 규칙 기반 슬롯 엔진이 다음 질문을 정하고, 없으면 검색된
   지식 문서를 답변 근거로 준비합니다.
3. 팩의 페르소나·말투·범위에 맞춰 선택한 LLM이 답변 또는 코칭을 만듭니다.
4. 접수 팩은 구조화 결과를, 코칭 팩은 대화 기록을 익명 식별자로 저장합니다.
5. 저장 결과는 관리자 대시보드에서 집계합니다.

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

이 절의 라우팅은 기본 상담 팩에만 적용됩니다. 다른 지식셋은 자신의
`_safety_protocol.md`와 문서 범위를 따릅니다.

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
| 대화 모드 | `_intake_schema.md` 유무 | 접수 또는 문서 기반 코칭 선택 |
| 질문 순서와 슬롯 상태 | `app/intake.py`, `_intake_schema.md` | 접수 모드의 반복 질문과 모델 편차 방지 |
| 위기·중독·인젝션 라우팅 | 결정론 코드 | 안전 규칙과 기관 정보를 고정 |
| 상담 문장의 자연스러운 표현 | 선택한 LLM | 사용자 발화에 맞춘 실시간 반응 |
| 도메인 지식 | `KNOWLEDGE_DIR`의 마크다운 | 코드 변경 없이 분야 교체 |
| 대화 저장 | JSON → SQLite 배치 | 원본 로그와 조회용 DB 분리 |
| 화면 | 정적 HTML/CSS/JS | 설치와 배포 단순화 |

## 빠른 시작

요구 사항은 Python 3.11 이상입니다. Windows, macOS, Linux에서 동일하게 동작합니다.

### 더블클릭으로 실행 (설치 지식 없이)

파이썬만 설치되어 있으면 됩니다. 나머지는 런처가 알아서 준비합니다.

| 운영체제 | 실행할 파일 |
|---|---|
| Windows | `시작하기-윈도우.bat` |
| macOS | `시작하기-맥.command` |

처음 실행하면 필요한 구성요소를 자동으로 내려받습니다(몇 분 소요, 인터넷 필요).
준비가 끝나면 브라우저가 자동으로 열립니다. 종료는 검은 창에서 `Ctrl+C`입니다.

파이썬이 없으면 런처가 설치 안내를 띄웁니다. Windows 설치 화면에서
**"Add python.exe to PATH"** 체크를 빠뜨리면 설치해도 다시 막히므로 주의하세요.

macOS에서 "권한이 없습니다"가 뜨면 터미널에서 한 번만:

```bash
chmod +x "시작하기-맥.command"
```

### 명령줄로 실행

```bash
python run.py --model fake       # 환경 준비 후 private loopback 서버 실행
python run.py --check            # 환경 점검만 (아무것도 바꾸지 않음)
python run.py --port 9000 --knowledge knowledge --reload
python run.py --no-browser       # 브라우저 자동 열기 끄기
```

Windows PowerShell에서 `python`이 Microsoft Store로 튀면 `py -3 run.py`를 씁니다.

- 챗봇: http://127.0.0.1:8000/
- 관리자 통계: http://127.0.0.1:8000/stats.html
### 현재 운영 경로: 1주 로컬 데모

`.env.example`은 `MODEL=auto`, `PRIVATE_LOCAL_UI=1`입니다. Codex 기본 모델은
`app/llm.py`의 `CODEX_DEFAULT_MODEL = "gpt-6.1-sol"`에서 관리합니다. 기본 체인은
`codex-cli:gpt-6.1-sol,claude-cli,fake`이며 `MODEL=fake`로 오프라인 검증할 수 있습니다. 현재
승인된 1주 개인 테스트에서는 Mac의 개인 Codex 로그인으로
`codex-cli:gpt-6.1-sol`를 `high` 강도로 사용합니다. `run.py`와 스모크 실행기는
`127.0.0.1`·`::1`·`localhost`에만 바인딩하며, 외부 IP, `0.0.0.0`, 리버스
프록시, Quick Tunnel을 통한 공개 CLI 실행은 지원하지 않습니다.

현재 개인 테스트 명령은 다음과 같습니다.

```bash
python run.py --model codex-cli:gpt-6.1-sol
```

브라우저에서 한 세션은 10턴까지 진행할 수 있습니다. 한도를 채웠거나 새 사례를
시작할 때는 화면의 **새 대화 시작**을 눌러 세션을 재설정합니다. 서버를 완전히
초기화하려면 `Ctrl+C`로 종료한 뒤 같은 명령으로 다시 시작합니다.


### 수동 설치

런처 없이 직접 구성할 때는 가상환경 경로가 OS마다 다릅니다.

| | macOS · Linux | Windows |
|---|---|---|
| 가상환경 생성 | `python3 -m venv .venv` | `py -3 -m venv .venv` |
| 파이썬 경로 | `.venv/bin/python` | `.venv\Scripts\python.exe` |
| 설정 파일 복사 | `cp .env.example .env` | `copy .env.example .env` |

이 문서의 나머지 예시는 `.venv/bin/python`으로 적혀 있습니다. Windows에서는
`.venv\Scripts\python.exe`로 바꿔 읽으세요.

### API 호출 없이 기능 확인

`fake`는 LLM 품질 시연용이 아니라 슬롯·저장·UI 테스트용 결정론 모드입니다.
기본 데모는 synthetic data, localhost-only, no-PII, non-production 교육 환경을
전제로 하며 `PRIVATE_LOCAL_UI=1`인 loopback 요청에서만 UI/API를 엽니다.

```bash
python run.py --model fake --knowledge knowledge --reload
```


### 크로스플랫폼 지원 범위

`.github/workflows/cross-platform.yml`이 windows / ubuntu / macOS × Python
3.11·3.13 매트릭스에서 테스트와 한글 왕복 스모크를 돌립니다. 윈도우 전용
실패(POSIX 전용 API, cp949 인코딩)는 개발 머신에서 재현되지 않으므로 이
매트릭스가 실질적인 회귀 가드입니다.

### 로컬 전용 제한

- 자식 프로세스 파이프와 파일 입출력은 UTF-8로 고정돼 있습니다. 로케일에
  맡기면 한국어 Windows(cp949)에서 한글이 깨집니다.
- canonical launcher는 기본적으로 `fake`를 사용하며, 로컬 Mac에서만 명시적인
  `codex-cli:<model>` 값을 허용합니다. 현재 개인 테스트 설정은
  `codex-cli:gpt-6.1-sol`와 `high` 추론 강도입니다.
- CLI 모델 경로는 `127.0.0.1`·`::1`·`localhost` 바인딩에서만 허용합니다.
  외부 IP, 리버스 프록시, Quick Tunnel을 통한 공개 CLI 실행은 지원하지 않습니다.
- 관리자 통계 API는 `STATS_API_TOKEN`이 설정된 경우에만 열립니다. 브라우저에서
  관리자 토큰을 `sessionStorage.setItem('lmwiki_stats_token', '...')`으로
  설정한 뒤 통계 페이지를 새로고침해야 합니다. 토큰이 없으면 API는
  fail-closed로 503을 반환합니다.

## 다른 업종으로 바꾸는 방법

모델을 재학습할 필요 없이 `KNOWLEDGE_DIR`의 문서와 선택적 접수 스키마를 교체합니다.
실제 복사·수정·검증 절차는 [`docs/customization-guide.md`](docs/customization-guide.md)를
따르세요.

```bash
MODEL=fake KNOWLEDGE_DIR=knowledge-alt \
  .venv/bin/python -m uvicorn app.main:app --reload
```

- `knowledge/`: 상담 초기면담 예시
- `knowledge-alt/`: 커피 브루잉 지식으로 만든 비민감 교육용 starter pack
- `knowledge-math/`: PNK 수학 학습 코칭 — 실제 지식 전달과 문제 풀이 지원을 위한 스키마 없는 코칭 예제
- `_intake_schema.md`: 수집할 항목, 분류값, 질문 의도, 조건부 슬롯, 화면 문구(`ui` 섹션)
- `_persona.md`: 역할과 금지사항
- `_tone.md`: 말투 규칙
- `_safety_protocol.md`: 안전·인젝션 대응 규칙

구조화된 접수가 필요할 때는 새 지식 폴더에 해당 도메인의 문서와
`_intake_schema.md`를 둡니다. 실제 지식 전달이나 코칭이 목적이면 스키마 없이
`_persona.md`, `_tone.md`, `_safety_protocol.md`와 지식 문서만 구성합니다.
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

`knowledge-math/`는 PNK 수학 방법론 문서 21편에 실제 코칭용 페르소나, 말투,
개인정보·인젝션 대응 규칙을 결합한 예제입니다. 접수 스키마를 두지 않으므로
질문이 들어오면 일반 지식전달 경로에서 답변을 생성합니다.

```bash
MODEL=fake KNOWLEDGE_DIR=knowledge-math \
  .venv/bin/python -m uvicorn app.main:app --reload
```

- 개념 설명, 문제 풀이 과정, 학습 습관 점검을 질문의 실제 목적에 맞춰 지원합니다.
- `/api/config`는 `mode=coaching`을 내려주고, 화면은 접수 스테퍼·칩 없이
  질문과 지식 문서 중심으로 표시합니다.
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
.venv/bin/python scripts/tone_eval.py --model codex-cli:gpt-6.1-sol
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
  --patient-mode codex --patient-model gpt-6.1-sol --bot-model fake
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

### 센터 관리번호 링크 (`knowledge-maeum`)

통계 인증이 된 내부 `/stats.html`의 **링크 만들기**에 `1`, `2`, `2026-003`처럼
센터 관리번호를 넣습니다. `POST /api/admin/links`는 기존 통계 토큰 또는 쿠키를
검증하고 요청 호스트 기준의 `/?management_id=…&link_ticket=…` 링크를 반환합니다.
번호는 영문·숫자로 시작하는 1~32자의 영문·숫자·하이픈이며, 전화번호·주민번호는
거부합니다. 센터가 직접 문자로 보내며 서버는 문자를 보내지 않습니다.

화면은 링크의 두 값을 주소창에서 지우고 동의 요청에 전달합니다. 서버 서명이
맞을 때만 해당 관리번호로 세션을 연결합니다. 링크 없이 직접 접속하면 `p_…`
번호를 새로 발급합니다. 발급 기록에는 관리번호의 해시만 저장합니다.
`PARTICIPANT_TICKET_SECRET`을 32바이트 이상으로 고정하면 재시작 후에도 링크를
검증할 수 있습니다. 비워 두면 프로세스별 키를 써 재시작 때 이전 링크가 무효가 됩니다.

`knowledge-maeum`은 `ui.handoff_mode: center`로, 원문과 요약표를 센터 확인 화면에
저장합니다. 마지막에 센터에 바라는 점·질문을 최대 두 개 받고, 전달 완료와 위기
번호·삭제 코드 안내를 보여 줍니다. 센터가 관리번호로 직접 식별하고 상담사를
배정합니다. 이 도구는 매칭이나 센터 결정을 보조하지 않습니다. `referral` 모드는
코드에 남아 있으며, 출구 기능을 쓰는 팩은 종료 모드를 명시해야 합니다.
