"""The chat quality harness runs offline (fake model) and its metrics see known failures."""

import importlib.util
from pathlib import Path

from app import chat
from app.config import Settings

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("chat_quality_eval", ROOT / "scripts" / "chat_quality_eval.py")
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)


def _settings():
    return Settings(anthropic_api_key="", knowledge_dir=str(ROOT / "knowledge-maeum"), model="fake",
                    trust_proxy_hops=0, daily_request_cap=500)


def test_cases_are_synthetic_and_grounded():
    data = harness.load_cases()
    assert len(data["cases"]) >= 30
    assert {case["category"] for case in data["cases"]} >= {
        "control", "multi_info", "offtopic", "pre_answered", "correction", "decline", "partial",
        "safety", "closing"}


def test_fake_run_scores_reask_and_offtopic(monkeypatch):
    monkeypatch.setattr(chat, "_sessions", {})
    data = harness.load_cases()
    cases = {case["id"]: case for case in data["cases"]}
    # Keyword capture keeps when_asked slots closed: timing given in the opening is asked again.
    run = harness.run_case(cases["p1-multi-open"], data["personas"], _settings(), 0)
    score = harness.score_case(run, cases["p1-multi-open"], data["personas"])
    assert ["symptom_context"] == [slot for _, slot in score["reask_detail"]][:1]
    assert score["misplaced"] >= 1
    # An off-topic reply stored as the asked slot's answer is counted.
    run = harness.run_case(cases["p1-offtopic-timing"], data["personas"], _settings(), 0)
    score = harness.score_case(run, cases["p1-offtopic-timing"], data["personas"])
    assert score["offtopic_turns"] == 1 and score["offtopic_misfill"] == 1
    summary = harness.summarize([run], [score])
    assert 0 < summary["precision"] < 1
