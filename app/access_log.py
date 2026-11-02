"""Private, append-only access evidence without raw credentials or session ids."""

import hashlib
import json
import os
from datetime import datetime, timezone

from app import consent, storage


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def actor_hash(token: str) -> str:
    return hash_value(token)[:8]


def append_private_record(filename: str, record: dict, base_dir=None) -> None:
    """Append under the shared record lock; propagate chmod/write/fsync errors."""
    with storage.data_lock(base_dir):
        path = consent.data_path(filename, base_dir)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8", newline="\n") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def record_access(kind: str, token: str, ip: str, *, filters=None, session_id=None, management_id=None, base_dir=None) -> dict:
    if kind not in {"stats", "raw_view", "review", "link_issue"}:
        raise ValueError("Invalid access kind")
    record = {
        "at": datetime.now(timezone.utc).isoformat(),
        "actor": actor_hash(token),
        "kind": kind,
        "ip_hash": hash_value(ip),
    }
    if kind == "stats":
        record["filters"] = filters or {}
    elif kind == "link_issue":
        record["management_id_hash"] = hash_value(management_id)
    else:
        record["session_hash"] = hash_value(session_id)
    append_private_record("access_log.jsonl", record, base_dir)
    return record
