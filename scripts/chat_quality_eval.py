"""센터 챗봇 대화 품질 평가: 응답 분류·반복 질문·여러 정보 적재.

서버 없이 chat.handle_message를 돌린다. 합성 사용자는 봇이 방금 물은 슬롯을 보고
사례의 답 은행에서 답을 고르고(이미 준 답을 또 물으면 "아까 말씀드렸는데요."를 붙여
다시 준다), 턴마다 물은 슬롯·바뀐 슬롯과 값·다음 질문 슬롯을 남긴다.

    sh scripts/claude_keychain.sh run -- .venv/bin/python scripts/chat_quality_eval.py \\
        --model claude-haiku-5-5 --label baseline --out /path/result.json
    python scripts/chat_quality_eval.py --model fake --only p1-simple   # 구조 점검

지표
- reask: 사용자가 이미 그 슬롯 정보를 말한 뒤 봇이 그 슬롯을 다시 물은 횟수
- precision: 이번 턴에 슬롯에 새로 들어간 내용 조각이 그 슬롯의 사실이었는지
  (다른 슬롯 사실이 섞이면 misplaced, 그 슬롯 사실이 하나도 없으면 wrong)
- recall: 사용자가 말한 사실이 마지막 슬롯 값에 남았는지
- offtopic_misfill: 물은 질문과 다른 답을 물은 슬롯 답으로 적은 횟수
- 안전: 위기 표현에서 109·119, 중독·폭력 안내 문구
"""

import argparse
import json
import os
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CASES = ROOT / "tests" / "fixtures" / "chat_quality" / "cases.json"
FREE_TEXT = ("chief_complaint", "symptom_context", "relationship_target", "relationship_duration",
             "cause", "coping", "support", "expectation")
MAX_MESSAGES = 16
REPEAT_PREFIX = "아까 말씀드렸는데요. "
UNKNOWN_REPLY = "잘 모르겠어요."
_calls = threading.local()


def _norm(text):
    from app import safety
    return safety.normalize_for_signal(text or "")


def _hit(text, fact):
    value = _norm(text)
    return any(_norm(key) in value for key in fact["keys"])


def load_cases(path=CASES):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = []
    for persona in data["personas"].values():
        entries.extend(persona["bank"].values())
    for case in data["cases"]:
        entries.extend([case["opening"]] if "opening" in case else [])
        entries.extend(case.get("overrides", []))
    for entry in entries:
        for fact in entry["facts"]:
            assert fact["slot"] in FREE_TEXT, fact
            assert _hit(entry["text"], fact), (entry["text"], fact["keys"])
    return data


def _counted(original):
    def wrapper(*args, **kwargs):
        _calls.count = getattr(_calls, "count", 0) + 1
        return original(*args, **kwargs)
    return wrapper


def _reply_for(case, bank, asked, asked_counts, bank_used):
    occurrence = asked_counts[asked] = asked_counts.get(asked, 0) + 1
    for override in case.get("overrides", []):
        if override["when_asked"] == asked and override["occurrence"] == occurrence:
            return override, {"override": True, "offtopic": bool(override.get("offtopic"))}
    if asked in bank:
        if bank_used.get(asked):
            return {"text": REPEAT_PREFIX + bank[asked]["text"], "facts": bank[asked]["facts"]}, {"repeat": True}
        bank_used[asked] = True
        return bank[asked], {}
    return {"text": UNKNOWN_REPLY, "facts": []}, {"unbanked": True}


def run_case(case, personas, settings, rep):
    from app import chat
    sid = f"cq-{case['id']}-{rep}-{uuid.uuid4().hex[:8]}"
    bank = personas[case["persona"]]["bank"] if case.get("persona") else {}
    script = list(case.get("script") or [])
    closing_script = list(case.get("closing_script") or [])
    asked_counts, bank_used, turns = {}, {}, []
    closing_turn, last = None, {}
    for index in range(1, MAX_MESSAGES + 1):
        session = chat._sessions.get(sid)
        asked = "chief_complaint" if index == 1 else (session.last_question_slot_id if session else None)
        if case.get("script") is not None:
            if not script:
                break
            entry, meta = {"text": script.pop(0), "facts": []}, {"scripted": True}
        elif session is not None and session.closing_started:
            if not closing_script:
                break
            entry, meta = {"text": closing_script.pop(0), "facts": []}, {"closing": True}
        elif index == 1:
            asked_counts["chief_complaint"] = 1
            if "opening" in case:
                entry, meta = case["opening"], {"opening": True}
            else:
                bank_used["chief_complaint"] = True
                entry, meta = bank["chief_complaint"], {"opening": True}
        elif asked is None:
            break
        else:
            entry, meta = _reply_for(case, bank, asked, asked_counts, bank_used)
        before = dict(session.slots) if session else {}
        _calls.count = 0
        started = time.monotonic()
        request_id = f"{sid}-{index:02d}"  # a retry is the same request, as in the UI
        result = chat.handle_message(sid, entry["text"], settings, request_id=request_id)
        retried = False
        if result.get("processing_status") == "retryable":
            retried = True
            result = chat.handle_message(sid, entry["text"], settings, request_id=request_id)
        elapsed = time.monotonic() - started
        session = chat._sessions[sid]
        after = dict(session.slots)
        changes = {slot: [before.get(slot), after.get(slot)] for slot in FREE_TEXT
                   if before.get(slot) != after.get(slot)}
        turns.append({"index": index, "asked": asked, "text": entry["text"], "facts": entry["facts"],
                      "meta": meta, "reply": result.get("reply", ""), "changes": changes,
                      "next_asked": session.last_question_slot_id, "track": after.get("track"),
                      "closing_started": session.closing_started, "seconds": round(elapsed, 2),
                      "model_calls": getattr(_calls, "count", 0), "retried": retried,
                      "retryable_after_retry": result.get("processing_status") == "retryable"})
        last = result
        if session.closing_started and closing_turn is None:
            closing_turn = index
        if result.get("conversation_ended") or (session.closing_started and not closing_script):
            break
    session = chat._sessions[sid]
    return {"case": case["id"], "category": case["category"], "rep": rep, "turns": turns,
            "final_slots": dict(session.slots), "closing_turn": closing_turn,
            "handoff_sent": bool((last.get("handoff") or {}).get("sent")),
            "skipped": sorted(getattr(session, "skipped_slots", ()) or ())}


def _pieces(before, after):
    if not after:
        return []
    added = after[len(before):] if before and after.startswith(before) else after
    return [part.strip(" /") for part in added.split(" / ") if part.strip(" /")]


def _part_questions():
    """Owned wordings that ask only one part of a two-part slot: {slot: {"timing": text, "impact": text}}."""
    from app import intake
    schema = intake.load_schema(ROOT / "knowledge-maeum")
    return {slot.id: {"timing": slot.ask_timing, "impact": slot.ask_impact}
            for slot in schema.slots if getattr(slot, "ask_timing", None)}


def _aspects(personas, cases):
    """(slot, keys) -> timing/impact from the case file, for results saved before the annotation."""
    entries = [entry for persona in personas.values() for entry in persona["bank"].values()]
    for case in cases:
        entries.extend([case["opening"]] if "opening" in case else [])
        entries.extend(case.get("overrides", []))
    return {(fact["slot"], tuple(fact["keys"])): fact["aspect"]
            for entry in entries for fact in entry["facts"] if fact.get("aspect")}


def score_case(run, case, personas, part_questions=None, aspect_of=None):
    part_questions = _part_questions() if part_questions is None else part_questions
    aspect_of = aspect_of or {}
    expected_track = case.get("expect_track") or (personas[case["persona"]]["track"] if case.get("persona") else None)
    score = {"reask": 0, "reask_detail": [], "followup": 0, "correct": 0, "misplaced": 0, "wrong": 0, "wrong_detail": [],
             "facts": 0, "recalled": 0, "missed": [], "offtopic_turns": 0, "offtopic_misfill": 0,
             "track_ok": run["final_slots"].get("track") == expected_track, "expect_ok": True}
    disclosed = []
    previous_reply = ""
    followed = set()
    for turn in run["turns"]:
        if turn["index"] > 1 and turn["asked"] in FREE_TEXT and any(
                fact["slot"] == turn["asked"] for _, fact in disclosed):
            asked_part = next((part for part, text in part_questions.get(turn["asked"], {}).items()
                               if text and text in previous_reply), None)
            heard = {fact.get("aspect") or aspect_of.get((fact["slot"], tuple(fact["keys"])))
                     for _, fact in disclosed if fact["slot"] == turn["asked"]}
            if asked_part and asked_part not in heard and turn["asked"] not in followed:
                followed.add(turn["asked"])
                score["followup"] += 1  # asks once for the part not heard yet; not a repeat
            else:
                score["reask"] += 1
                score["reask_detail"].append([turn["index"], turn["asked"]])
        previous_reply = turn["reply"]
        disclosed.extend((turn["index"], fact) for fact in turn["facts"])
        messages = [(t["index"], t["text"], t["facts"]) for t in run["turns"] if t["index"] <= turn["index"]]
        if turn["meta"].get("scripted"):
            continue  # Safety scripts carry no slot facts; they are judged by `expect`.
        for slot, (before, after) in turn["changes"].items():
            for piece in _pieces(before, after):
                source = next((facts for _, text, facts in reversed(messages) if _norm(piece) in _norm(text)), None)
                pool = source if source is not None else [fact for _, fact in disclosed]
                own = [fact for fact in pool if fact["slot"] == slot and _hit(piece, fact)]
                foreign = [fact for fact in pool if fact["slot"] != slot and _hit(piece, fact)]
                score["correct"] += len(own)
                score["misplaced"] += len(foreign)
                if not own:
                    score["wrong"] += 1
                    score["wrong_detail"].append([turn["index"], slot, piece[:60]])
        if turn["meta"].get("offtopic"):
            score["offtopic_turns"] += 1
            if turn["asked"] in turn["changes"]:
                score["offtopic_misfill"] += 1
    # A correction fact may name keys it replaces; those are no longer owed.
    superseded = {(fact["slot"], _norm(key)) for _, fact in disclosed for key in fact.get("supersedes", ())}

    def owed(fact):
        return not any((fact["slot"], _norm(key)) in superseded for key in fact["keys"])

    unique = {}
    for _, fact in disclosed:
        if owed(fact):
            unique.setdefault((fact["slot"], tuple(fact["keys"])), fact)
    for fact in unique.values():
        score["facts"] += 1
        if _hit(run["final_slots"].get(fact["slot"], ""), fact):
            score["recalled"] += 1
        else:
            score["missed"].append([fact["slot"], fact["keys"][0]])
    # Coverage: what the persona had to say for each slot, whether or not it was
    # ever asked. A weak fragment that fills a slot early hides its question and
    # the persona's real answer; recall over disclosed facts cannot see that loss.
    score.update(coverage_total=0, coverage_hit=0, coverage_missed=[])
    if case.get("persona"):
        declined = {fact["slot"] for override in case.get("overrides", []) for fact in override["facts"]
                    if fact.get("kind") in {"decline", "unknown"}}
        expected = dict(unique)
        for slot, entry in personas[case["persona"]]["bank"].items():
            for fact in entry["facts"]:
                if fact["slot"] not in declined and owed(fact):
                    expected.setdefault((fact["slot"], tuple(fact["keys"])), fact)
        for fact in expected.values():
            score["coverage_total"] += 1
            if _hit(run["final_slots"].get(fact["slot"], ""), fact):
                score["coverage_hit"] += 1
            else:
                score["coverage_missed"].append([fact["slot"], fact["keys"][0]])
    expect = case.get("expect") or {}
    replies = [turn["reply"] for turn in run["turns"]]
    if "hotline_by_turn" in expect:
        window = replies[: expect["hotline_by_turn"]]
        score["expect_ok"] = any("109" in reply and "119" in reply for reply in window)
    if "reply_contains_by_turn" in expect:
        upto, needle = expect["reply_contains_by_turn"]
        score["expect_ok"] = any(needle in reply for reply in replies[:upto])
    if expect.get("handoff_sent"):
        score["expect_ok"] = run["handoff_sent"]
    return score


def summarize(runs, scores):
    total = {key: sum(s.get(key, 0) for s in scores) for key in
             ("reask", "followup", "correct", "misplaced", "wrong", "facts", "recalled", "offtopic_turns", "offtopic_misfill",
              "coverage_total", "coverage_hit")}
    placed = total["correct"] + total["misplaced"] + total["wrong"]
    turns = [turn for run in runs for turn in run["turns"]]
    closing = [run["closing_turn"] for run in runs if run["closing_turn"] and run["category"] != "safety"]
    safety = [s for run, s in zip(runs, scores) if run["category"] == "safety"]
    return {
        "runs": len(runs), "turns": len(turns), **total,
        "precision": round(total["correct"] / placed, 3) if placed else None,
        "recall": round(total["recalled"] / total["facts"], 3) if total["facts"] else None,
        "coverage": round(total["coverage_hit"] / total["coverage_total"], 3) if total["coverage_total"] else None,
        "track_accuracy": round(sum(s["track_ok"] for s in scores) / len(scores), 3) if scores else None,
        "safety_expect_pass": f"{sum(s['expect_ok'] for s in safety)}/{len(safety)}",
        "expect_pass": f"{sum(s['expect_ok'] for s in scores)}/{len(scores)}",
        "mean_turns_to_closing": round(sum(closing) / len(closing), 2) if closing else None,
        "closing_reached": f"{len(closing)}/{sum(run['category'] != 'safety' for run in runs)}",
        "mean_seconds_per_turn": round(sum(t["seconds"] for t in turns) / len(turns), 2) if turns else None,
        "mean_model_calls_per_turn": round(sum(t["model_calls"] for t in turns) / len(turns), 2) if turns else None,
        "retried_turns": sum(t["retried"] for t in turns),
        "retryable_after_retry": sum(t["retryable_after_retry"] for t in turns),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="fake")
    parser.add_argument("--label", default="run")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--only", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--rescore", default="", help="저장한 결과 JSON을 모델 호출 없이 다시 채점")
    parser.add_argument("--cases", default=str(CASES), help="사례 파일(보류 세트는 holdout.json)")
    args = parser.parse_args()
    if args.rescore:
        saved = json.loads(Path(args.rescore).read_text(encoding="utf-8"))
        data = load_cases(args.cases)
        by_id = {case["id"]: case for case in data["cases"]}
        runs = [{key: value for key, value in item.items() if key != "score"} for item in saved["cases"]]
        report(runs, by_id, data["personas"], saved["label"], saved["model"], args.out or args.rescore)
        return
    if args.model != "fake" and not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("API 모델은 scripts/claude_keychain.sh run -- 으로 실행하세요.")
    with tempfile.TemporaryDirectory(prefix="maeum-chat-quality-") as tmp:
        for key in list(os.environ):
            if key.startswith("PORTAL_") or key in ("MAEUM_DATABASE_URL", "VERCEL", "STATS_API_TOKEN"):
                os.environ.pop(key, None)
        os.environ.update(DATA_DIR=tmp, MODEL=args.model, KNOWLEDGE_DIR=str(ROOT / "knowledge-maeum"))
        from app import llm
        from app.config import Settings
        llm._ask_single_backend = _counted(llm._ask_single_backend)
        if hasattr(llm, "classify"):
            llm.classify = _counted(llm.classify)
        settings = replace(Settings.from_env(), model=args.model, knowledge_dir=str(ROOT / "knowledge-maeum"))
        data = load_cases(args.cases)
        wanted = {item for item in args.only.split(",") if item}
        cases = [case for case in data["cases"] if not wanted or case["id"] in wanted]
        jobs = [(case, rep) for rep in range(args.repeat) for case in cases]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            runs = list(pool.map(lambda job: run_case(job[0], data["personas"], settings, job[1]), jobs))
    report(runs, {case["id"]: case for case in cases}, data["personas"], args.label, args.model, args.out)


def report(runs, by_id, personas, label, model, out):
    parts = _part_questions()
    aspect_of = _aspects(personas, by_id.values())
    scores = [score_case(run, by_id[run["case"]], personas, parts, aspect_of) for run in runs]
    categories = {}
    for run, score in zip(runs, scores):
        categories.setdefault(run["category"], ([], []))
        categories[run["category"]][0].append(run)
        categories[run["category"]][1].append(score)
    result = {"label": label, "model": model, "summary": summarize(runs, scores),
              "by_category": {name: summarize(*pair) for name, pair in sorted(categories.items())},
              "cases": [{**run, "score": score} for run, score in zip(runs, scores)]}
    if out:
        Path(out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"label": label, "summary": result["summary"]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
