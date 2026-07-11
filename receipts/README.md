# receipts/ — 단계별 실행 영수증

phase마다 "무엇을, 어떤 모델이, 어떤 도구로, 토큰을 얼마나 쓰며" 진행했는지 남기는 폴더. 각 phase 완료 직후 orchestrator가 생성한다.

## 파일

- `phase-00-intake-init-receipt.md` — 기획 단계(인테이크+스펙리뷰+렌더링) 영수증
- `phase-NN-<slug>-receipt.md` — 각 실행 phase 영수증 (phase-run 중 생성)
- `collect_usage.py` — transcript(JSONL) 실측 집계기

## 수집 방법

Claude Code는 모든 대화를 `~/.claude/projects/<project>/<session>.jsonl`에, sub-agent(워커) 대화를 `<session>/subagents/agent-*.jsonl`에 남긴다. 각 assistant 메시지에 API가 반환한 `usage`(토큰 실측)와 `model`, `tool_use` 블록이 그대로 있어서 `collect_usage.py`가 이를 합산한다.

```bash
python3 receipts/collect_usage.py <transcript.jsonl 또는 디렉토리> [--since ISO --until ISO] [--json]
```

## 항목 설명

| 항목 | 의미 |
|---|---|
| input_tokens | 캐시 미적중 입력 토큰 (정가 과금) |
| output_tokens | 모델이 생성한 출력 토큰 |
| cache_read_input_tokens | 프롬프트 캐시에서 읽은 입력 (정가의 ~10% 과금) |
| cache_creation_input_tokens | 캐시에 새로 쓴 입력 (정가의 ~125% 과금) |
| tool calls | 도구별 호출 횟수 (tool_use 블록 실측) |

## 한계 (정직하게)

- 토큰 수치는 API 실측이지만, **합계 토큰 ≠ 비용**이다. 캐시 읽기/쓰기 과금 가중치가 달라서 비용 환산은 위 가중치를 곱해야 한다.
- 메인 orchestrator 세션은 여러 phase에 걸쳐 이어지므로, phase별 절단은 `--since/--until` 타임스탬프 기준이다 (경계 ±1 메시지 오차 가능).
- 워커(sub-agent) transcript는 phase와 1:1이라 절단 오차가 없다.
- "추론 과정"은 각 receipt의 요약 서술 + 워커의 `## 실행 결과`(phase 파일 내) 병기로 남긴다. 원문 추론 로그가 필요하면 해당 transcript 파일 경로를 receipt에 적어 둔다.
