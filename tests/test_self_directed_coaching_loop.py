import json
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "self_directed_coaching_scenarios.json"


def test_golden_cases_cover_the_required_coaching_surfaces() -> None:
    scenarios = json.loads(FIXTURE.read_text(encoding="utf-8"))
    routes = {scenario["expected"]["route"] for scenario in scenarios}
    bottlenecks = {scenario["expected"]["bottleneck"] for scenario in scenarios}
    assert {"concrete_scene", "artifact", "strategy", "understanding", "execution", "monitoring", "reflection", "ai_boundary", "provenance", "safety"} <= routes
    assert {"concept", "interpretation", "strategy", "execution", "monitoring", "reflection", "ai_overreliance", "unknown"} <= bottlenecks
    assert all(case["forbidden_terms"] == [] for case in scenarios)


def test_each_turn_contract_requires_one_question_and_direct_action() -> None:
    scenarios = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert all(case["expected"]["question_count"] == 1 for case in scenarios)
    assert all(isinstance(case["expected"]["micro_action"], str) and case["expected"]["micro_action"] for case in scenarios)
