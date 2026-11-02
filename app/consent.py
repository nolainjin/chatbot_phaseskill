"""Pack-owned privacy notice, explicit consent, and one-time deletion credentials."""

import hashlib
import json
import re
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app import storage

_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


class PrivacyError(ValueError):
    """A present but invalid privacy contract must stop startup."""


class _UniqueLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader, node):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in mapping:
            raise PrivacyError("_privacy.md: 중복되거나 잘못된 frontmatter 키")
        mapping[key] = loader.construct_object(value_node)
    return mapping


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


@dataclass(frozen=True)
class Privacy:
    consent_version: str
    retention_raw_days: int
    retention_summary_days: int
    deletion_days: int
    body: str

    def as_dict(self):
        return asdict(self)


def load_privacy(knowledge_dir, settings=None) -> Privacy | None:
    path = Path(knowledge_dir) / "_privacy.md"
    if not path.exists() and not path.is_symlink():
        return None
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 65536:
        raise PrivacyError("_privacy.md: 올바른 일반 문서가 필요합니다.")
    text = path.read_text(encoding="utf-8")
    match = re.fullmatch(r"---\n(.*?)\n---\n(.+)", text, re.DOTALL)
    if not match:
        raise PrivacyError("_privacy.md: YAML frontmatter와 고지 본문이 필요합니다.")
    try:
        data = yaml.load(match[1], Loader=_UniqueLoader)
    except yaml.YAMLError as exc:
        raise PrivacyError("_privacy.md: YAML 형식 오류") from exc
    if not isinstance(data, dict):
        raise PrivacyError("_privacy.md: frontmatter는 매핑이어야 합니다.")
    version = data.get("consent_version")
    if not isinstance(version, str) or not version.strip() or len(version) > 128:
        raise PrivacyError("_privacy.md: consent_version 문자열이 필요합니다.")
    for key in ("retention_raw_days", "retention_summary_days", "deletion_days"):
        if type(data.get(key)) is not int or data[key] <= 0:
            raise PrivacyError(f"_privacy.md: {key}는 양의 정수여야 합니다.")
    if data["retention_raw_days"] > data["retention_summary_days"]:
        raise PrivacyError("_privacy.md: 요약 보관 기간은 원문 보관 기간보다 짧을 수 없습니다.")
    body = match[2].strip()
    if not body:
        raise PrivacyError("_privacy.md: 고지 본문이 비어 있습니다.")
    privacy = Privacy(version, data["retention_raw_days"], data["retention_summary_days"], data["deletion_days"], body)
    if settings is not None and (
        privacy.retention_raw_days != settings.retention_raw_days
        or privacy.retention_summary_days != settings.retention_summary_days
    ):
        raise PrivacyError("_privacy.md와 RETENTION_RAW_DAYS/RETENTION_SUMMARY_DAYS가 일치해야 합니다.")
    return privacy


def data_path(filename, base_dir=None):
    return Path(base_dir if base_dir is not None else storage.DEFAULT_CONVERSATIONS_DIR).parent / filename


def _read_codes(base_dir=None):
    path = data_path("delete_codes.jsonl", base_dir)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line] if path.exists() else []


def _write_codes(records, base_dir=None):
    storage._write_private_text(data_path("delete_codes.jsonl", base_dir), "".join(json.dumps(r) + "\n" for r in records))


def _normalize_code(code):
    if not isinstance(code, str) or len(code) > 64:
        return None
    compact = re.sub(r"[-\s]", "", code.upper())
    if len(compact) != 12 or any(c not in _CODE_ALPHABET for c in compact):
        return None
    return compact


def _code_hash(code, salt):
    return hashlib.sha256((salt + ":" + code).encode("ascii")).hexdigest()


def issue_delete_code(session_id, base_dir=None):
    """Return the only plaintext copy; persist a random salt and digest privately."""
    compact = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(12))
    salt = secrets.token_hex(32)
    with storage.data_lock(base_dir):
        records = _read_codes(base_dir)
        records.append({"session_id": session_id, "salt": salt, "code_hash": _code_hash(compact, salt)})
        _write_codes(records, base_dir)
    return "-".join(compact[i:i + 4] for i in range(0, 12, 4))


def session_for_delete_code(code, base_dir=None):
    compact = _normalize_code(code)
    if compact is None:
        return None
    for record in _read_codes(base_dir):
        if secrets.compare_digest(record["code_hash"], _code_hash(compact, record["salt"])):
            return record["session_id"]
    return None


def remove_delete_code(session_id, base_dir=None):
    records = _read_codes(base_dir)
    remaining = [r for r in records if r["session_id"] != session_id]
    if remaining != records:
        _write_codes(remaining, base_dir)


def record_consent(session, privacy):
    session.consented_at = datetime.now(timezone.utc).isoformat()
    session.consent_version = privacy.consent_version
    session.consent_pack = str(Path(session.consent_pack).resolve())
    persist_consent(session)


def persist_consent(session):
    """Each dated transcript retains the original consent, including after midnight."""
    storage.update_metadata(session.session_id, {
        "created_at": session.created_at,
        "consented_at": session.consented_at,
        "consent_version": session.consent_version,
        "consent_pack": session.consent_pack,
    }, participant_id=session.participant_id)
