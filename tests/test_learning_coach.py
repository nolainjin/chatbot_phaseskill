import importlib.util
import json
from pathlib import Path

from app.learning_coach import LearningState, build_turn, choose_question, choose_route, reduce_state


FIXTURE = Path(__file__).parent / "fixtures" / "self_directed_coaching_scenarios.json"
REQUIRED_EXPECTED_KEYS = {"route", "stage", "bottleneck", "question_count", "micro_action", "doc_titles"}
STAGES = {"anchor", "locate", "diagnose", "intervene", "retry", "reflect"}


def _scenarios() -> list[dict]:
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


def test_reducer_matches_fixture_contract() -> None:
    for scenario in _scenarios():
        turn = build_turn(scenario["previous_state"], scenario["messages"][0])
        expected = scenario["expected"]
        assert turn.state.route == expected["route"]
        assert turn.state.stage == expected["stage"]
        assert turn.state.bottleneck == expected["bottleneck"]
        assert turn.micro_action == expected["micro_action"]
        assert len([turn.question]) == expected["question_count"]


def test_reducer_is_deterministic_and_does_not_regress_stage() -> None:
    previous = LearningState(stage="reflect", route="reflection")
    first = reduce_state(previous, "새로운 학습 장면", ())
    second = reduce_state(previous, "새로운 학습 장면", ())
    assert first == second
    assert first.stage == "reflect"
    assert first.bottleneck == "unknown"


def test_ambiguous_input_gets_one_scene_question_without_fixed_study_recipe() -> None:
    assert choose_route("공부를 잘하고 싶어요") == "concrete_scene"
    turn = build_turn(None, "공부를 잘하고 싶어요")
    assert choose_question(turn.state).count("?") + choose_question(turn.state).count("？") <= 1
    assert "5-20-5" not in turn.micro_action
