from pathlib import Path

import pytest

from scripts.math_student_eval import (
    EXPECTED_STUDENT_COUNT,
    build_student_questions,
    evaluate_student_questions,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_builds_deterministic_safe_student_question_corpus():
    first = build_student_questions()
    second = build_student_questions()

    assert len(first) == EXPECTED_STUDENT_COUNT == 150
    assert first == second
    assert len({question.student_id for question in first}) == EXPECTED_STUDENT_COUNT
    forbidden = ("보호자", "전문기관", "위기", "자해", "자살")
    corpus = "\n".join(question.question for question in first)
    assert not any(term in corpus for term in forbidden)


def test_evaluates_all_students_with_fake_and_fixed_math_pack(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    report = evaluate_student_questions(
        build_student_questions(),
        knowledge_dir=REPO_ROOT / "knowledge-math",
        model="fake",
    )

    assert report.model == "fake"
    assert report.knowledge_dir == "knowledge-math"
    assert report.total == EXPECTED_STUDENT_COUNT
    assert report.passed == EXPECTED_STUDENT_COUNT
    assert report.failed == 0
    assert report.failures == ()
    replies = "\n".join(result.reply for result in report.results)
    assert not any(term in replies for term in ("보호자", "전문기관", "위기", "자해", "자살"))
    assert report.digest == evaluate_student_questions(
        build_student_questions(),
        knowledge_dir=REPO_ROOT / "knowledge-math",
        model="fake",
    ).digest


def test_evaluation_rejects_real_model_configuration():
    with pytest.raises(ValueError, match="MODEL=fake"):
        evaluate_student_questions(
            build_student_questions()[:1],
            knowledge_dir=REPO_ROOT / "knowledge-math",
            model="claude-cli",
        )
