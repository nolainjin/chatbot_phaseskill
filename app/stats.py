"""SQLite 상담 로그를 읽어 내담자 통계 대시보드 JSON으로 변환한다."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path("data/chatlog.db")


_SLOT_LABELS = {
    "track": "상담 트랙",
    "chief_complaint": "호소 문제",
    "symptom_context": "증상 시기·일상 영향",
    "relationship_context": "관계 대상·기간",
    "crisis_plan_means": "자해 계획·수단",
    "crisis_attempt_history": "과거 시도 이력",
    "coping": "대처 시도",
    "support": "지지체계",
    "expectation": "상담 기대",
}


def _empty_stats(db_path: Path, filters: dict[str, str | None] | None = None) -> dict[str, Any]:
    return {
        "database": str(db_path),
        "exists": db_path.exists(),
        "filters": filters or {},
        "totals": {
            "participants": 0,
            "conversations": 0,
            "turns": 0,
            "user_turns": 0,
            "assistant_turns": 0,
            "summaries": 0,
            "red_flag_sessions": 0,
            "avg_user_turns_per_conversation": 0,
        },
        "track_counts": [],
        "slot_completion": [],
        "daily_counts": [],
        "recent_sessions": [],
    }


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _count(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def _conversation_filter(
    participant_prefix: str | None,
    session_prefix: str | None,
    alias: str = "c",
) -> tuple[str, tuple[str, ...]]:
    clauses: list[str] = []
    params: list[str] = []
    if participant_prefix:
        clauses.append(f"{alias}.participant_id LIKE ?")
        params.append(f"{participant_prefix}%")
    if session_prefix:
        clauses.append(f"{alias}.session_id LIKE ?")
        params.append(f"{session_prefix}%")
    return (" WHERE " + " AND ".join(clauses), tuple(params)) if clauses else ("", ())


def _turn_join_filter(
    participant_prefix: str | None,
    session_prefix: str | None,
    role: str | None = None,
) -> tuple[str, tuple[str, ...]]:
    where, params = _conversation_filter(participant_prefix, session_prefix, "c")
    clauses: list[str] = []
    merged = list(params)
    if where:
        clauses.append(where[7:])
    if role:
        clauses.append("t.role=?")
        merged.append(role)
    return (" WHERE " + " AND ".join(clauses), tuple(merged)) if clauses else ("", ())


def _load_summaries(
    conn: sqlite3.Connection,
    participant_prefix: str | None,
    session_prefix: str | None,
) -> list[dict[str, Any]]:
    where, params = _turn_join_filter(participant_prefix, session_prefix, "intake_summary")
    rows = conn.execute(
        f"""
        SELECT t.date, t.session_id, t.text
        FROM turns t
        JOIN conversations c
          ON c.date=t.date AND c.session_id=t.session_id
        {where}
        ORDER BY t.date DESC, t.session_id ASC, t.seq ASC
        """,
        params,
    ).fetchall()
    summaries: list[dict[str, Any]] = []
    for day, session_id, text in rows:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            parsed["date"] = day
            parsed["session_id"] = session_id
            summaries.append(parsed)
    return summaries


def read_stats(
    db_path: str | Path = DEFAULT_DB_PATH,
    participant_prefix: str | None = None,
    session_prefix: str | None = None,
) -> dict[str, Any]:
    db_path = Path(db_path)
    filters = {"participant_prefix": participant_prefix, "session_prefix": session_prefix}
    if not db_path.exists():
        return _empty_stats(db_path, filters)

    conn = sqlite3.connect(db_path)
    try:
        if not all(_table_exists(conn, table) for table in ("participants", "conversations", "turns")):
            return _empty_stats(db_path, filters)

        conv_where, conv_params = _conversation_filter(participant_prefix, session_prefix, "c")
        turn_where, turn_params = _turn_join_filter(participant_prefix, session_prefix)
        user_where, user_params = _turn_join_filter(participant_prefix, session_prefix, "user")
        assistant_where, assistant_params = _turn_join_filter(participant_prefix, session_prefix, "assistant")
        summary_where, summary_params = _turn_join_filter(participant_prefix, session_prefix, "intake_summary")

        participant_total = _count(
            conn,
            f"SELECT COUNT(DISTINCT c.participant_id) FROM conversations c{conv_where}",
            conv_params,
        )
        conversation_total = _count(
            conn,
            f"SELECT COUNT(*) FROM conversations c{conv_where}",
            conv_params,
        )
        turn_total = _count(
            conn,
            """
            SELECT COUNT(*)
            FROM turns t
            JOIN conversations c
              ON c.date=t.date AND c.session_id=t.session_id
            """
            + turn_where,
            turn_params,
        )
        user_turns = _count(
            conn,
            """
            SELECT COUNT(*)
            FROM turns t
            JOIN conversations c
              ON c.date=t.date AND c.session_id=t.session_id
            """
            + user_where,
            user_params,
        )
        assistant_turns = _count(
            conn,
            """
            SELECT COUNT(*)
            FROM turns t
            JOIN conversations c
              ON c.date=t.date AND c.session_id=t.session_id
            """
            + assistant_where,
            assistant_params,
        )
        summary_total = _count(
            conn,
            """
            SELECT COUNT(*)
            FROM turns t
            JOIN conversations c
              ON c.date=t.date AND c.session_id=t.session_id
            """
            + summary_where,
            summary_params,
        )
        avg_user_turns = round(user_turns / conversation_total, 2) if conversation_total else 0

        summaries = _load_summaries(conn, participant_prefix, session_prefix)
        track_counter: Counter[str] = Counter()
        completed_slots: Counter[str] = Counter()
        missing_slots: Counter[str] = Counter()
        red_flag_sessions = 0
        for summary in summaries:
            track_counter[str(summary.get("track") or "미확인")] += 1
            slots = summary.get("slots") if isinstance(summary.get("slots"), dict) else {}
            for slot_id, value in slots.items():
                if value not in (None, "", "미확인"):
                    completed_slots[str(slot_id)] += 1
            unfilled = summary.get("unfilled") if isinstance(summary.get("unfilled"), dict) else {}
            for slot_id in unfilled:
                missing_slots[str(slot_id)] += 1
            red_flags = summary.get("red_flags") if isinstance(summary.get("red_flags"), list) else []
            if red_flags:
                red_flag_sessions += 1

        all_slot_ids = sorted(set(_SLOT_LABELS) | set(completed_slots) | set(missing_slots))
        slot_completion = []
        denominator = summary_total or conversation_total or 1
        for slot_id in all_slot_ids:
            completed = completed_slots[slot_id]
            missing = missing_slots[slot_id]
            slot_completion.append(
                {
                    "slot_id": slot_id,
                    "label": _SLOT_LABELS.get(slot_id, slot_id),
                    "completed": completed,
                    "missing": missing,
                    "rate": round(completed / denominator, 3),
                }
            )
        slot_completion.sort(key=lambda item: (-item["completed"], item["slot_id"]))

        daily_counts = [
            {"date": row[0], "conversations": row[1], "participants": row[2]}
            for row in conn.execute(
                f"""
                SELECT c.date, COUNT(*), COUNT(DISTINCT c.participant_id)
                FROM conversations c
                {conv_where}
                GROUP BY c.date
                ORDER BY c.date DESC
                LIMIT 14
                """,
                conv_params,
            ).fetchall()
        ]

        user_turn_count_by_session = defaultdict(int)
        for day, session_id, count in conn.execute(
            f"""
            SELECT t.date, t.session_id, COUNT(*)
            FROM turns t
            JOIN conversations c
              ON c.date=t.date AND c.session_id=t.session_id
            {user_where}
            GROUP BY t.date, t.session_id
            """,
            user_params,
        ).fetchall():
            user_turn_count_by_session[(day, session_id)] = int(count)

        summary_by_session = {(s["date"], s["session_id"]): s for s in summaries}
        recent_sessions = []
        for day, session_id, participant_id in conn.execute(
            f"""
            SELECT c.date, c.session_id, c.participant_id
            FROM conversations c
            {conv_where}
            ORDER BY c.date DESC, c.session_id DESC
            LIMIT 20
            """,
            conv_params,
        ).fetchall():
            summary = summary_by_session.get((day, session_id), {})
            recent_sessions.append(
                {
                    "date": day,
                    "session_id": session_id,
                    "participant_id": participant_id,
                    "track": summary.get("track", "미확인"),
                    "red_flags": summary.get("red_flags", []),
                    "user_turns": user_turn_count_by_session[(day, session_id)],
                }
            )

        return {
            "database": str(db_path),
            "exists": True,
            "filters": filters,
            "totals": {
                "participants": participant_total,
                "conversations": conversation_total,
                "turns": turn_total,
                "user_turns": user_turns,
                "assistant_turns": assistant_turns,
                "summaries": summary_total,
                "red_flag_sessions": red_flag_sessions,
                "avg_user_turns_per_conversation": avg_user_turns,
            },
            "track_counts": [
                {"track": track, "count": count} for track, count in track_counter.most_common()
            ],
            "slot_completion": slot_completion,
            "daily_counts": daily_counts,
            "recent_sessions": recent_sessions,
        }
    finally:
        conn.close()
