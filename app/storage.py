"""대화 턴을 날짜별 JSON 파일에 저장한다.

data/conversations/YYYY-MM-DD/{session_id}.json 에 세션 메타데이터와 턴을
저장한다. 세션당 최대 20턴(사용자+봇 각 10턴)이라 파일 전체를 매번
재작성해도 충분히 가볍다 — append 전용 스트리밍 writer는 필요 없다.
"""

import json
import os
import re
from datetime import date
from pathlib import Path

DEFAULT_CONVERSATIONS_DIR = Path("data/conversations")

# 공개 API가 주는 id가 파일명/SQLite 키가 되므로 경로 구분자를 차단한다.
_SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_EMAIL_RE = re.compile(r"\b[^@\s]+@[^@\s]+\.[^@\s]+\b")
_KOREAN_RRN_RE = re.compile(r"(?<!\d)\d{6}-[1-8]\d{6}(?!\d)")
_KOREAN_PHONE_RE = re.compile(
    r"(?<!\d)(?:01[016789]-?\d{3,4}-?\d{4}|0[2-6][1-5]?-?\d{3,4}-?\d{4})(?!\d)"
)
_KOREAN_NAME_RE = re.compile(r"(제\s*이름은|이름은)\s*[가-힣]{2,4}")
_KOREAN_ADDRESS_RE = re.compile(
    r"(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)"
    r"(?:특별시|광역시|시|도)?\s+[가-힣0-9 .-]{0,40}(?:구|군|시)\s+"
    r"[가-힣0-9 .-]{0,50}(?:로|길)\s*\d+(?:[-\s]\d+)?(?:\s*\d+호)?"
)
_PII_REPLACEMENTS = (
    (_EMAIL_RE, "[redacted-email]"),
    (_KOREAN_RRN_RE, "[redacted-rrn]"),
    (_KOREAN_PHONE_RE, "[redacted-phone]"),
    (_KOREAN_NAME_RE, r"\1 [redacted-name]"),
    (_KOREAN_ADDRESS_RE, "[redacted-address]"),
)




def valid_session_id(session_id: str) -> bool:
    """session_id가 파일명으로 안전한 화이트리스트(길이·문자셋)에 맞는지 검사한다."""
    return bool(_SAFE_ID_RE.fullmatch(session_id))


def valid_participant_id(participant_id: str) -> bool:
    """개인번호(participant_id)는 식별정보가 아니라 무작위 로컬 ID만 허용한다."""
    if not _SAFE_ID_RE.fullmatch(participant_id):
        return False
    if participant_id.startswith("p_"):
        return True
    if _KOREAN_RRN_RE.fullmatch(participant_id) or _KOREAN_PHONE_RE.fullmatch(participant_id):
        return False
    if _EMAIL_RE.fullmatch(participant_id):
        return False
    return True


def redact_pii(text: str) -> str:
    """Remove obvious direct identifiers before durable local conversation storage."""
    redacted = text
    for pattern, replacement in _PII_REPLACEMENTS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def conversation_exists(
    session_id: str,
    base_dir: str | Path = DEFAULT_CONVERSATIONS_DIR,
) -> bool:
    if not valid_session_id(session_id):
        return False
    return any(
        path.is_file()
        for path in Path(base_dir).glob(f"*/{session_id}.json")
    )


def normalize_conversation_payload(
    raw,
    session_id: str,
    participant_id: str | None = None,
) -> dict:
    """legacy list 로그와 신규 metadata 로그를 공통 dict 형태로 정규화한다."""
    effective_participant_id = participant_id or session_id
    if isinstance(raw, list):
        return {
            "schema_version": 2,
            "session_id": session_id,
            "participant_id": effective_participant_id,
            "turns": raw,
        }
    if isinstance(raw, dict):
        turns = raw.get("turns")
        if not isinstance(turns, list):
            turns = []
        raw_participant = str(raw.get("participant_id") or effective_participant_id)
        if not valid_participant_id(raw_participant):
            raw_participant = effective_participant_id
        return {
            "schema_version": 2,
            "session_id": session_id,
            "participant_id": raw_participant,
            "turns": turns,
        }
    return {
        "schema_version": 2,
        "session_id": session_id,
        "participant_id": effective_participant_id,
        "turns": [],
    }


def _redact_obj(value):
    if isinstance(value, str):
        return redact_pii(value)
    if isinstance(value, dict):
        return {k: _redact_obj(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_obj(v) for v in value]
    return value


def _write_private_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def append_turn(
    session_id: str,
    role: str,
    text: str,
    participant_id: str | None = None,
    base_dir: str | Path = DEFAULT_CONVERSATIONS_DIR,
) -> None:
    """오늘 날짜 디렉토리의 세션 JSON에 (role, text) 턴을 추가한다."""
    if not valid_session_id(session_id):
        raise ValueError(f"잘못된 session_id: {session_id!r}")
    if participant_id is not None and not valid_participant_id(participant_id):
        raise ValueError(f"잘못된 participant_id: {participant_id!r}")

    day_dir = Path(base_dir) / date.today().isoformat()
    _ensure_private_dir(day_dir)
    path = day_dir / f"{session_id}.json"

    raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    payload = normalize_conversation_payload(raw, session_id, participant_id)
    turns = payload["turns"]
    turns.append({"seq": len(turns), "role": role, "text": redact_pii(text)})


    _write_private_json(path, payload)
def update_metadata(
    session_id: str,
    updates: dict,
    participant_id: str | None = None,
    base_dir: str | Path = DEFAULT_CONVERSATIONS_DIR,
) -> None:
    """오늘 날짜 세션 JSON의 top-level metadata를 갱신한다."""
    if not valid_session_id(session_id):
        raise ValueError(f"잘못된 session_id: {session_id!r}")
    if participant_id is not None and not valid_participant_id(participant_id):
        raise ValueError(f"잘못된 participant_id: {participant_id!r}")

    day_dir = Path(base_dir) / date.today().isoformat()
    _ensure_private_dir(day_dir)
    path = day_dir / f"{session_id}.json"

    raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    payload = normalize_conversation_payload(raw, session_id, participant_id)
    payload.update(_redact_obj(updates))
    _write_private_json(path, payload)
