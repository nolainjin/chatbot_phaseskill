import json
import shutil
import subprocess
import sys
from pathlib import Path

from app.knowledge_pack import validate_pack
from app.intake import load_schema

REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = REPO_ROOT / "scripts" / "validate_knowledge_pack.py"


def _run_validator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_knowledge_alt_validates_and_runtime_schema_loads():
    result = validate_pack(REPO_ROOT / "knowledge-alt")

    assert result.valid, [issue.as_dict() for issue in result.errors]
    assert load_schema(REPO_ROOT / "knowledge-alt") is not None


def test_runtime_schema_rejects_symlink(tmp_path):
    target = tmp_path / "real-schema.md"
    shutil.copy(REPO_ROOT / "knowledge" / "_intake_schema.md", target)
    (tmp_path / "_intake_schema.md").symlink_to(target)

    assert load_schema(tmp_path) is None


def test_validator_accepts_schema_less_coaching_pack(tmp_path):
    pack = tmp_path / "coaching"
    pack.mkdir()
    for name in ("_persona.md", "_tone.md", "_safety_protocol.md"):
        (pack / name).write_text("# coaching\n", encoding="utf-8")
    (pack / "lesson.md").write_text(
        "---\ntype: concept\n---\n# Lesson\n\nKnowledge.\n", encoding="utf-8"
    )

    result = validate_pack(pack)
    exercise = validate_pack(pack, exercise=True)

    assert result.valid
    assert exercise.valid
    assert exercise.exercise == {"ok": True, "mode": "coaching", "messages": 0, "unfilled": []}


def test_validator_json_is_deterministic_and_relative():
    first = _run_validator("knowledge-alt", "--json")
    second = _run_validator("knowledge-alt", "--json")

    assert first.returncode == 0
    assert first.stdout == second.stdout
    payload = json.loads(first.stdout)
    assert payload["valid"] is True
    assert "/Volumes/" not in first.stdout


def test_validator_missing_pack_exits_2():
    result = _run_validator("missing-pack", "--json")

    assert result.returncode == 2
    assert json.loads(result.stdout)["errors"][0]["code"] == "PACK_NOT_FOUND"


def test_validator_missing_required_file_exits_1(tmp_path):
    pack = tmp_path / "pack"
    shutil.copytree(REPO_ROOT / "knowledge-alt", pack)
    (pack / "_tone.md").unlink()

    result = _run_validator(str(pack), "--json")

    assert result.returncode == 1
    errors = json.loads(result.stdout)["errors"]
    assert any(error["code"] == "PACK_REQUIRED_FILE_MISSING" and error["path"] == "_tone.md" for error in errors)


def test_validator_semantic_schema_errors_are_actionable(tmp_path):
    pack = tmp_path / "pack"
    shutil.copytree(REPO_ROOT / "knowledge-alt", pack)
    schema = (pack / "_intake_schema.md").read_text(encoding="utf-8")
    schema = schema.replace("id: learner_level", "id: brew_goal", 1)
    schema = schema.replace("priority: 1", "priority: high", 1)
    schema = schema.replace(
        "ask: \"커피 추출을 처음 배우시는지",
        "when: \"missing=위기\"\n      ask: \"커피 추출을 처음 배우시는지",
        1,
    )
    (pack / "_intake_schema.md").write_text(schema, encoding="utf-8")

    result = _run_validator(str(pack), "--json")
    payload = json.loads(result.stdout)
    codes = {error["code"] for error in payload["errors"]}

    assert result.returncode == 1
    assert "SLOT_ID_DUPLICATE" in codes
    assert "SLOT_PRIORITY_TYPE" in codes
    assert "SLOT_CONDITION_UNKNOWN_SLOT" in codes


def test_validator_exercise_reaches_terminal_state():
    result = _run_validator("knowledge-alt", "--exercise", "--json")
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["exercise"]["ok"] is True
    assert payload["exercise"]["unfilled"] == []


def test_self_directed_validator_exercise_reaches_reflect_without_intake():
    result = _run_validator("knowledge-self-directed", "--exercise", "--json")
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["exercise"]["mode"] == "self-directed"
    assert payload["exercise"]["terminal_stage"] == "reflect"
    assert payload["exercise"]["public_fields"] == ["coach_stage", "next_action"]


def test_validator_exercise_reports_unfilled_slot(tmp_path):
    pack = tmp_path / "pack"
    shutil.copytree(REPO_ROOT / "knowledge-alt", pack)
    scenario_path = pack / "_validation_scenario.json"
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    scenario["messages"] = scenario["messages"][:-1]
    scenario_path.write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")

    result = _run_validator(str(pack), "--exercise", "--json")
    payload = json.loads(result.stdout)

    assert result.returncode == 1
    assert payload["errors"][0]["code"] == "EXERCISE_TERMINAL_STATE"
    assert "demo_boundary" in payload["errors"][0]["message"]


def test_validator_rejects_marked_coaching_pack_with_missing_required_document(tmp_path):
    # Given: a coaching-marked pack missing one required coaching document
    pack = tmp_path / "coaching"
    pack.mkdir()
    for name in ("_persona.md", "_tone.md", "_safety_protocol.md", "_coaching_contract.md"):
        (pack / name).write_text("# coaching\n", encoding="utf-8")
    (pack / "학습장면진단루브릭.md").write_text("# rubric\n", encoding="utf-8")
    (pack / "코칭사례와반례.md").write_text("# examples\n", encoding="utf-8")
    (pack / "문헌근거와출처상태.md").write_text("# sources\n", encoding="utf-8")
    (pack / "lesson.md").write_text("---\ntype: concept\n---\n# Lesson\n\nKnowledge.\n", encoding="utf-8")

    # When: the pack validator checks the marked pack
    result = validate_pack(pack)

    # Then: the missing path and marker-specific error code are explicit
    assert not result.valid
    assert any(
        issue.code == "PACK_COACHING_REQUIRED_FILE_MISSING" and issue.path == "개입카드.md"
        for issue in result.errors
    )


def test_validator_accepts_complete_marked_pack_without_marker_reserved_warning(tmp_path):
    pack = tmp_path / "coaching"
    pack.mkdir()
    for name in (
        "_persona.md",
        "_tone.md",
        "_safety_protocol.md",
        "_coaching_contract.md",
        "학습장면진단루브릭.md",
        "개입카드.md",
        "코칭사례와반례.md",
        "문헌근거와출처상태.md",
        "_future.md",
    ):
        content = "# coaching\n" if name.startswith("_") else "---\ntype: concept\n---\n# coaching\n"
        (pack / name).write_text(content, encoding="utf-8")
    (pack / "lesson.md").write_text("---\ntype: concept\n---\n# Lesson\n\nKnowledge.\n", encoding="utf-8")

    result = validate_pack(pack)

    assert result.valid
    assert all(issue.path != "_coaching_contract.md" for issue in result.warnings)
    assert any(issue.code == "PACK_UNKNOWN_RESERVED_FILE" and issue.path == "_future.md" for issue in result.warnings)


def test_validator_preserves_schema_less_behavior_without_coaching_marker(tmp_path):
    pack = tmp_path / "coaching"
    pack.mkdir()
    for name in ("_persona.md", "_tone.md", "_safety_protocol.md", "_future.md"):
        (pack / name).write_text("# coaching\n", encoding="utf-8")
    (pack / "lesson.md").write_text("---\ntype: concept\n---\n# Lesson\n\nKnowledge.\n", encoding="utf-8")

    result = validate_pack(pack)

    assert result.valid
    assert any(issue.code == "PACK_UNKNOWN_RESERVED_FILE" and issue.path == "_future.md" for issue in result.warnings)
