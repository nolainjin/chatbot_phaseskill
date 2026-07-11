"""접수 슬롯 스키마 파서 + 슬롯 모델.

`_intake_schema.md`(지식 디렉토리 예약 파일)를 읽어 슬롯 모델로 바꾸는
도메인 무관 엔진. 스키마는 마크다운 산문 + 기계 파싱용 YAML 블록 1개로
선언한다(결정 D01). 파일 부재·YAML 블록 추출 실패·파싱 오류·필수 키
누락 등 어떤 실패 경로도 예외를 밖으로 새지 않고 None으로 수렴한다 —
스키마 오류 하나가 대화 전체를 죽이는 사고를 막기 위해서다(FP1, CAP09).

원칙: 상담 등 도메인 문구는 이 모듈에 일절 넣지 않는다 — 전부 스키마
데이터가 소유한다.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_SCHEMA_FILENAME = "_intake_schema.md"
_YAML_FENCE_RE = re.compile(r"```yaml\s*?\n(.*?)```", re.DOTALL)


@dataclass
class Slot:
    id: str
    label: str
    required: bool = False
    priority: int = 0
    red_flag: bool = False
    when: str | None = None
    values: list | None = None
    signals: dict | list | None = None
    ask: str | None = None

    def is_active(self, filled: dict) -> bool:
        """when 없으면 공통 슬롯(항상 활성). 있으면 "slot_id=값" 조건을 filled로 판정."""
        if self.when is None:
            return True
        cond_id, _, cond_value = self.when.partition("=")
        return filled.get(cond_id) == cond_value


@dataclass
class Schema:
    version: str
    opening_question: str
    slots: list[Slot]

    def active_slots(self, filled: dict) -> list[Slot]:
        return [slot for slot in self.slots if slot.is_active(filled)]

    def unfilled_by_priority(self, filled: dict, red_flag_first_ids) -> list[Slot]:
        """활성이면서 미충족인 슬롯을 정렬한다.

        red_flag_first_ids(이번 턴에 레드플래그 신호가 감지된 슬롯 id 집합)를
        최상단에 두고, 나머지는 priority 오름차순.
        """
        red_flag_ids = set(red_flag_first_ids or ())
        unfilled = [slot for slot in self.active_slots(filled) if slot.id not in filled]
        return sorted(unfilled, key=lambda slot: (slot.id not in red_flag_ids, slot.priority))


def _parse_slot(raw) -> Slot:
    if not isinstance(raw, dict):
        raise TypeError("slot 항목은 매핑이어야 한다")
    return Slot(
        id=raw["id"],
        label=raw["label"],
        required=bool(raw.get("required", False)),
        priority=int(raw.get("priority", 0)),
        red_flag=bool(raw.get("red_flag", False)),
        when=raw.get("when"),
        values=raw.get("values"),
        signals=raw.get("signals"),
        ask=raw.get("ask"),
    )


def load_schema(knowledge_dir) -> Schema | None:
    """<knowledge_dir>/_intake_schema.md 를 읽어 Schema로 바꾼다.

    부재 · fenced 블록 추출 실패 · YAML 파싱 오류 · 필수 키 누락 중 어느
    경로를 타든 예외 없이 None을 반환한다(형식 오류 = 폴백, 결정 D01).
    """
    schema_path = Path(knowledge_dir) / _SCHEMA_FILENAME
    if not schema_path.is_file():
        return None

    text = schema_path.read_text(encoding="utf-8")
    match = _YAML_FENCE_RE.search(text)
    if match is None:
        return None

    try:
        parsed = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None

    if not isinstance(parsed, dict):
        return None
    data = parsed.get("intake_schema")
    if not isinstance(data, dict):
        return None

    version = data.get("version")
    opening_question = data.get("opening_question")
    slots_raw = data.get("slots")
    if not version or not opening_question or not isinstance(slots_raw, list) or not slots_raw:
        return None

    try:
        slots = [_parse_slot(raw) for raw in slots_raw]
    except (KeyError, TypeError, ValueError):
        return None

    return Schema(version=version, opening_question=opening_question, slots=slots)
