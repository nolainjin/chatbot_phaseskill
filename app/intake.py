"""접수 슬롯 스키마 파서 + 슬롯 모델.

`_intake_schema.md`(지식 디렉토리 예약 파일)를 읽어 슬롯 모델로 바꾸는
도메인 무관 엔진. 스키마는 마크다운 산문 + 기계 파싱용 YAML 블록 1개로
선언한다(결정 D01). 파일 부재·YAML 블록 추출 실패·파싱 오류·필수 키
누락 등 어떤 실패 경로도 예외를 밖으로 새지 않고 None으로 수렴한다 —
스키마 오류 하나가 대화 전체를 죽이는 사고를 막기 위해서다(FP1, CAP09).

원칙: 상담 등 도메인 문구는 스키마 데이터가 소유한다. 자살·자해 안전
판정은 crisis_signals의 결정론 규칙을 함께 사용한다.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app import crisis_signals, knowledge, safety

_SCHEMA_FILENAME = "_intake_schema.md"
_YAML_FENCE_RE = re.compile(r"```yaml\s*?\n(.*?)```", re.DOTALL)
_SLOTS_FENCE_RE = re.compile(r"```slots\s*?\n(.*?)```", re.DOTALL)
_MAX_SLOT_VALUE_LEN = 200
_MAX_SCHEMA_FILE_BYTES = 64 * 1024
_TRACK_RANK = {"정서": 0, "관계": 1, "중독": 2, "위기": 3}
_EVIDENCE_MUTABLE_FREE_TEXT_IDS = {
    "chief_complaint", "symptom_context", "relationship_duration",
    "cause", "coping", "expectation",
}


class SchemaExtractError(ValueError):
    """Unknown extraction policies are configuration errors, never a fallback."""


class HandoffConfigError(ValueError):
    """Exit-enabled packs must explicitly declare their destination and closing UI."""


def validate_handoff_config(data: dict, uses_exit: bool = False) -> None:
    ui = data.get("ui") or {}
    mode = ui.get("handoff_mode") if isinstance(ui, dict) else None
    slots = data.get("slots")
    slot_ids = {slot["id"] for slot in slots
                if isinstance(slot, dict) and isinstance(slot.get("id"), str)} if isinstance(slots, list) else set()
    uses_exit = uses_exit or "closing" in data or {"area", "age_band", "contact_pref"} <= slot_ids
    if mode is None and not uses_exit and (not isinstance(ui, dict) or "handoff_mode" not in ui):
        return  # Packs without an exit retain their existing behavior.
    if not isinstance(mode, str) or mode not in {"center", "referral"}:
        raise HandoffConfigError("ui.handoff_mode는 center 또는 referral이어야 합니다.")
    if mode == "center":
        closing = data.get("closing")
        if not isinstance(closing, dict):
            raise HandoffConfigError("center 모드에는 closing 설정이 필요합니다.")
        options = closing.get("options")
        if (not isinstance(options, list) or not options
                or not all(isinstance(item, str) and item.strip() for item in options)
                or len(set(options)) != len(options)
                or not isinstance(closing.get("question"), str) or not closing["question"].strip()
                or not isinstance(closing.get("send_label"), str) or not closing["send_label"].strip()
                or closing["send_label"] in options):
            raise HandoffConfigError("closing 질문·선택지·보내기 문구를 확인해 주세요.")


@dataclass
class Slot:
    id: str
    label: str
    required: bool = False
    priority: int = 0
    red_flag: bool = False
    when: str | None = None
    unless: str | None = None
    values: list | None = None
    allow_override_values: list | None = None
    override_signals: dict | None = None
    reject_signals: list | None = None
    reject_unless_signals: list | None = None
    signals: dict | list | None = None
    ask: str | None = None
    capture: str | None = None
    extract: str | None = None
    when_any: list[str] | None = None

    def accepts_answer(self, last_question_slot_id=None):
        return self.extract != "when_asked" or last_question_slot_id == self.id

    def is_active(self, filled: dict) -> bool:
        """``when`` 조건은 일치할 때, ``unless`` 조건은 불일치할 때 활성화한다."""
        if self.when_any is not None and not any(
            filled.get(condition.partition("=")[0]) == condition.partition("=")[2]
            for condition in self.when_any
        ):
            return False
        if self.when is not None:
            cond_id, _, cond_value = self.when.partition("=")
            if filled.get(cond_id) != cond_value:
                return False
        if self.unless is not None:
            cond_id, _, cond_value = self.unless.partition("=")
            if filled.get(cond_id) == cond_value:
                return False
        return True


@dataclass
class Schema:
    version: str
    opening_question: str
    slots: list[Slot]
    # 화면 고정 문구(제목·인사말·칩 등)도 스키마 데이터가 소유한다 — 모듈
    # 상단 원칙의 UI 연장. 비어 있으면 static/의 기본(상담) 문구를 쓴다.
    ui: dict = field(default_factory=dict)
    closing: dict | None = None

    @property
    def handoff_mode(self) -> str | None:
        return self.ui.get("handoff_mode")

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
    """message에서 signals 매칭 결과를 반환한다.

    양쪽을 공통 정규화한 뒤 공백 없는 형태도 비교한다. 한국어 사용자는
    "죽고싶어요"처럼 띄어쓰기를 생략하고, 공격자는 zero-width/NBSP를
    삽입할 수 있으므로 raw substring만으로는 안전 라우팅을 맡길 수 없다.
    """
    normalized_message = safety.normalize_for_signal(message)

    def matched(signal: str) -> bool:
        normalized_signal = safety.normalize_for_signal(str(signal))
        return bool(normalized_signal and normalized_signal in normalized_message)

    if isinstance(signals, dict):
        for value, substrings in signals.items():
            if any(matched(sub) for sub in substrings):
                return value
        return None
    for sub in signals:
        if matched(sub):
            return sub
    return None


def _fake_slot_value(message: str, matched_value: str, slot: Slot) -> str:
    """fake 모드 슬롯 값 생성. capture=full_message면 발화 전체를 보존한다."""
    if slot.capture == "full_message":
        return " ".join(message.split())[:_MAX_SLOT_VALUE_LEN]
    return matched_value


def _has_semantic_slot_evidence(
    message: str | None, slot: Slot, last_question_slot_id: str | None = None
) -> bool:
    """Require meaning, not a shared noun, for narrow support/expectation slots."""
    if message is None or slot.id not in {"support", "expectation"}:
        return True
    if last_question_slot_id == slot.id:
        return True
    normalized = safety.normalize_for_signal(message)
    if slot.id == "support":
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
    return any(marker in normalized for marker in (
        "기대", "원하", "바라", "도움", "편해지", "나아지", "바뀌", "좋겠",
        "했으면", "줄었으면", "알고싶", "배우고싶", "정리하고싶", "해결하고싶",
        "상담받", "상담을받",
    ))


def _is_rejected_by_signal_guard(
    message: str | None, slot: Slot, last_question_slot_id: str | None = None
) -> bool:
    """slot-level negative signal guard.

    Some slots are semantically narrower than their keyword hints. Example:
    a current crisis-plan slot may use "약" as a signal, but "예전에 약을
    먹으려고 한 적" is past attempt history, not current means. The schema
    owns these domain distinctions through reject_signals/reject_unless_signals.
    """
    if message is None:
        return False
    if not _has_semantic_slot_evidence(message, slot, last_question_slot_id):
        return True
    if slot.id == "coping":
        normalized = safety.normalize_for_signal(message)
        counselor_preference = any(marker in normalized for marker in (
            "상담사가", "상담사에게", "선생님이", "먼저대화를걸어",
            "들어주면", "해주면", "진행해주면",
        ))
        future_only = any(marker in normalized for marker in (
            "해보고싶", "하고싶", "가보고싶", "해볼게", "해볼래",
            "배우고싶", "알고싶", "방법을배우", "방법을알고",
        ))
        actual_attempt = any(marker in normalized for marker in (
            "해봤", "써봤", "했어", "했습니다", "쉬었", "쉬고있", "걸었",
            "산책했", "운동했", "상담받", "대화했", "얘기했", "이야기했",
            "일기를썼", "기록했", "참았", "견뎌", "가보려했",
        ))
        if counselor_preference or (future_only and not actual_attempt):
            return True
        if "걸어" in message and not any(
            marker in message for marker in ("걸어봤", "걸었", "걸어서", "산책")
        ):
            return True
    if not slot.reject_signals:
        return False
    if not any(
        safety.normalize_for_signal(word) in safety.normalize_for_signal(message)
        for word in slot.reject_signals
    ):
        return False
    if slot.reject_unless_signals and any(
        safety.normalize_for_signal(word) in safety.normalize_for_signal(message)
        for word in slot.reject_unless_signals
    ):
        return False
    return True


def _can_override(
    slot: Slot, current_value: str, new_value: str, message: str | None = None
) -> bool:
    """스키마가 허용한 값으로만 기존 슬롯 값을 갱신한다(예: 위기 승격).

    override_signals가 선언된 값은 그 좁은 신호 부분문자열이 실제 메시지에 있어야
    갱신을 허용한다. 관계 승격을 남편/아내 같은 정체성 명사 언급만으로 허용하면,
    이미 확정된 트랙이 스쳐 지나가는 배우자 언급 한 번에 덮어써진다(실측:
    emo-insomnia 페르소나 — "잠"으로 정서 확정 후 "아내한테는 피곤하다고만 말했다"는
    지나가는 언급에 관계로 덮어써짐). 원문 message가 없는 호출에서는
    override_signals가 선언된 값을 안전하게 거부한다.
    """
    normalized = safety.normalize_for_signal(message or "")
    correction_markers = ("정정할게", "정정합니다", "바꿀게", "바꿔주세요", "아니라", "잘못말했")
    evidence_bound = bool(message and new_value in message)
    if (slot.id in _EVIDENCE_MUTABLE_FREE_TEXT_IDS
            and slot.capture == "full_message" and not slot.values and not slot.red_flag
            and current_value != new_value and evidence_bound
            and any(marker in normalized for marker in correction_markers)):
        return True
    if (slot.id in _EVIDENCE_MUTABLE_FREE_TEXT_IDS
            and slot.capture == "full_message" and not slot.values and not slot.red_flag
            and current_value != new_value and evidence_bound):
        return True
    if slot.id == "track" and slot.values and current_value not in slot.values:
        return new_value in slot.values  # A placeholder is not an established track.
    if slot.allow_override_values is None or new_value not in slot.allow_override_values:
        return False
    if current_value == new_value:
        return False
    if slot.id == "track":
        current_rank = _TRACK_RANK.get(current_value, -1)
        new_rank = _TRACK_RANK.get(new_value, -1)
        if new_rank < current_rank:
            return False
    restricted = slot.override_signals and slot.override_signals.get(new_value)
    if restricted:
        return message is not None and _match_signal(message, restricted) is not None
    return True


def extract_fake(message: str, schema: Schema, filled: dict, last_question_slot_id=None) -> dict[str, str]:
    """fake 모드 전용 결정론적 슬롯 추출.

    활성 상태이면서 아직 채워지지 않은 슬롯을 대상으로 signals 부분문자열 매칭을
    시도한다. 이미 채워진 슬롯은 기본적으로 덮어쓰지 않지만, 스키마가
    allow_override_values로 허용한 값(예: 위기 승격)은 갱신한다. 이 함수는
    filled를 변경하지 않고 이번 발화로 새로 채워진 슬롯만 담은 dict를 반환한다.
    """
    new_fills: dict[str, str] = {}
    for slot in schema.active_slots(filled):
        if not slot.accepts_answer(last_question_slot_id):
            continue
        if slot.signals is None:
            continue
        if (
            slot.id == "track"
            and slot.values
            and "위기" in slot.values
            and crisis_signals.detect_crisis(message) is not None
        ):
            matched_value = "위기"
        else:
            matched_value = _match_signal(message, slot.signals)
        if matched_value is None:
            continue
        if _is_rejected_by_signal_guard(message, slot, last_question_slot_id):
            continue
        if slot.id in filled and not _can_override(slot, filled[slot.id], matched_value, message):
            continue
        new_fills[slot.id] = _fake_slot_value(message, matched_value, slot)
    return new_fills


def extract_classification(message: str, schema: Schema, filled: dict, last_question_slot_id=None) -> dict[str, str]:
    """닫힌 값 집합(values)을 선언한 분류 슬롯만 신호어로 결정론 판정한다. 실모드용.

    track을 모델 재량에 맡기면 같은 발화에도 채웠다 말았다 한다(실측). track이 비면
    when 분기 슬롯(symptom_context / crisis_*)이 통째로 안 켜지고, 위기 트랙을 놓치는
    건 안전 실패다. 자유서술 슬롯(chief_complaint 등)은 여전히 모델이 의미 요약한다.
    """
    classify_ids = {slot.id for slot in schema.slots if slot.values}
    return {
        slot_id: value
        for slot_id, value in extract_fake(message, schema, filled, last_question_slot_id).items()
        if slot_id in classify_ids
    }

def crisis_signal_present(message: str, schema: Schema) -> bool:
    """계열 판정과 기존 스키마 신호 모두를 모델 호출 전 안전 경로에 쓴다."""
    for slot in schema.active_slots({}):
        if slot.id == "track" and isinstance(slot.signals, dict):
            if "위기" in slot.signals and crisis_signals.detect_crisis(message) is not None:
                return True
            if _match_signal(message, slot.signals) == "위기":
                return True
    return False


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


def extract_real(
    reply: str,
    schema: Schema,
    filled: dict,
    message: str | None = None,
    last_question_slot_id: str | None = None,
) -> tuple[str, dict[str, str]]:
    """실모드 LLM 응답에서 ```slots fenced JSON 블록을 분리해 신뢰 경계로 거른다.

    LLM 출력은 신뢰 경계 밖이다 — fenced 블록 분리 실패나 JSON 파싱 실패는
    그 턴의 추출을 스킵한다(원문 그대로, 빈 dict 반환. 다음 턴에 만회하므로
    파싱 실패의 영향은 그 턴 한정 — FP19 방지). 파싱에 성공해도 각 항목을
    4중 필터로 거른다: 스키마 활성 슬롯 id 화이트리스트에 없으면 폐기,
    문자열이 아니면 폐기, 200자를 넘으면 폐기, 이미 채워진 슬롯이면 폐기한다.
    단 스키마가 allow_override_values로 명시한 안전 승격 값은 허용한다. 통과분만
    반환하고, reply에서는 슬롯 JSON 블록을 제거해 사용자·history·storage에는 절대 노출하지 않는다.
    """
    match = _SLOTS_FENCE_RE.search(reply)
    if match is None:
        return reply, {}

    clean_reply = reply[: match.start()].rstrip()

    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return clean_reply, {}

    if not isinstance(parsed, dict):
        return clean_reply, {}

    accepted: dict[str, str] = {}
    # Validate track first so dependent slots in the same block can become active.
    for slot_id, value in sorted(parsed.items(), key=lambda item: item[0] != "track"):
        active_slots = {slot.id: slot for slot in schema.active_slots({**filled, **accepted})}
        slot = active_slots.get(slot_id)
        if slot is None:
            continue
        if not slot.accepts_answer(last_question_slot_id):
            continue
        if not isinstance(value, str):
            continue
        if len(value) > _MAX_SLOT_VALUE_LEN:
            continue
        value = value.strip()
        if not value:
            continue
        if safety.sanitize_model_reply(value, "__blocked_slot__") == "__blocked_slot__":
            continue
        if any(marker in value for marker in ("<", ">", "```", "[시스템 지시]", "[대화]")):
            continue
        # 닫힌 값 집합을 선언한 슬롯은 그 안의 값만 받는다. track이 대표적 —
        # when 분기(`track=위기`)가 이 값과 정확히 맞물리므로, 모델이 지어낸
        # 자유 문자열("work-related stress")을 받으면 조건부 슬롯이 통째로 안 켜진다.
        if slot.values and value not in slot.values:
            continue
        if _is_rejected_by_signal_guard(message, slot, last_question_slot_id):
            continue
        if slot_id in filled and not _can_override(slot, filled[slot_id], value, message):
            continue
        accepted[slot_id] = value

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
    red_flags = [slot.id for slot in active if slot.red_flag and slot.id in filled]
    return {
        "track": filled.get("track", "미확인"),
        "slots": dict(filled),
        "unfilled": {slot.id: "미확인" for slot in unfilled},
        "red_flags": red_flags,
        "review_required": filled.get("track") == "위기" or bool(red_flags),
    }


def _parse_slot(raw) -> Slot:
    if not isinstance(raw, dict):
        raise TypeError("slot 항목은 매핑이어야 한다")
    if "extract" in raw and raw["extract"] != "when_asked":
        raise SchemaExtractError("slot.extract는 when_asked만 허용합니다.")
    if "when_any" in raw and (
        not isinstance(raw["when_any"], list) or not raw["when_any"]
        or not all(isinstance(item, str) and re.fullmatch(r"[^=\s]+=[^=\s]+", item)
                   for item in raw["when_any"])
    ):
        raise SchemaExtractError("slot.when_any는 slot=value 조건 목록이어야 합니다.")
    return Slot(
        id=raw["id"],
        label=raw["label"],
        required=bool(raw.get("required", False)),
        priority=int(raw.get("priority", 0)),
        red_flag=bool(raw.get("red_flag", False)),
        when=raw.get("when"),
        unless=raw.get("unless"),
        values=raw.get("values"),
        allow_override_values=(
            raw.get("allow_override_values")
            if isinstance(raw.get("allow_override_values"), list)
            else None
        ),
        override_signals=(
            raw.get("override_signals") if isinstance(raw.get("override_signals"), dict) else None
        ),
        reject_signals=(
            raw.get("reject_signals") if isinstance(raw.get("reject_signals"), list) else None
        ),
        reject_unless_signals=(
            raw.get("reject_unless_signals")
            if isinstance(raw.get("reject_unless_signals"), list)
            else None
        ),
        signals=raw.get("signals"),
        ask=raw.get("ask"),
        capture=raw.get("capture") if isinstance(raw.get("capture"), str) else None,
        extract=raw.get("extract"),
        when_any=raw.get("when_any"),
    )


def load_schema(knowledge_dir) -> Schema | None:
    """<knowledge_dir>/_intake_schema.md 를 읽어 Schema로 바꾼다.

    부재 · fenced 블록 추출 실패 · YAML 파싱 오류 · 필수 키 누락 중 어느
    경로를 타든 예외 없이 None을 반환한다(형식 오류 = 폴백, 결정 D01).
    """
    schema_path = Path(knowledge_dir) / _SCHEMA_FILENAME
    if not schema_path.is_file():
        return None

    text = knowledge.read_safe_text(schema_path, max_bytes=_MAX_SCHEMA_FILE_BYTES)
    if text is None:
        return None
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

    validate_handoff_config(data, uses_exit=(Path(knowledge_dir) / "연결-지도.yaml").exists())

    version = data.get("version")
    opening_question = data.get("opening_question")
    slots_raw = data.get("slots")
    if not version or not opening_question or not isinstance(slots_raw, list) or not slots_raw:
        return None

    try:
        slots = [_parse_slot(raw) for raw in slots_raw]
    except SchemaExtractError:
        raise
    except (KeyError, TypeError, ValueError):
        return None

    ui = data.get("ui")
    if not isinstance(ui, dict):
        ui = {}

    return Schema(version=version, opening_question=opening_question, slots=slots, ui=ui,
                  closing=data.get("closing"))
