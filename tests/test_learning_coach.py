import importlib.util
import json
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "self_directed_coaching_scenarios.json"
REQUIRED_EXPECTED_KEYS = {"route", "stage", "bottleneck", "question_count", "micro_action", "doc_titles"}
STAGES = {"anchor", "locate", "diagnose", "intervene", "retry", "reflect"}


def _scenarios() -> list[dict[str, object]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_scenario_fixture_has_coaching_contract_shape() -> None:
    scenarios = _scenarios()
    assert 24 <= len(scenarios) <= 40
    for scenario in scenarios:
        assert {"id", "messages", "previous_state", "expected", "forbidden_terms"} <= scenario.keys()
        expected = scenario["expected"]
        assert REQUIRED_EXPECTED_KEYS <= expected.keys()
        assert expected["stage"] in STAGES
        assert expected["question_count"] == 1
        assert expected["micro_action"]
        assert isinstance(expected["doc_titles"], list)


def test_learning_coach_module_is_the_next_contract_boundary() -> None:
    assert importlib.util.find_spec("app.learning_coach") is not None

