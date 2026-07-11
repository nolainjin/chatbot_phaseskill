#!/usr/bin/env python3
"""Claude Code transcript(JSONL)에서 토큰·도구 사용 실측치를 집계한다.

사용법:
  python3 receipts/collect_usage.py FILE [FILE...] [--since ISO] [--until ISO] [--json]

- FILE: 세션 또는 sub-agent transcript (.jsonl). 디렉토리를 주면 *.jsonl 전부.
- --since/--until: 메인 세션 파일을 phase 시간 창으로 잘라 집계할 때 사용.
- 출력: 모델별 토큰(입력/출력/캐시 읽기/캐시 생성), 도구 호출 횟수, 메시지 수.

한계: 토큰 수치는 Anthropic API가 반환한 usage 필드의 합산(실측)이지만,
캐시 읽기 토큰은 과금 가중치(~0.1x)가 달라 단순 합산은 비용과 1:1이 아니다.
"""
import json
import sys
import argparse
from pathlib import Path
from collections import defaultdict


def iter_records(paths):
    for p in paths:
        p = Path(p)
        files = sorted(p.glob("*.jsonl")) if p.is_dir() else [p]
        for f in files:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield f.name, json.loads(line)
                    except json.JSONDecodeError:
                        continue


def collect(paths, since=None, until=None):
    by_model = defaultdict(lambda: defaultdict(int))
    tools = defaultdict(int)
    msg_count = defaultdict(int)
    files_seen = set()
    for fname, rec in iter_records(paths):
        ts = rec.get("timestamp", "")
        if since and ts and ts < since:
            continue
        if until and ts and ts > until:
            continue
        msg = rec.get("message") or {}
        if rec.get("type") != "assistant" or not isinstance(msg, dict):
            continue
        files_seen.add(fname)
        model = msg.get("model", "unknown")
        msg_count[model] += 1
        usage = msg.get("usage") or {}
        for k in ("input_tokens", "output_tokens",
                  "cache_read_input_tokens", "cache_creation_input_tokens"):
            by_model[model][k] += usage.get(k) or 0
        for block in msg.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tools[block.get("name", "?")] += 1
    return {
        "files": sorted(files_seen),
        "models": {m: dict(v) for m, v in by_model.items()},
        "messages_by_model": dict(msg_count),
        "tool_calls": dict(sorted(tools.items(), key=lambda x: -x[1])),
        "tool_calls_total": sum(tools.values()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = collect(a.paths, a.since, a.until)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    print(f"files: {len(r['files'])}  tool calls: {r['tool_calls_total']}")
    for m, u in r["models"].items():
        total = sum(u.values())
        print(f"\n[{m}] messages={r['messages_by_model'].get(m, 0)}")
        for k, v in u.items():
            pct = (100 * v / total) if total else 0
            print(f"  {k:<28} {v:>12,}  ({pct:4.1f}%)")
    print("\ntool calls:")
    for t, n in r["tool_calls"].items():
        print(f"  {t:<28} {n}")


if __name__ == "__main__":
    main()


# ponytail: 자기 검증 — python3 receipts/collect_usage.py --selftest 대신 아래 assert 데모
def _demo():
    import io, tempfile, os
    rec = {"type": "assistant", "timestamp": "2026-07-11T00:00:00Z",
           "message": {"model": "m1", "usage": {"input_tokens": 10, "output_tokens": 5},
                        "content": [{"type": "tool_use", "name": "Bash"}]}}
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps(rec) + "\n")
        name = f.name
    out = collect([name])
    os.unlink(name)
    assert out["models"]["m1"]["input_tokens"] == 10
    assert out["tool_calls"]["Bash"] == 1
