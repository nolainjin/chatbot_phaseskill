import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "bin" / "python"
SCRIPT = ROOT / "scripts" / "self_directed_coaching_eval.py"
RED_TEAM = ROOT / "scripts" / "self_directed_red_team.py"


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
