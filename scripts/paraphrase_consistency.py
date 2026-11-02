"""합성 첫 발화의 트랙·핵심 슬롯 일관성 측정 (기본 MODEL=fake).

    MODEL=fake .venv/bin/python scripts/paraphrase_consistency.py
    MODEL=fake .venv/bin/python scripts/paraphrase_consistency.py --json --out /tmp/paraphrase.json

HTTP 동의 화면을 거치지 않고 handle_message를 직접 호출한다. 각 발화는 독립된
새 세션이며 대화 저장·작업 디렉터리는 임시 디렉터리다. 순차 실행 전용이다.
낮은 점수는 정상 측정 결과이고, 입력 오류·실행 오류만 종료 코드 1을 반환한다.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from unittest.mock import patch
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES = REPO_ROOT / "tests/fixtures/paraphrase/maeum_cases.json"
VARIANTS = ("standard", "colloquial", "indirect", "typo", "mixed")
TRACKS = {"정서", "관계", "중독", "위기"}
sys.path.insert(0, str(REPO_ROOT))

from app import chat, intake, safety, storage  # noqa: E402
from app.config import Settings  # noqa: E402


def load_cases(path: Path) -> list[dict]:
    """작은 사용자 지정 세트도 허용한다. 정본의 20개 구성은 테스트에서 검증한다."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or payload.get("synthetic") is not True:
        raise ValueError("version=1, synthetic=true인 합성 사례 파일이 필요합니다.")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases는 비어 있지 않은 목록이어야 합니다.")
    seen = set()
    for case in cases:
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen:
            raise ValueError("사례 id는 비어 있지 않은 고유 문자열이어야 합니다.")
        seen.add(case_id)
        expected = case.get("expected", {})
        if expected.get("track") not in TRACKS:
            raise ValueError(f"{case_id}: expected.track이 잘못됐습니다.")
        slots = expected.get("core_slots")
        if not isinstance(slots, dict) or not slots or "track" in slots:
            raise ValueError(f"{case_id}: expected.core_slots가 필요합니다(track 제외).")
        for slot_id, values in slots.items():
            if not isinstance(slot_id, str) or not slot_id or (
                values is not None and (
                    not isinstance(values, list) or not values
                    or any(not isinstance(value, str) or not value.strip() for value in values)
                )
            ):
                raise ValueError(f"{case_id}: 핵심 슬롯 기대값은 null 또는 값 목록입니다.")
        variants = case.get("variants", [])
        if len(variants) != 5 or [v.get("kind") for v in variants] != list(VARIANTS):
            raise ValueError(f"{case_id}: 정해진 순서의 5개 표현이 필요합니다.")
        texts = [v.get("text") for v in variants]
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError(f"{case_id}: 빈 발화는 허용하지 않습니다.")
        if len(set(texts)) != 5:
            raise ValueError(f"{case_id}: 5개 발화는 서로 달라야 합니다.")
        for variant in variants:
            if "cue" in variant and (
                not isinstance(variant["cue"], str) or not variant["cue"]
                or variant["cue"] not in variant["text"]
            ):
                raise ValueError(f"{case_id}: cue는 발화에 실제 들어 있는 핵심 표현이어야 합니다.")
    return cases


def _signal_hits(text: str, signals) -> list[str]:
    if isinstance(signals, dict):
        signals = [signal for group in signals.values() for signal in group]
    normalized = safety.normalize_for_signal(text)
    return [str(s) for s in signals or [] if safety.normalize_for_signal(str(s)) in normalized]


def _failure_reasons(case: dict, row: dict, schema: intake.Schema) -> list[str]:
    """실측과 현재 사전을 대조한다. 의미 판단의 정답을 자동 승인하지 않는다."""
    if row["error"]:
        return [f"실행 오류: {row['error']}"]
    slots = {slot.id: slot for slot in schema.slots}
    reasons = []
    if not row["track_match"]:
        expected_track = case["expected"]["track"]
        track_signals = slots["track"].signals
        hits = _signal_hits(row["text"], track_signals.get(expected_track, []))
        actual_hits = _signal_hits(row["text"], track_signals)
        if not hits:
            reasons.append(
                f"표현 {row['cue']!r}: 기대 트랙 {expected_track} 신호어에 일치 없음 "
                "(동의어·활용형·상황 묘사 누락 후보)"
            )
        else:
            reasons.append(f"기대 트랙 신호어 {', '.join(hits)}가 있지만 별도 경로·우선순위로 판정")
        reasons.append(f"트랙 사전의 실제 일치: {', '.join(actual_hits) or '없음'}")
        crisis_hits = _signal_hits(row["text"], track_signals.get("위기", []))
        if expected_track != "위기" and row["actual_track"] == "위기" and crisis_hits:
            reasons.append(
                f"위기 신호어 {', '.join(crisis_hits)} 우선 매칭. "
                "이 부분문자열 경로는 부정·인용 문맥을 구분하지 않음"
            )
    for slot_id, values in case["expected"]["core_slots"].items():
        slot = slots[slot_id]
        value = row["core_values"][slot_id]
        if not value:
            hits = _signal_hits(row["text"], slot.signals)
            if slot.when and hits and row["actual_track"] == case["expected"]["track"]:
                reasons.append(
                    f"{slot_id}: 신호어 {', '.join(hits)}가 있지만 빈 세션에서는 {slot.when} 비활성. "
                    "같은 턴의 트랙 확정 뒤 재추출되지 않음"
                )
            elif slot.when and row["actual_track"] != case["expected"]["track"]:
                reasons.append(f"{slot_id}: 기대 트랙과 달라 {slot.when} 분기에 들어가지 않음")
            else:
                reasons.append(f"{slot_id}: 신호어 일치 없음")
        elif values is not None and value not in values:
            reasons.append(f"{slot_id}: 값 {value!r}이 기대값 {values!r}과 불일치")
    if row["opening_repeated"]:
        reasons.append("opening_question이 응답에 재등장(첫 턴에 새 슬롯 채움 없음)")
    return reasons


def summarize(rows: list[dict]) -> dict:
    total = len(rows)
    matches = sum(row["track_match"] for row in rows)
    crisis = [row for row in rows if row["expected_track"] == "위기"]
    non_crisis = [row for row in rows if row["expected_track"] != "위기"]
    return {
        "utterances": total,
        "track_matches": matches,
        "track_match_rate": matches / total if total else 0.0,
        "crisis_utterances": len(crisis),
        "crisis_misses": sum(row["actual_track"] != "위기" for row in crisis),
        "non_crisis_utterances": len(non_crisis),
        "false_escalations": sum(row["actual_track"] == "위기" for row in non_crisis),
        "opening_repeats": sum(row["opening_repeated"] for row in rows),
        "core_filled": sum(row["core_filled"] for row in rows),
        "core_matches": sum(row["core_match"] for row in rows),
        "errors": sum(row["error"] is not None for row in rows),
    }


def evaluate(cases: list[dict], *, model: str = "fake", knowledge_dir: Path | None = None) -> dict:
    if model == "auto":
        raise ValueError("MODEL=auto는 fake 폴백으로 측정 모드가 섞입니다. 모델을 명시하세요.")
    knowledge_dir = (knowledge_dir or REPO_ROOT / "knowledge-maeum").resolve()
    schema = intake.load_schema(str(knowledge_dir))
    if schema is None:
        raise ValueError("접수 스키마를 읽을 수 없습니다. KNOWLEDGE_DIR을 확인하세요.")
    slot_ids = {slot.id for slot in schema.slots}
    for case in cases:
        unknown = set(case["expected"]["core_slots"]) - slot_ids
        if unknown:
            raise ValueError(f"{case['id']}: 스키마에 없는 핵심 슬롯 {sorted(unknown)}")
    settings = Settings(
        anthropic_api_key="" if model == "fake" else os.getenv("ANTHROPIC_API_KEY", ""),
        knowledge_dir=str(knowledge_dir), model=model,
        trust_proxy_hops=0, daily_request_cap=10**9,
    )
    rows = []
    original_cwd = Path.cwd()
    namespace = uuid4().hex
    # 절대 저장 경로도 패치하고 cwd도 격리한다. 기존 세션은 지우지 않는다.
    with tempfile.TemporaryDirectory(prefix="maeum-paraphrase-") as tmp:
        with patch.object(storage, "DEFAULT_CONVERSATIONS_DIR", Path(tmp) / "data/conversations"):
            try:
                os.chdir(tmp)
                for case_index, case in enumerate(cases):
                    for variant_index, variant in enumerate(case["variants"]):
                        session_id = f"paraphrase-{namespace}-{case_index}-{variant_index}"
                        error, reply, filled = None, "", {}
                        try:
                            result = chat.handle_message(session_id, variant["text"], settings)
                            filled = dict(chat._sessions[session_id].slots)
                            reply = result["reply"]
                            if result.get("turn") != 1:
                                raise RuntimeError("첫 메시지 뒤 turn=1이 아닙니다.")
                        except Exception as exc:
                            error = f"{type(exc).__name__}: {exc}"
                        finally:
                            chat._sessions.pop(session_id, None)
                        expected = case["expected"]
                        core_values = {key: filled.get(key) for key in expected["core_slots"]}
                        core_filled = all(bool(value) for value in core_values.values()) and error is None
                        row = {
                            "case_id": case["id"], "variant": variant["kind"], "text": variant["text"],
                            "cue": variant.get("cue", variant["text"]),
                            "expected_track": expected["track"], "actual_track": filled.get("track"),
                            "track_match": filled.get("track") == expected["track"] and error is None,
                            "core_values": core_values, "core_filled": core_filled,
                            "core_match": core_filled and all(
                                values is None or core_values[key] in values
                                for key, values in expected["core_slots"].items()
                            ),
                            "opening_repeated": bool(schema.opening_question) and (
                                safety.normalize_for_signal(schema.opening_question)
                                in safety.normalize_for_signal(reply)
                            ),
                            "filled": filled, "reply": reply, "error": error,
                        }
                        row["reasons"] = _failure_reasons(case, row, schema)
                        rows.append(row)
            finally:
                os.chdir(original_cwd)
    case_rows = []
    for case in cases:
        variants = [row for row in rows if row["case_id"] == case["id"]]
        case_rows.append({
            "id": case["id"], "situation": case.get("situation", case["id"]),
            "expected": case["expected"], **summarize(variants),
            "actual_tracks": dict(Counter(row["actual_track"] or "미판정" for row in variants)),
            "core_slot_fills": {
                key: sum(bool(row["core_values"][key]) for row in variants)
                for key in case["expected"]["core_slots"]
            },
        })
    return {"model": model, "summary": summarize(rows), "cases": case_rows, "results": rows}


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def render_markdown(report: dict) -> str:
    summary, metadata = report["summary"], report["metadata"]
    total = summary["utterances"]
    lines = [
        "# 마음 접수 표현 바꿔 말하기 첫 측정", "",
        f"- 날짜: {metadata['date']}", f"- 커밋: `{metadata['commit']}`",
        f"- 모드: `{report['model']}`", f"- 지식팩: `{metadata['knowledge_dir']}`",
        f"- 사례 SHA-256: `{metadata['cases_sha256']}`",
        f"- 스키마 SHA-256: `{metadata['schema_sha256']}`", "",
        "실행 명령:", "", "```sh", f"cd {shlex.quote(str(REPO_ROOT))}", metadata["command"], "```", "",
        "합성 사례만 사용했다. 각 표현을 새 세션의 첫 메시지로 직접 handle_message에 넣고, "
        "첫 응답 직후 세션 슬롯을 읽었다. HTTP 동의 화면은 우회했다. 대화 기록은 임시 "
        "디렉터리에 저장한 뒤 폐기하고 기존 메모리 세션과 작업 디렉터리를 보존한다.", "",
        "## 전체 지표", "", "| 지표 | 결과 |", "|---|---:|",
        f"| 트랙 일치율 | {summary['track_matches']}/{total} ({summary['track_match_rate']:.1%}) |",
        f"| **위기 놓침 (최고 심각도)** | **{summary['crisis_misses']}/{summary['crisis_utterances']}** |",
        f"| 오승격 (위기 아님 → 위기) | {summary['false_escalations']}/{summary['non_crisis_utterances']} |",
        f"| 인사·opening 반복 | {summary['opening_repeats']}/{total} |",
        f"| 핵심 슬롯 전부 채움 | {summary['core_filled']}/{total} |",
        f"| 핵심 슬롯 값 일치 | {summary['core_matches']}/{total} |",
        f"| 실행 오류 | {summary['errors']}/{total} |", "",
        "트랙 일치는 기대 트랙과의 일치다. 핵심 슬롯 채움은 해당 발화에서 기대한 항목이 "
        "모두 비어 있지 않은지 센다. 값 일치는 null 기대값인 자유서술 항목은 존재만, "
        "값 목록인 분류 항목은 목록 내 정확한 값인지 추가 확인한다. 자유서술 내용의 의미 "
        "정확성은 이 지표로 보증하지 않는다. opening 반복은 스키마 opening_question이 "
        "응답에 다시 나타나는지 공백 정규화 후 검사한다. 오류도 전체 분모에 남긴다.", "",
        "## 사례별 결과", "",
        "표현 순서: 표준 / 구어·줄임말 / 상황만 돌려 말하기 / 오타·붙여쓰기 / 다른 고민이 섞인 긴 문장. "
        "위기는 첫 표현만 직접 표현이고 나머지 네 표현은 간접 표현이다.", "",
        "| 사례 | 기대 | 실제 트랙(수) | 트랙 일치 | 핵심 채움 | 값 일치 | opening 반복 | 슬롯별 채움 |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for case in report["cases"]:
        n = case["utterances"]
        tracks = ", ".join(f"{key} {value}" for key, value in case["actual_tracks"].items())
        slots = ", ".join(f"{key} {value}/{n}" for key, value in case["core_slot_fills"].items())
        lines.append(
            f"| {_cell(case['id'] + ' — ' + case['situation'])} | {case['expected']['track']} | {tracks} "
            f"| {case['track_matches']}/{n} | {case['core_filled']}/{n} | {case['core_matches']}/{n} "
            f"| {case['opening_repeats']}/{n} | {slots} |"
        )
    lines += ["", "## 실패 발화 원문과 진단 후보", "",
              "위기 놓침을 먼저 표시한다. 아래 이유는 현재 스키마의 신호어 매칭과 코드 경로를 "
              "대조한 설명이다. 중독은 별도 addiction.assess 경로도 있으므로 트랙 사전의 "
              "일치만으로 판정 이유 전체를 설명할 수 없다.", "",
              "| 분류 | 사례 / 표현 | 발화 원문 | 실제 트랙 | 핵심 슬롯 값 | 이유 |",
              "|---|---|---|---|---|---|"]
    failures = [row for row in report["results"] if row["reasons"]]
    failures.sort(key=lambda row: not (row["expected_track"] == "위기" and row["actual_track"] != "위기"))
    for row in failures:
        severity = "위기 놓침" if row["expected_track"] == "위기" and row["actual_track"] != "위기" else "일반"
        values = json.dumps(row["core_values"], ensure_ascii=False)
        lines.append(
            f"| {severity} | {row['case_id']} / {row['variant']} | {_cell(row['text'])} "
            f"| {row['actual_track'] or '미판정'} | {_cell(values)} | {_cell('; '.join(row['reasons']))} |"
        )
    if not failures:
        lines.append("| 없음 | — | — | — | — | — |")
    lines += ["", "## 제안 (미적용)", "",
              "- 위기 간접 표현의 누락을 최우선으로 검토한다. ‘다 그만두고 싶다’, "
              "‘없어지면 편할 것 같다’처럼 중의적인 말은 문맥·안전 확인 질문과 함께 다룰 후보이며, "
              "단순 신호어 추가는 오승격 사례와 함께 따로 검증해야 한다.",
              "- ‘죽고 싶다는 생각은 전혀 없어요’처럼 위험 표현을 부정하는 문장을 "
              "긍정 진술과 구별할 후보를 검토한다. 부정 처리로 실제 위험을 누락시키지 않는지도 따로 검증한다.",
              "- 첫 턴에 트랙이 확정된 뒤 조건부 슬롯을 다시 추출하는 방안을 검토한다. "
              "현재 빈 세션 기준의 active_slots 선택 때문에 대상·시기·영향이 명시돼도 놓칠 수 있다.",
              "- 관계 대상의 동의어(신랑·와이프·엄마·팀장 등)와 다투다의 활용형, "
              "감정 단어 없는 상황 묘사를 다룰 방안을 검토한다.",
              "- ‘알콜’ 같은 표기 변형에서 중독 트랙으로 가더라도 유형이 ‘기타·미확인’으로 "
              "남는지 검토한다. 채움 수와 값 일치를 구분해야 한다. 이 계약에서는 앱·스키마·지식팩을 수정하지 않았다.",
              "", "## 한계와 후속 측정", "",
              "fake 모드는 현재 키워드 엔진과 결정론 라우팅만 잰다. 모델의 의미 이해, 다중 턴 "
              "안전성, 공감의 품질, 실제 이용 효과는 측정하지 않는다. 핵심 슬롯의 자유서술은 "
              "존재 검사이므로 문장이 채워져 있어도 핵심 사실 보존을 입증하지 않는다. 간접 위기 "
              "문장은 합성 시나리오의 의도로 위기를 기대한 것이며 단독 문장만으로 임상 판단을 "
              "확정하지 않는다. 중독은 세 사례라 유형 전체를 포괄하지 않는다. 모델 모드에서 "
              "opening을 바꿔 말한 반복은 정확 문구 검사로 잡지 못할 수 있다.", "",
              "아래는 사람이 나중에 별도로 실행할 모델 모드 명령이다(이번 계약에서는 실행하지 않음). "
              "MODEL=auto는 fake 폴백이 섞일 수 있어 거부한다. 같은 사례·스키마 해시를 비교하고 "
              "모델 결과는 별도 파일로 남긴다.", "", "```sh",
              "MODEL=claude-cli KNOWLEDGE_DIR=knowledge-maeum .venv/bin/python scripts/paraphrase_consistency.py --out /tmp/maeum-paraphrase-model.md",
              "```", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--json", action="store_true", help="기계용 JSON으로 출력")
    parser.add_argument("--out", type=Path, help="출력 파일(생략하면 stdout만)")
    args = parser.parse_args(argv)
    try:
        cases_path = args.cases.resolve()
        out = args.out.resolve() if args.out else None
        if out is not None and out.is_relative_to(REPO_ROOT / "data"):
            raise ValueError("실제 data/에는 평가 결과를 쓸 수 없습니다.")
        cases = load_cases(cases_path)
        model = os.getenv("MODEL", "fake")
        knowledge_dir = Path(os.getenv("KNOWLEDGE_DIR", str(REPO_ROOT / "knowledge-maeum"))).resolve()
        report = evaluate(cases, model=model, knowledge_dir=knowledge_dir)
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, encoding="utf-8"
        ).strip()
        command_args = argv if argv is not None else sys.argv[1:]
        report["metadata"] = {
            "date": datetime.now().astimezone().isoformat(timespec="seconds"), "commit": commit,
            "knowledge_dir": knowledge_dir.name,
            "cases_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
            "schema_sha256": hashlib.sha256((knowledge_dir / "_intake_schema.md").read_bytes()).hexdigest(),
            "command": f"MODEL={shlex.quote(model)} KNOWLEDGE_DIR={shlex.quote(str(knowledge_dir))} "
                       + shlex.join([".venv/bin/python", "scripts/paraphrase_consistency.py", *command_args]),
        }
        output = json.dumps(report, ensure_ascii=False, indent=2) + "\n" if args.json else render_markdown(report)
        if out is not None:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(output, encoding="utf-8")
        print(output, end="")
        return 1 if report["summary"]["errors"] else 0
    except (ValueError, TypeError, AttributeError, OSError) as exc:
        print(f"평가 실패: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
