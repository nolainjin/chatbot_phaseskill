#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "anthropic",
#     "pyyaml",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/math_student_eval.py
# 3. Or make executable and run:
#      chmod +x scripts/math_student_eval.py && ./scripts/math_student_eval.py
# ──────────────────

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app import knowledge, llm
from app.config import Settings

EXPECTED_STUDENT_COUNT = 150


@dataclass(frozen=True, slots=True)
class StudentQuestion:
    student_id: str
    question: str
    expected_title: str


@dataclass(frozen=True, slots=True)
class QuestionTemplate:
    cue: str
    expected_title: str
    prompt: str


@dataclass(frozen=True, slots=True)
class QuestionResult:
    student_id: str
    expected_title: str
    matched_titles: tuple[str, ...]
    reply: str
    passed: bool


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    model: str
    knowledge_dir: str
    total: int
    passed: int
    failed: int
    failures: tuple[str, ...]
    digest: str
    results: tuple[QuestionResult, ...]


TEMPLATES: Final[tuple[QuestionTemplate, ...]] = (
    QuestionTemplate("PNK수학의 방향성 개념 토대 교육과정", "PNK수학의 방향성", "개념의 토대가 왜 중요한지"),
    QuestionTemplate("Backwarding 역산 사고 정돈 구하는 대상", "Backwarding(역산해서 사고 정돈하기)", "역산으로 문제를 정리하는 방법"),
    QuestionTemplate("Tagging 방법론 접근 증거 단서", "Tagging(방법론으로 접근하기)", "태깅으로 풀이 단서를 찾는 방법"),
    QuestionTemplate("Why How 셀프 피드백 연습 실수", "Why&How(제대로 된 셀프 피드백)", "피드백을 공부에 적용하는 방법"),
    QuestionTemplate("구체화전략 수준 떨어뜨리기 구체적 명확한 형태", "1. 수준 떨어뜨리기", "구체화전략이 문제 이해에 쓰이는 방식"),
    QuestionTemplate("문제풀이 4단계 읽기 기억 이해 풀이", "문제풀이4단계(고난도 문제를 풀기 위한 필수단계)", "문제풀이 4단계의 순서"),
    QuestionTemplate("사고의 4단계 방법론 유사 연결", "사고의 4단계(풀이 방법 탐색하기)", "사고의 4단계로 풀이 방법을 찾는 방법"),
    QuestionTemplate("다항식 유리식 무리식 초월식 정의역 치역", "TB4.식의 사용된 함수에 따른 형태(다항식, 유무리식, 초월식)", "식의 함수 형태를 먼저 보는 이유"),
    QuestionTemplate("항등식 방정식 부등식 목적 관계식", "TB5.목적에 따른 식의 종류(등식, 부등식)", "식의 목적을 구분하는 방법"),
    QuestionTemplate("평면도형 기하적 분석 개체 요소 관계", "TB6. 도형(연역기하)의 종류 - 평면도형 → 기하적분석", "평면도형을 분석하는 순서"),
    QuestionTemplate("그래프 관련 표현 점 좌표 내분점", "TB7. 그래프와 관련된 표현들", "그래프에서 점과 좌표를 읽는 방법"),
    QuestionTemplate("함수 구조 일대일 이산 연속 증가 감소", "TB8. 함수의 구조 → 일반적으로 함수의 구조가 함수식 종류보다 우선", "함수의 구조를 먼저 확인하는 이유"),
    QuestionTemplate("함수 그래프 우함수 기함수 대칭", "TB9. 함수의 그래프 표현", "우함수와 기함수의 그래프 대칭"),
    QuestionTemplate("대수 지수 로그 밑 통일 소인수분해", "TB11. 대수", "지수와 로그를 계산할 때 볼 것"),
    QuestionTemplate("확률 통계 경우 개수 수형도 근원사건", "TB14. 확률과 통계", "확률과 통계에서 경우를 세는 방법"),
)

VARIANTS: Final[tuple[str, ...]] = (
    "핵심을 짧게 설명해 주세요.",
    "처음 배우는 학생도 이해할 수 있게 설명해 주세요.",
    "문제에 적용하는 장면을 함께 알려 주세요.",
    "어떤 순서로 생각하면 되는지 알려 주세요.",
    "헷갈리기 쉬운 점도 알려 주세요.",
    "간단한 예시를 들어 주세요.",
    "이 방법이 필요한 이유를 알려 주세요.",
    "문제를 읽을 때 무엇을 먼저 봐야 하나요?",
    "비슷한 개념과 어떻게 다른가요?",
    "복습용으로 정리해 주세요.",
)


def build_student_questions() -> tuple[StudentQuestion, ...]:
    questions: list[StudentQuestion] = []
    for template in TEMPLATES:
        for variant in VARIANTS:
            index = len(questions) + 1
            questions.append(
                StudentQuestion(
                    student_id=f"math-student-{index:03d}",
                    question=f"{template.prompt}에 대해 {template.cue}를 중심으로 {template.cue}가 쓰이는 장면을 {variant}",
                    expected_title=template.expected_title,
                )
            )
    return tuple(questions)


def evaluate_student_questions(
    questions: tuple[StudentQuestion, ...],
    knowledge_dir: Path,
    model: str,
) -> EvaluationReport:
    if model != "fake":
        raise ValueError("150명 평가에는 MODEL=fake만 허용됩니다")
    if knowledge_dir.name != "knowledge-math":
        raise ValueError("평가 지식셋은 knowledge-math로 고정됩니다")
    documents = knowledge.load_documents(knowledge_dir)
    results: list[QuestionResult] = []
    failures: list[str] = []
    for question in questions:
        matches = knowledge.search(question.question, documents, top_n=3)
        matched_titles = tuple(document.title for document in matches)
        settings = Settings(
            anthropic_api_key="",
            knowledge_dir=str(knowledge_dir),
            model="fake",
            trust_proxy_hops=0,
            daily_request_cap=500,
        )
        reply = llm.ask(
            system="문서에 근거해서 지식 질문에 답하라.",
            history=[],
            user=question.question,
            doc_titles=list(matched_titles),
            settings=settings,
        )
        passed = question.expected_title in matched_titles and question.expected_title in reply
        result = QuestionResult(
            student_id=question.student_id,
            expected_title=question.expected_title,
            matched_titles=matched_titles,
            reply=reply,
            passed=passed,
        )
        results.append(result)
        if not passed:
            failures.append(f"{question.student_id}: {question.expected_title}")
    result_payload = [
        {
            "student_id": result.student_id,
            "expected_title": result.expected_title,
            "matched_titles": result.matched_titles,
            "reply": result.reply,
            "passed": result.passed,
        }
        for result in results
    ]
    digest_input = json.dumps(result_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
    return EvaluationReport(
        model="fake",
        knowledge_dir=knowledge_dir.name,
        total=len(results),
        passed=sum(result.passed for result in results),
        failed=len(failures),
        failures=tuple(failures),
        digest=digest,
        results=tuple(results),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(".omo/evidence/math-150-student-intake-eval.json"))
    args = parser.parse_args()
    if os.getenv("MODEL") != "fake":
        print("MODEL=fake 환경에서만 실행할 수 있습니다", file=sys.stderr)
        return 2
    report = evaluate_student_questions(
        build_student_questions(),
        knowledge_dir=REPO_ROOT / "knowledge-math",
        model="fake",
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"MODEL=fake KNOWLEDGE_DIR=knowledge-math total={report.total} passed={report.passed} failed={report.failed}")
    print(f"digest={report.digest}")
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
