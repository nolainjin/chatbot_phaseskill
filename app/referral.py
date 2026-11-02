"""Validated local referral data and deterministic matching / handoff text."""

from __future__ import annotations

import math
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import yaml

MAP_FILENAME = "연결-지도.yaml"
DEFAULT_GUIDANCE = (
    "광역 단위 정신건강 상담 전화 1577-0199 또는 자살예방상담전화 109로 "
    "도움을 요청할 수 있어요."
)
KINDS = {"정신건강복지센터", "청년마음건강", "자살예방", "중독관리", "트라우마", "기타공공"}
TRACKS = {"정서", "관계", "위기", "중독"}
AREAS = {"중구", "동구", "서구", "남구", "북구", "수성구", "달서구", "달성군", "군위군", "대구 전역"}
_REQUIRED = {
    "id", "name", "kind", "area", "age_min", "age_max", "tracks", "services",
    "referral", "phone", "homepage", "source_urls", "web_checked_at", "verified_at", "verified_by",
}
_AGE_BANDS = {
    "10대": (10, 19), "20대": (20, 29), "30대": (30, 39),
    "40대": (40, 49), "50대": (50, 59), "60대 이상": (60, math.inf),
}


class MapValidationError(ValueError):
    """A present but invalid map must never silently become an empty map."""


class _UniqueLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise MapValidationError("지도 key는 중복 없는 문자열이어야 합니다.")
        result[key] = loader.construct_object(value_node)
    return result


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def _date_value(value, field: str) -> str | None:
    if value is None:
        return None
    if type(value) is date:
        return value.isoformat()
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            pass
    raise MapValidationError(f"{field}: 날짜는 YYYY-MM-DD 또는 null이어야 합니다.")


def _http_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not any(c.isspace() for c in value)
    except ValueError:
        return False


def load_map(path: str | Path) -> list[dict] | None:
    """Return validated institutions; None explicitly means the map is missing."""
    path = Path(path)
    if path.is_symlink():
        raise MapValidationError("지도 symlink는 허용하지 않습니다.")
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueLoader)
    except FileNotFoundError:
        return None
    except (yaml.YAMLError, UnicodeError) as exc:
        raise MapValidationError("지도 YAML을 읽을 수 없습니다.") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("institutions"), list):
        raise MapValidationError("institutions 목록이 필요합니다.")
    institutions = []
    ids = set()
    for index, institution in enumerate(raw["institutions"]):
        prefix = f"institutions[{index}]"
        if not isinstance(institution, dict) or not _REQUIRED <= institution.keys():
            raise MapValidationError(f"{prefix}: 필수 키가 빠졌습니다.")
        item = dict(institution)
        for key in ("id", "name", "kind", "area", "referral", "phone", "homepage"):
            if not isinstance(item[key], str):
                raise MapValidationError(f"{prefix}.{key}: 문자열이어야 합니다.")
        if not item["id"].strip() or item["id"] in ids:
            raise MapValidationError(f"{prefix}.id: 비어 있거나 중복된 id입니다.")
        ids.add(item["id"])
        if item["kind"] not in KINDS or item["area"] not in AREAS:
            raise MapValidationError(f"{prefix}: 허용되지 않은 kind 또는 area입니다.")
        for key in ("tracks", "services", "source_urls"):
            if not isinstance(item[key], list) or not all(isinstance(v, str) and v.strip() for v in item[key]):
                raise MapValidationError(f"{prefix}.{key}: 문자열 목록이어야 합니다.")
        if not item["tracks"] or not set(item["tracks"]) <= TRACKS:
            raise MapValidationError(f"{prefix}.tracks: 허용되지 않은 트랙입니다.")
        for key in ("age_min", "age_max"):
            value = item[key]
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                raise MapValidationError(f"{prefix}.{key}: 0 이상 숫자 또는 null이어야 합니다.")
        if item["age_min"] is not None and item["age_max"] is not None and item["age_min"] > item["age_max"]:
            raise MapValidationError(f"{prefix}: 연령 하한이 상한보다 큽니다.")
        for key in ("web_checked_at", "verified_at"):
            item[key] = _date_value(item[key], f"{prefix}.{key}")
        if item["verified_by"] is not None and not isinstance(item["verified_by"], str):
            raise MapValidationError(f"{prefix}.verified_by: 문자열 또는 null이어야 합니다.")
        if (item["homepage"] and not _http_url(item["homepage"])) or any(not _http_url(url) for url in item["source_urls"]):
            raise MapValidationError(f"{prefix}: 홈페이지·출처는 http(s) URL이어야 합니다.")
        institutions.append(item)
    return institutions


def _value(summary: dict, slot_id: str):
    # build_summary_json nests slots; flat summaries are also accepted by match.
    return summary.get("slots", {}).get(slot_id, summary.get(slot_id))


def match(summary: dict, institutions: list[dict], min_check: str = "verified") -> dict:
    """Apply the contract's filters and total ordering without any model calls."""
    if min_check not in {"verified", "web"}:
        raise ValueError("REFERRAL_MIN_CHECK는 verified 또는 web이어야 합니다.")
    track = _value(summary, "track")
    if track not in TRACKS:
        track = "정서"
    area = _value(summary, "area")
    age = _AGE_BANDS.get(_value(summary, "age_band"))
    candidates = []
    for item in institutions:
        level = "verified" if item["verified_at"] else "web" if item["web_checked_at"] else None
        if level is None or (min_check == "verified" and level != "verified"):
            continue
        if track not in item["tracks"]:
            continue
        if item["area"] != "대구 전역" and (area not in AREAS or item["area"] != area):
            continue
        limited = item["age_min"] is not None or item["age_max"] is not None
        if age is None:
            if limited:
                continue
        elif (item["age_min"] is not None and age[1] < item["age_min"]) or (
            item["age_max"] is not None and age[0] > item["age_max"]
        ):
            continue
        candidates.append({
            "id": item["id"], "name": item["name"], "referral": item["referral"],
            "phone": item["phone"], "homepage": item["homepage"], "check_level": level,
            "_order": (item["area"] == "대구 전역", not limited, level != "verified", item["id"]),
        })
    candidates.sort(key=lambda item: item["_order"])
    selected = [{k: v for k, v in item.items() if k != "_order"} for item in candidates[:3]]
    return {"institutions": selected, "fallback_used": not selected}


def build_handoff_note(summary: dict, schema) -> list[str]:
    """Five fixed lines containing only the relevant, already redacted slot text."""
    active_ids = {slot.id for slot in schema.active_slots(summary.get("slots", summary))}

    def value(*slot_ids):
        for slot_id in slot_ids:
            raw = _value(summary, slot_id) if slot_id in active_ids else None
            if isinstance(raw, str) and raw.strip() and raw not in {"미확인", "말하지 않음"}:
                return raw
        return "말하지 않음"

    return [
        "지금 힘든 일: " + value("chief_complaint"),
        "시작 시기와 일상 영향: " + value("symptom_context", "relationship_duration"),
        "해본 대처: " + value("coping"),
        "바라는 도움: " + value("expectation"),
        "연결 선호(연결 방식): " + value("contact_pref"),
    ]
