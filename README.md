# lmwiki-chatbot

지식 데이터(마크다운 + YAML 프론트매터)만 교체하면 다른 분야 챗봇으로
전환할 수 있는 소규모 위키 기반 챗봇. 첫 도메인은 상담 초기 면담.

지식은 `KNOWLEDGE_DIR` 환경변수가 가리키는 디렉토리 하나에서 읽는다.
챗봇 로직과 지식 콘텐츠는 분리되어 있다 — `knowledge/`(상담 초기 면담)와
`knowledge-alt/`(커피 브루잉, 스왑 검증용 다른 도메인) 두 샘플 지식셋이
그 증거다.

## 현재 상태

상담 초기면담 데모는 로컬에서 실제 구동 가능하다. 핵심 파이프라인은
지식 폴더 로딩 → 채팅 API → JSON 저장 → SQLite 배치 → rate limit → 정적 UI까지
구현되어 있고, 진행 이력은
[docs/planning/lmwiki-chatbot-proto/checklist.md](docs/planning/lmwiki-chatbot-proto/checklist.md)
참고.

## 개발 환경 설정

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # ANTHROPIC_API_KEY 등 채워넣기
```

## 테스트

```bash
.venv/bin/python -m pytest -q
```

## 브라우저 스모크 (playwright)

`scripts/gui-smoke/gui-smoke.mjs`는 GUI(스테퍼·퀵리플라이 칩·intake 사이드
패널)의 브라우저 회귀 스위트다. 사전조건은 `.venv` 구성과 playwright
chromium 캐시(최초 1회 `npx playwright install chromium`)다.

```bash
cd scripts/gui-smoke
npm i
node gui-smoke.mjs
```

기대 결과는 20개 단언 전부 PASS, exit 0이다. knowledge 세트로 스테퍼/칩/패널
정상 동작을, knowledge-alt 스왑으로 해당 요소들이 hidden 처리되는지를
검증한다. 스크린샷은 `scripts/gui-smoke/screenshots/`에 저장된다(git 추적
제외).

## 페르소나 평가

구독 한도 없이 400회 규모의 안전·트랙 회귀를 먼저 확인하려면 scripted 환자 +
fake 봇으로 돌린다. 실모델 감각 확인은 그 뒤 소규모로만 진행한다.

```bash
# 로컬 deterministic 400회 — API/Claude CLI 호출 없음
.venv/bin/python scripts/persona_eval.py --runs 20 --workers 8 --patient-mode scripted --bot-model fake

# Codex 환자 시뮬레이터 파일럿 — Codex 사용량 소모, 봇은 fake로 격리
.venv/bin/python scripts/persona_eval.py --runs 1 --workers 1 --persona crisis-hidden --patient-mode codex --patient-model gpt-5.6-luna --bot-model fake

# 실모드 축소 파일럿 — Claude 구독/비용 소모, 사용량 한도 감지 시 기본 fail-fast
.venv/bin/python scripts/persona_eval.py --runs 2 --workers 2 --patient-mode scripted --bot-model claude-cli
```

## 데모 시연

의사 고객 또는 내부 검증용 데모는 API 키 없이 fake 모드로 실행할 수 있다.

```bash
# Fake 모드로 구동 (API 호출 없음)
MODEL=fake KNOWLEDGE_DIR=knowledge .venv/bin/python -m uvicorn app.main:app --reload
```

```bash
# 실제 모델 응답 데모 — 첫 안내문은 UI의 정형 문구, 이후 상담사 답변은 Codex GPT가 생성
MODEL=codex-cli CODEX_MODEL=gpt-5.4 KNOWLEDGE_DIR=knowledge .venv/bin/python -m uvicorn app.main:app --reload
```

이 모드는 접수 상태/안전 라우팅은 결정론 슬롯 엔진이 맡고, 사용자에게 보이는
상담사 문장은 Codex GPT가 매 턴 생성한다. 브라우저는 모델 응답을 받은 뒤
말풍선을 점진적으로 렌더링해 "완성 문장 덩어리"가 아니라 작성 중인 대화처럼 보인다.

자세한 시연 대본과 각 단계별 확인사항은 [데모 시나리오](docs/demo-scenario.md)를 참고하자.

## 말투·안전 프로필

`knowledge/`의 `_persona.md`, `_tone.md`, `_safety_protocol.md`는 검색 문서가 아니라
시스템 프롬프트에만 들어가는 예약 파일이다. `_tone.md`는 SecondBrain 원문을
복사하지 않고 시연용 말투 특성만 추출한 요약 규칙이며, `_safety_protocol.md`는
프롬프트 인젝션·엉뚱한 발화 대응 규칙이다. 공개적으로 검색 가능한 대응 목록은
`knowledge/엉뚱한-발화와-프롬프트-인젝션-대응.md`에 둔다.

## 프론트매터 스키마

지식 문서는 SecondBrain wiki 스키마와 호환된다.

```yaml
---
type: concept
aliases: ["별칭1", "별칭2"]
author: "작성자"
date: 2026-01-01
tags: [tag1, tag2]
cluster: optional-cluster-name   # 선택
---
```

제목은 프론트매터 `title` 키가 아니라 본문 첫 H1(`# 제목`)에서 가져온다.
H1도 없으면 파일명이 제목이 된다. `type`/`aliases`/`author`/`date`/`cluster`
등 스키마에 정의되지 않은 키는 `Document.meta`에 그대로 보존된다.

## 대화 저장 & SQLite 배치 적재

대화 턴은 `data/conversations/YYYY-MM-DD/{session_id}.json`에 실시간
저장된다(`app/storage.py`). 브라우저는 탭/세션 단위 `session_id`와, 같은
로컬 브라우저 사용자를 익명으로 연결하는 무작위 `participant_id`를 함께 보낸다.
이 값은 이름·전화번호가 아니라 UUID 형태의 개인번호라 데이터 반출 시 직접 식별
위험을 낮추면서도 같은 사람의 여러 세션을 나중에 묶을 수 있다.

하루 1회 `scripts/load_to_sqlite.py`가 전일자 JSON을 `data/chatlog.db`에
UPSERT로 적재한다. SQLite는 `participants(participant_id)`,
`conversations(date, session_id, participant_id)`, `turns(date, session_id, seq)`
구조를 쓴다. 같은 브라우저 세션 ID가 날짜를 넘겨 재사용돼도 날짜별 기록은 서로
덮어쓰이지 않고, 여러 세션은 `participant_id`로 연결된다. `--date YYYY-MM-DD`로
특정 날짜를 지정할 수 있다.

실제 배포 환경에서는 크론에 등록한다 (등록 자체는 배포 phase에서 진행):

```bash
0 3 * * * cd /path/to/repo && .venv/bin/python scripts/load_to_sqlite.py
```

## 100명 데모 데이터 + 통계 대시보드

합성 내담자 100명 프로파일과 대화 로그를 한 번에 만들고 SQLite에 적재한다.
실제 인물·실제 상담 기록은 포함하지 않는다.

```bash
.venv/bin/python scripts/generate_demo_population.py --count 100 --reset
```

생성물:
- `docs/demo-100-profiles.md` — 100명 synthetic 프로파일과 scripted turns
- `data/conversations/YYYY-MM-DD/demo-session-###.json` — 챗봇 응답 로그
- `data/chatlog.db` — `participants`/`conversations`/`turns` 적재 결과
- `/stats.html` — `demo-person-` 필터가 적용된 내담자 통계 대시보드. 탭은 **전체 현황 / 관리 대상 / 위기 우선**으로 나뉘고, 개별 특이 사항은 전체·위기·긴급·주의·지지체계·미확인·조기이탈 필터로 다시 좁힐 수 있다.

발표용 슬라이드 원고와 Keynote에서 열 수 있는 PPTX는 다음 파일에 있다.

- `docs/slides/chatbot_phaseskill_keynote.md`
- `docs/slides/chatbot_phaseskill_keynote.pptx`
