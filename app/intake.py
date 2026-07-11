"""접수 슬롯 스키마 파서 + 슬롯 모델.

`_intake_schema.md`(지식 디렉토리 예약 파일)를 읽어 슬롯 모델로 바꾸는
도메인 무관 엔진. 스키마는 마크다운 산문 + 기계 파싱용 YAML 블록 1개로
선언한다(결정 D01). 파일 부재·YAML 블록 추출 실패·파싱 오류·필수 키
누락 등 어떤 실패 경로도 예외를 밖으로 새지 않고 None으로 수렴한다 —
스키마 오류 하나가 대화 전체를 죽이는 사고를 막기 위해서다(FP1, CAP09).

원칙: 상담 등 도메인 문구는 이 모듈에 일절 넣지 않는다 — 전부 스키마
데이터가 소유한다.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_SCHEMA_FILENAME = "_intake_schema.md"
_YAML_FENCE_RE = re.compile(r"```yaml\s*?\n(.*?)```", re.DOTALL)
_SLOTS_FENCE_RE = re.compile(r"```slots\s*?\n(.*?)```", re.DOTALL)
_MAX_SLOT_VALUE_LEN = 200


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


def _match_signal(message: str, signals) -> str | None:
    """message에서 signals 부분문자열 매칭 결과를 반환한다. 없으면 None.

    signals가 dict(값 -> 부분문자열 목록)이면 매칭된 값(키)을 반환하고,
    list(부분문자열 목록)이면 매칭된 부분문자열 자체를 반환한다.
    """
    if isinstance(signals, dict):
        for value, substrings in signals.items():
            if any(sub in message for sub in substrings):
                return value
        return None
    for sub in signals:
        if sub in message:
            return sub
    return None


def extract_fake(message: str, schema: Schema, filled: dict) -> dict[str, str]:
    """fake 모드 전용 결정론적 슬롯 추출.

    활성 상태이면서 아직 채워지지 않은 슬롯만 대상으로 signals 부분문자열
    매칭을 시도한다. 한 발화에서 여러 슬롯이 동시에 매칭될 수 있다. 이미
    채워진 슬롯은 절대 덮어쓰지 않는다(트랙 뒤집힘 방지) — 이 함수는 filled를
    변경하지 않고 이번 발화로 새로 채워진 슬롯만 담은 dict를 반환한다.
    """
    new_fills: dict[str, str] = {}
    for slot in schema.active_slots(filled):
        if slot.id in filled or slot.signals is None:
            continue
        value = _match_signal(message, slot.signals)
        if value is not None:
            new_fills[slot.id] = value
    return new_fills


def detect_red_flags(message: str, schema: Schema, filled: dict) -> set[str]:
    """이번 발화가 red_flag 슬롯의 signals에 걸리면 그 슬롯 id 집합을 반환한다.

    채움 여부와 무관하게 감지한다 — 결과는 unfilled_by_priority의 우선 정렬
    신호로만 쓰인다(이미 채워진 슬롯은 unfilled_by_priority가 알아서 제외).
    """
    hits = set()
    for slot in schema.active_slots(filled):
        if not slot.red_flag or slot.signals is None:
            continue
        if _match_signal(message, slot.signals) is not None:
            hits.add(slot.id)
    return hits


def extract_real(reply: str, schema: Schema, filled: dict) -> tuple[str, dict[str, str]]:
    """실모드 LLM 응답에서 ```slots fenced JSON 블록을 분리해 신뢰 경계로 거른다.

    LLM 출력은 신뢰 경계 밖이다 — fenced 블록 분리 실패나 JSON 파싱 실패는
    그 턴의 추출을 스킵한다(원문 그대로, 빈 dict 반환. 다음 턴에 만회하므로
    파싱 실패의 영향은 그 턴 한정 — FP19 방지). 파싱에 성공해도 각 항목을
    4중 필터로 거른다: 스키마 활성 슬롯 id 화이트리스트에 없으면 폐기,
    문자열이 아니면 폐기, 200자를 넘으면 폐기, 이미 채워진 슬롯이면 폐기
    (덮어쓰기 금지). 통과분만 반환하고, reply에서는 슬롯 JSON 블록을 제거해
    사용자·history·storage에는 절대 노출하지 않는다.
    """
    match = _SLOTS_FENCE_RE.search(reply)
    if match is None:
        return reply, {}

    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return reply, {}

    if not isinstance(parsed, dict):
        return reply, {}

    active_ids = {slot.id for slot in schema.active_slots(filled)}
    accepted: dict[str, str] = {}
    for slot_id, value in parsed.items():
        if slot_id not in active_ids:
            continue
        if not isinstance(value, str):
            continue
        if len(value) > _MAX_SLOT_VALUE_LEN:
            continue
        if slot_id in filled:
            continue
        accepted[slot_id] = value

    clean_reply = (reply[: match.start()] + reply[match.end() :]).rstrip()
    return clean_reply, accepted


def build_summary_json(schema: Schema, filled: dict) -> dict:
    """스키마 활성 시 세션 슬롯 상태만으로 구조화 접수 요약을 만든다(LLM 무호출).

    채워진 슬롯은 이미 세션 상태에 있으므로 LLM을 부를 이유가 없다 —
    결정론 생성이라 fake 모드에서도 동일하게 돈다. 활성인데 못 채운 슬롯은
    "미확인"으로 남긴다(CAP07). red_flags는 별도 감지 이력 없이 채워진
    red_flag 슬롯에서 파생한다 — 신호는 감지됐지만 끝내 못 채운 레드플래그
    슬롯은 unfilled의 미확인으로 표기되어 정보 손실이 없다.
    """
    active = schema.active_slots(filled)
    unfilled = [slot for slot in active if slot.id not in filled]
    return {
        "track": filled.get("track", "미확인"),
        "slots": dict(filled),
        "unfilled": {slot.id: "미확인" for slot in unfilled},
        "red_flags": [slot.id for slot in active if slot.red_flag and slot.id in filled],
    }


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
