import json
import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "bin" / "python"
SCRIPT = ROOT / "scripts" / "self_directed_coaching_eval.py"
RED_TEAM = ROOT / "scripts" / "self_directed_red_team.py"
SPEC = importlib.util.spec_from_file_location("self_directed_coaching_eval", SCRIPT)
EVALUATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(EVALUATOR)


def test_fake_evaluator_runs_all_golden_cases(tmp_path):
    output = tmp_path / "report.json"
    result = subprocess.run(
        [str(PYTHON), str(SCRIPT), "--model", "fake", "--out", str(output)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["total"] == 24
    assert report["failed"] == 0
    assert report["evaluation"] == "deterministic_contract"
    assert len(report["digest"]) == 64
    assert report["results"][0]["reply"]
    assert "[시스템 지시]" not in report["results"][0]["reply"]
    assert "[self-directed-eval] 24/24" in result.stderr


def test_question_count_ignores_question_marks_inside_inline_examples():
    reply = "공식 예시는 `v = ?`입니다. 이 기호는 무엇을 뜻하나요?"

    assert EVALUATOR._question_count(reply) == 1


def test_evaluator_rejects_unbounded_or_auto_models():
    for args in (("--model", "codex-cli:gpt-5.4", "--count", "21"), ("--model", "auto")):
        result = subprocess.run(
            [str(PYTHON), str(SCRIPT), *args],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "ERROR:" in result.stderr


def test_self_directed_red_team_reports_safe_attack_contract(tmp_path):
    output = tmp_path / "red-team.json"
    result = subprocess.run(
        [str(PYTHON), str(RED_TEAM), "--out", str(output)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["total"] == 6
    assert report["failed"] == 0
    assert all("input" in row and "blocked" in row and "llm_called" in row and row["reply_safe"] for row in report["results"])
