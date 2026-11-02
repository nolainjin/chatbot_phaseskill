"""Resolve durable data paths from DATA_DIR at call time.

An explicit base_dir keeps the existing convention: it names the conversations
directory, and companion records live beside that directory.
"""

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "data"))


def conversations_dir(base_dir: str | Path | None = None) -> Path:
    return Path(base_dir) if base_dir is not None else data_dir() / "conversations"


def data_path(filename: str, base_dir: str | Path | None = None) -> Path:
    root = data_dir() if base_dir is None else Path(base_dir).parent
    return root / filename


def db_path() -> Path:
    return data_path("chatlog.db")


def ratelimit_path() -> Path:
    return data_path("ratelimit.json")


def records_lock_path(base_dir: str | Path | None = None) -> Path:
    return data_path(".records.lock", base_dir)


def delete_codes_path(base_dir: str | Path | None = None) -> Path:
    return data_path("delete_codes.jsonl", base_dir)


def tombstones_path(base_dir: str | Path | None = None) -> Path:
    return data_path("tombstones.jsonl", base_dir)


def access_log_path(base_dir: str | Path | None = None) -> Path:
    return data_path("access_log.jsonl", base_dir)


def reviews_path(base_dir: str | Path | None = None) -> Path:
    return data_path("reviews.jsonl", base_dir)
