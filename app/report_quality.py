"""Conservative, read-only quality projection for legacy intake reports."""

from copy import deepcopy
import re
from typing import Any

from app import safety


ALGORITHM_VERSION = "report-quality-v1"


def _normalized(value: str) -> str:
    return re.sub(r"[\s.,!?。·'\"“”‘’]", "", value).lower()


def _turn_index(documents: list[dict[str, Any]]) -> tuple[dict[tuple[str, int], list[dict]], dict[str, list[dict]]]:
    by_key: dict[tuple[str, int], list[dict]] = {}
    by_day: dict[str, list[dict]] = {}
    for document in documents:
        if not isinstance(document, dict) or not isinstance(document.get("day"), str):
            continue
        day = document["day"]
        turns = document.get("turns")
        if not isinstance(turns, list):
            continue
        for turn in turns:
            if (not isinstance(turn, dict) or not isinstance(turn.get("seq"), int)
                    or isinstance(turn.get("seq"), bool)
                    or turn.get("role") not in {"user", "assistant"}
                    or not isinstance(turn.get("text"), str)):
                continue
            item = {"day": day, "seq": turn["seq"], "role": turn["role"], "text": turn["text"]}
            by_key.setdefault((day, turn["seq"]), []).append(item)
            by_day.setdefault(day, []).append(item)
    for turns in by_day.values():
        turns.sort(key=lambda item: item["seq"])
    return by_key, by_day


def _canonical_source(source: Any, by_key: dict) -> tuple[dict, dict] | None:
    if (not isinstance(source, dict) or not isinstance(source.get("day"), str)
            or not isinstance(source.get("seq"), int)
            or isinstance(source.get("seq"), bool)
            or source.get("role", "user") != "user"):
        return None
    matches = by_key.get((source["day"], source["seq"]), [])
    if len(matches) != 1 or matches[0].get("role") != "user":
        return None
    pointer = {"day": source["day"], "seq": source["seq"], "role": "user"}
    return pointer, matches[0]


def _resolve_source(
    field: str,
    value: str,
    summary: dict,
    sources: dict,
    by_key: dict,
) -> tuple[dict, dict] | None:
    candidates = sources.get(field)
    if isinstance(candidates, list) and candidates:
        resolved = [_canonical_source(candidate, by_key) for candidate in candidates]
        resolved = [item for item in resolved if item is not None
                    and _normalized(item[1]["text"]) == _normalized(value)]
        if len(candidates) == 1 and len(resolved) == 1:
            return resolved[0]
        return None
    evidence = summary.get("slot_evidence", {}).get(field, {})
    if isinstance(evidence, dict) and evidence.get("source") is not None:
        resolved = _canonical_source(evidence.get("source"), by_key)
        if resolved is not None and _normalized(resolved[1]["text"]) == _normalized(value):
            return resolved
        return None
    wanted = _normalized(value)
    matches = []
    for turns in by_key.values():
        for turn in turns:
            if turn.get("role") == "user" and _normalized(turn["text"]) == wanted:
                matches.append(turn)
    if len(matches) != 1:
        return None
    turn = matches[0]
    return _canonical_source(
        {"day": turn["day"], "seq": turn["seq"], "role": "user"}, by_key
    )


def _previous_assistant(turn: dict, by_day: dict[str, list[dict]]) -> str | None:
    previous = [item for item in by_day.get(turn["day"], []) if item["seq"] < turn["seq"]]
    if not previous:
        return None
    latest_seq = max(item["seq"] for item in previous)
    latest = [item for item in previous if item["seq"] == latest_seq]
    return latest[0]["text"] if len(latest) == 1 and latest[0].get("role") == "assistant" else None


def _question_kinds(text: str | None) -> set[str]:
    if not text:
        return set()
    clauses = [part.strip() for part in re.split(r"(?<=[.!?。])\s+|\n+", text) if part.strip()]
    normalized = safety.normalize_for_signal(clauses[-1] if clauses else text)
    kinds = set()
    if any(marker in normalized for marker in ("상담에서", "어떤도움", "가장기대")):
        kinds.add("expectation")
    if any(marker in normalized for marker in (
        "도와주는사람", "알고있거나", "곁에서", "의지할사람", "이야기를아는사람",
    )):
        kinds.add("support")
    if any(marker in normalized for marker in (
        "언제부터", "주로언제", "가장크게올라오는때", "시작됐", "기간", "일상에는어떤영향",
    )):
        kinds.add("timing")
    return kinds


def _support_statement(value: str) -> bool:
    normalized = safety.normalize_for_signal(value)
    direct_support = any(marker in normalized for marker in (
        "도와주", "곁에서", "이이야기를알고", "내상황을알고", "털어놓", "들어줘",
        "들어주", "의지", "상의", "연락할사람",
        "혼자예요", "혼자입니다", "아무도없", "아무도몰라", "도와줄사람이없",
        "말할사람이없", "얘기할사람이없", "털어놓을사람이없",
    ))
    disclosure = any(
        f"{person}{particle}{speech}" in normalized
        for person in ("친구", "가족", "부모", "엄마", "아빠", "선생님", "상담사", "동료")
        for particle in ("에게", "한테", "와", "랑")
        for speech in ("말했", "말해봤", "얘기했", "얘기해", "이야기했", "이야기해")
    )
    return direct_support or disclosure


def _expectation_statement(value: str) -> bool:
    normalized = safety.normalize_for_signal(value)
    return any(marker in normalized for marker in (
        "기대", "원하", "바라", "도움", "편해지", "나아지", "바뀌", "좋겠", "했으면",
        "줄었으면", "알고싶", "배우고싶", "정리하고싶", "해결하고싶", "상담받", "상담을받",
    ))


def _time_context(value: str) -> bool:
    normalized = safety.normalize_for_signal(value)
    return any(marker in normalized for marker in (
        "언제부터", "전부터", "개월", "달전", "주전", "이후부터", "아침", "저녁", "밤에",
        "새벽", "주로", "때는", "때마다", "앉으면", "시작하면",
    ))


def _academic_context(text: str) -> bool:
    normalized = safety.normalize_for_signal(text)
    return any(marker in normalized for marker in (
        "공부", "학업", "시험", "성적", "중간고사", "기말고사", "과목", "집중", "영어", "수학",
    ))


def _academic_competition(text: str) -> bool:
    normalized = safety.normalize_for_signal(text)
    return _academic_context(text) and any(marker in normalized for marker in (
        "따라잡", "비교", "앞서", "뒤처", "성적", "점수", "등수", "더잘", "못할까",
    ))


def _comparison_worry(text: str) -> bool:
    normalized = safety.normalize_for_signal(text)
    projected_competition = any(marker in normalized for marker in (
        "따라잡힐까", "따라잡히지않나", "뒤처질까", "뒤처지지않을까", "못할까",
    ))
    internal_worry = any(marker in normalized for marker in (
        "걱정", "불안", "생각", "두려", "무섭",
    ))
    return projected_competition and internal_worry


def _source_turn(field: str, summary: dict, sources: dict, by_key: dict) -> tuple[dict, dict] | None:
    if field in sources:
        candidates = sources.get(field)
        if not isinstance(candidates, list) or len(candidates) != 1:
            return None
        return _canonical_source(candidates[0], by_key)
    evidence = summary.get("slot_evidence", {}).get(field, {})
    if isinstance(evidence, dict):
        return _canonical_source(evidence.get("source"), by_key)
    return None


def _relationship_problem(text: str) -> bool:
    normalized = safety.normalize_for_signal(text)
    return any(marker in normalized for marker in (
        "갈등", "다툼", "다퉜", "싸움", "싸웠", "사이가안", "이혼", "괴롭힘", "따돌림",
        "관계때문", "친구관계", "말다툼", "연락을끊", "무시당", "무시했", "조롱",
        "놀리", "놀려", "멀어졌", "멀어진", "어색", "피해", "피하",
    ))


def project(summary: dict, sources: dict, documents: list[dict] | None) -> dict:
    """Return a deep-copied display projection; never mutate stored inputs."""
    projected_summary = deepcopy(summary)
    projected_sources = deepcopy(sources) if isinstance(sources, dict) else {}
    if isinstance(documents, list) and any(
        isinstance(document, dict) and document.get("raw_purged_at")
        for document in documents
    ):
        return {"summary": projected_summary, "sources": projected_sources}
    if not isinstance(projected_summary, dict):
        return {"summary": projected_summary, "sources": projected_sources}

    slots = projected_summary.get("slots")
    if not isinstance(slots, dict):
        return {"summary": projected_summary, "sources": projected_sources}
    evidence = projected_summary.setdefault("slot_evidence", {})
    if not isinstance(evidence, dict):
        evidence = {}
        projected_summary["slot_evidence"] = evidence
    unfilled = projected_summary.setdefault("unfilled", {})
    if not isinstance(unfilled, dict):
        unfilled = {}
        projected_summary["unfilled"] = unfilled

    docs = documents if isinstance(documents, list) else []
    by_key, by_day = _turn_index(docs)
    repairs: list[dict[str, str]] = []
    moved: list[tuple[str, dict]] = []

    def repair(field: str, reason: str) -> None:
        item = {"field": field, "reason": reason}
        if item not in repairs:
            repairs.append(item)

    def unconfirm(field: str, reason: str) -> None:
        slots.pop(field, None)
        evidence[field] = {"status": "unconfirmed"}
        unfilled[field] = "미확인"
        projected_sources.pop(field, None)
        repair(field, reason)

    support = slots.get("support")
    if isinstance(support, str) and not _support_statement(support):
        resolved = _resolve_source("support", support, projected_summary, projected_sources, by_key) if docs else None
        asked_support = False
        if resolved is not None:
            asked_support = _question_kinds(_previous_assistant(resolved[1], by_day)) == {"support"}
        summary_only_mismatch = not docs and _comparison_worry(support)
        positive_mismatch = _comparison_worry(support)
        if (resolved is not None and not asked_support and positive_mismatch) or summary_only_mismatch:
            unconfirm("support", "unsupported_support_value")

    expectation = slots.get("expectation")
    if isinstance(expectation, str) and not _expectation_statement(expectation):
        resolved = _resolve_source(
            "expectation", expectation, projected_summary, projected_sources, by_key
        ) if docs else None
        kinds = _question_kinds(_previous_assistant(resolved[1], by_day)) if resolved else set()
        if resolved is not None and kinds == {"timing"} and _time_context(expectation):
            moved.append((expectation, resolved[0]))
            unconfirm("expectation", "question_context_mismatch")
        elif resolved is not None and len(kinds) == 1 and "expectation" not in kinds:
            unconfirm("expectation", "unsupported_expectation_value")
        elif not docs and _time_context(expectation):
            unconfirm("expectation", "time_context_not_expectation")

    user_text = " ".join(
        turn["text"] for turns in by_day.values() for turn in turns if turn.get("role") == "user"
    )
    track_source = _source_turn("track", projected_summary, projected_sources, by_key) if docs else None
    reclassify_track = (
        bool(docs)
        and projected_summary.get("track") == "관계"
        and projected_summary.get("track_inferred") is True
        and track_source is not None
        and _comparison_worry(track_source[1]["text"])
        and _academic_context(user_text)
        and not _relationship_problem(user_text)
    )
    if reclassify_track:
        projected_summary["track"] = "정서"
        slots["track"] = "정서"
        projected_summary["track_inferred"] = True
        evidence["track"] = {"status": "inferred", "value": "정서"}
        projected_sources.pop("track", None)
        repair("track", "inferred_academic_context")

        duration = slots.get("relationship_duration")
        if isinstance(duration, str) and _time_context(duration):
            resolved = _resolve_source(
                "relationship_duration", duration, projected_summary, projected_sources, by_key
            )
            if resolved is not None and "timing" in _question_kinds(
                _previous_assistant(resolved[1], by_day)
            ):
                moved.append((duration, resolved[0]))
        for field in ("relationship_target", "relationship_duration"):
            slots.pop(field, None)
            evidence.pop(field, None)
            unfilled.pop(field, None)
            projected_sources.pop(field, None)
            repair(field, "inactive_after_track_projection")

    if moved:
        moved.sort(key=lambda item: (item[1]["day"], item[1]["seq"]))
        values = []
        current = slots.get("symptom_context")
        if isinstance(current, str) and current.strip():
            values.append(current.strip())
        pointers = list(projected_sources.get("symptom_context", []))
        for value, pointer in moved:
            if value not in values:
                values.append(value)
            if pointer not in pointers:
                pointers.append(pointer)
        combined = " / ".join(values)
        slots["symptom_context"] = combined
        unfilled.pop("symptom_context", None)
        projected_sources["symptom_context"] = pointers
        evidence["symptom_context"] = {
            "status": "answered", "value": combined, "source": pointers[0]
        }
        repair("symptom_context", "timing_context_reassigned")

    if repairs:
        projected_summary["report_quality"] = {
            "algorithm_version": ALGORITHM_VERSION,
            "notice": "stored_snapshot_projected",
            "repairs": repairs,
        }
    return {"summary": projected_summary, "sources": projected_sources}
