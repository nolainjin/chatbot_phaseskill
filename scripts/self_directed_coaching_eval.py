#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app import chat, knowledge, learning_coach, llm
from app.config import Settings

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "self_directed_coaching_scenarios.json"
FORBIDDEN_TERMS = ("보호자", "전문기관", "위기", "자해", "자살")
DOC_ALIASES = {
    "학습장면진단루브릭": "학습장면 진단 루브릭",
    "개입카드": "자기주도학습 개입 카드",
    "코칭사례와반례": "자기주도학습 코칭 사례와 반례",
    "문헌근거와출처상태": "자기주도학습 논문 출처와 검증상태",
}
_INLINE_CODE_RE = re.compile(r"`[^`]*`")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="fake")
    parser.add_argument("--count", type=int)
    parser.add_argument("--knowledge-dir", default=os.getenv("KNOWLEDGE_DIR", "knowledge-self-directed"))
    parser.add_argument("--out", type=Path)
    return parser


def _load_cases() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _expected_doc_matches(expected: str, actual: tuple[str, ...]) -> bool:
    alias = DOC_ALIASES.get(expected, expected)
    return any(expected in title or alias in title for title in actual)


def _question_count(reply: str) -> int:
    return _INLINE_CODE_RE.sub("", reply).count("?")


def _run_case(case: dict, settings: Settings, documents: list[knowledge.Document]) -> dict:
    session_id = f"self-directed-eval-{case['id']}"
    chat._sessions.pop(session_id, None)
    previous = case["previous_state"]
    if isinstance(previous, dict):
        chat._sessions[session_id] = chat.ChatSession(
            session_id=session_id,
            learning_state=learning_coach.LearningState(stage=str(previous.get("stage", "anchor"))),
        )
    result = chat.handle_message(session_id, case["messages"][0], settings)
    state = chat._sessions[session_id].learning_state
    if state is None:
        failures = ["missing_learning_state"]
        actual_state = {"route": "", "stage": "", "bottleneck": ""}
        actual_docs: tuple[str, ...] = ()
    else:
        turn = learning_coach.build_turn(case["previous_state"], case["messages"][0], documents)
        actual_state = {"route": state.route, "stage": state.stage, "bottleneck": state.bottleneck}
        actual_docs = turn.doc_titles
        failures = []
        expected = case["expected"]
        for field in ("route", "stage", "bottleneck"):
            if actual_state[field] != expected[field]:
                failures.append(f"{field}:{actual_state[field]}!={expected[field]}")
        if _question_count(result.get("reply", "")) != expected["question_count"]:
            failures.append("question_count")
        if not result.get("next_action"):
            failures.append("missing_next_action")
        if not _expected_doc_matches(expected["doc_titles"][0], actual_docs):
            failures.append("doc_routing")
    reply = result.get("reply", "")
    forbidden = [term for term in FORBIDDEN_TERMS if term in reply]
    failures.extend(f"forbidden:{term}" for term in forbidden)
    public_keys = {"reply", "turn", "limit_reached", "coach_stage", "next_action"}
    if set(result) != public_keys:
        failures.append("public_fields")
    return {
        "id": case["id"],
        "route": actual_state["route"],
        "stage": actual_state["stage"],
        "bottleneck": actual_state["bottleneck"],
        "reply": reply,
        "question_count": _question_count(reply),
        "micro_action": result.get("next_action", ""),
        "doc_titles": list(actual_docs),
        "public_fields": sorted(result),
        "forbidden_terms": forbidden,
        "passed": not failures,
        "failures": failures,
    }


def run(model: str, count: int | None, knowledge_dir: str) -> dict:
    cases = _load_cases()
    requested_count = len(cases) if count is None else count
    max_count = len(cases) if model == "fake" else 20
    if requested_count < 1 or requested_count > max_count:
        raise ValueError("--count must be between 1 and 20; 21+ calls are blocked")
    if model == "auto":
        raise ValueError("--model auto is not allowed for bounded self-directed evaluation")
    if model != "fake" and not model.startswith("codex-cli:"):
        raise ValueError("--model must be fake or codex-cli:<model>")
    root = Path(knowledge_dir)
    if not (root / "_coaching_contract.md").is_file():
        raise ValueError("knowledge_dir is not a marked self-directed coaching pack")
    selected = cases[:requested_count]
    settings = Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        knowledge_dir=str(root),
        model=model,
        trust_proxy_hops=0,
        daily_request_cap=500,
    )
    documents = knowledge.load_documents(root)
    old_strict = os.environ.get("SELF_DIRECTED_EVAL_STRICT")
    old_timeout = llm.CODEX_TIMEOUT_SEC
    old_retries = llm.CODEX_RETRIES
    if model != "fake":
        os.environ["SELF_DIRECTED_EVAL_STRICT"] = "1"
        llm.CODEX_TIMEOUT_SEC = 15
        llm.CODEX_RETRIES = 1
    try:
        results = []
        for index, case in enumerate(selected, start=1):
            result = _run_case(case, settings, documents)
            results.append(result)
            print(
                f"[self-directed-eval] {index}/{len(selected)} {case['id']} "
                f"{'PASS' if result['passed'] else 'FAIL'}",
                file=sys.stderr,
                flush=True,
            )
    finally:
        if old_strict is None:
            os.environ.pop("SELF_DIRECTED_EVAL_STRICT", None)
        else:
            os.environ["SELF_DIRECTED_EVAL_STRICT"] = old_strict
        llm.CODEX_TIMEOUT_SEC = old_timeout
        llm.CODEX_RETRIES = old_retries
    payload = {
        "model": model,
        "evaluation": "deterministic_contract" if model == "fake" else "external_sample",
        "knowledge_dir": str(root),
        "total": len(results),
        "passed": sum(1 for result in results if result["passed"]),
        "failed": sum(1 for result in results if not result["passed"]),
        "failure_ids": [result["id"] for result in results if not result["passed"]],
        "results": results,
        "cleanup_receipt": "Evaluator owns in-memory sessions only; no server, browser, external model, or persistent repository data was created.",
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["digest"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def main() -> int:
    args = _parser().parse_args()
    try:
        report = run(args.model, args.count, args.knowledge_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except RuntimeError:
        report = {
            "status": "BLOCKED",
            "model": args.model,
            "knowledge_dir": args.knowledge_dir,
            "requested_count": args.count,
            "blocker": "external model CLI or provider call unavailable; no fake fallback was used",
            "cleanup_receipt": "No raw prompt, secret, token, or model output was written.",
        }
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text + "\n", encoding="utf-8")
        print(text, file=sys.stderr)
        return 3
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
