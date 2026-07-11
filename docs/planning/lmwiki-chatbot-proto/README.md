# LM Wiki 챗봇 프로토타입 (lmwiki-chatbot-proto)

지식 데이터(마크다운+프론트매터)만 교체하면 다른 분야로 전환되는 텍스트 챗봇 프로토타입. 목표 배포 주간: 2026-07-20.

## 한눈에

- 대화: 10턴 미만 텍스트 Q&A, 초과 시 거부
- LLM: Anthropic Claude — 기본 `claude-haiku-4-5`, 운영자 키 서버측 env (D02/D07)
- 스택: Python + FastAPI + 바닐라 HTML/JS (D03)
- 저장: 대화 → JSON 파일 → 일 1회 배치가 SQLite 적재 (서버 DB 없음)
- 방어: IP당 1시간 신규 세션 5회 (D05) + 일일 총량 캡 + XFF 스푸핑 차단
- 배포: 저비용/무료 후보 4종(Railway/Fly.io/Oracle Free VM/Hetzner) 중 사용자 확정 후 실배포까지 이번 task에서 완결 (D01/D06)

## 문서 지도

| 문서 | 내용 |
|---|---|
| [origin.md](./origin.md) | 원 요청 verbatim (frozen, sha256 무결성) |
| [intake.md](./intake.md) | 사실/가정/제약/리스크 정규화 |
| [research.md](./research.md) | 호스팅 영속성 리서치 (공식 문서 10건) |
| [decisions.md](./decisions.md) | 사용자 결정 D01~D07 |
| [capabilities.md](./capabilities.md) | 보존 능력 원장 CAP01~19 (적대적 플래그 9건) |
| [spec-review.md](./spec-review.md) | 스펙 리뷰 감사기록 (purpose→critic→judge→triage, pass) |
| [checklist.md](./checklist.md) | phase 진행 현황 (phase-run이 갱신) |

## 실행

```bash
/phase-run lmwiki-chatbot-proto
```

Phase 8은 intervention — 배포 플랫폼 확정과 실배포 실행에 사용자 참여가 필요하다.
