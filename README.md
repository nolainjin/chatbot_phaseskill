# lmwiki-chatbot

지식 데이터(마크다운 + YAML 프론트매터)만 교체하면 다른 분야 챗봇으로
전환할 수 있는 소규모 위키 기반 챗봇. 첫 도메인은 상담 초기 면담.

지식은 `KNOWLEDGE_DIR` 환경변수가 가리키는 디렉토리 하나에서 읽는다.
챗봇 로직과 지식 콘텐츠는 분리되어 있다 — `knowledge/`(상담 초기 면담)와
`knowledge-alt/`(커피 브루잉, 스왑 검증용 다른 도메인) 두 샘플 지식셋이
그 증거다.

## 현재 상태

이 리포는 phase 단위로 만들어지는 중이다. Phase 1(지식베이스 로더 +
프로젝트 뼈대)까지 완료된 상태. 진행 상황은
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
저장된다(`app/storage.py`). 하루 1회 `scripts/load_to_sqlite.py`가 전일자
JSON을 `data/chatlog.db`에 UPSERT로 적재한다 — 세션+턴순번 PK라 재실행해도
중복되지 않는다(멱등). `--date YYYY-MM-DD`로 특정 날짜를 지정할 수 있다.

실제 배포 환경에서는 크론에 등록한다 (등록 자체는 배포 phase에서 진행):

```bash
0 3 * * * cd /path/to/repo && .venv/bin/python scripts/load_to_sqlite.py
```
