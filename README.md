# LM Wiki 챗봇 프로토타입

지식 데이터(마크다운 + YAML 프론트매터)만 교체하면 다른 분야로 전환되는
텍스트 챗봇 프로토타입. 챗봇 로직과 지식 콘텐츠를 분리해, `KNOWLEDGE_DIR`
환경변수 하나로 어떤 지식베이스를 쓸지 정한다.

## 시작하기

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # ANTHROPIC_API_KEY 등 채워넣기
.venv/bin/python -m pytest -q
```

## 구조

```
app/
  config.py     - 환경변수(Settings) 단일 진입점
  knowledge.py  - 지식베이스 로더 + 키워드 검색
knowledge/       - 샘플 지식셋 (사내 IT 헬프데스크)
knowledge-alt/    - 샘플 지식셋 (홈카페 원두 가이드, 스왑 검증용)
tests/            - pytest 테스트
```

`knowledge/`, `knowledge-alt/`는 서로 완전히 다른 도메인 샘플 지식셋이다.
`KNOWLEDGE_DIR`을 바꿔 로딩하는 지식만 교체해도 챗봇 로직 수정 없이 다른
분야로 전환되는지 확인하는 스왑 실증에 쓰인다.

## 개발 진행 상황

전체 phase 계획과 진행 현황은
[docs/planning/lmwiki-chatbot-proto/checklist.md](./docs/planning/lmwiki-chatbot-proto/checklist.md)를
참고한다.
