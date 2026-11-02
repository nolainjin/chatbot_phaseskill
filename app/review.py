"""Append-only human confirmation; the last record for a session is current."""

import json
from datetime import date, datetime, timezone

from app import access_log, consent, storage

ACTIONS = ("안내 전화함", "기관 연결함", "해당 없음", "연락 불가")


def validate_payload(payload: dict) -> tuple[str, str, str, str]:
    day, session_id, action = (payload.get(key) for key in ("day", "session_id", "action"))
    note = payload.get("note", "")
    if not isinstance(day, str) or len(day) != 10 or date.fromisoformat(day).isoformat() != day:
        raise ValueError("day 형식이 올바르지 않습니다.")
    if not isinstance(session_id, str) or not storage.valid_session_id(session_id):
        raise ValueError("session_id 형식이 올바르지 않습니다.")
    if action not in ACTIONS:
        raise ValueError("action은 정해진 확인 결과 중 하나여야 합니다.")
    if not isinstance(note, str) or len(note) > 200:
        raise ValueError("note는 200자 이하의 문자열이어야 합니다.")
    return day, session_id, action, note


def review_required(summary: dict) -> bool:
    """Derive from signals as well, so older summaries also remain visible."""
    return summary.get("track") == "위기" or bool(summary.get("red_flags"))


def read_reviews(base_dir=None) -> list[dict]:
    path = consent.data_path("reviews.jsonl", base_dir)
    with storage.data_lock(base_dir):
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line] if path.exists() else []


def latest_actions(base_dir=None) -> dict[str, str]:
    return {record["session_hash"]: record["action"] for record in read_reviews(base_dir)}


def record_review(session_id: str, action: str, token: str, note: str = "", base_dir=None) -> dict:
    # Validate here too for callers outside the API. Never persist raw notes.
    if action not in ACTIONS or not isinstance(note, str) or len(note) > 200:
        raise ValueError("Invalid review")
    record = {"session_hash": access_log.hash_value(session_id), "action": action,
              "at": datetime.now(timezone.utc).isoformat(), "actor": access_log.actor_hash(token)}
    if note:
        record["note"] = storage.redact_pii(note)[:200]
    access_log.append_private_record("reviews.jsonl", record, base_dir)
    return record


def remove_reviews(session_id: str, base_dir=None) -> None:
    with storage.data_lock(base_dir):
        records = read_reviews(base_dir)
        digest = access_log.hash_value(session_id)
        remaining = [record for record in records if record["session_hash"] != digest]
        if remaining != records:
            storage._write_private_text(consent.data_path("reviews.jsonl", base_dir),
                                        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in remaining))
