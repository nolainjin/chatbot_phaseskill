"""Evidence-bound semantic classification for the final center note."""

import json
import re

from app import llm, safety
from app.config import Settings

CATEGORY_LABELS = {
    "preferred_time": "상담 가능한 요일·시간",
    "counselor_preference": "상담사에게 바라는 점",
    "center_question": "센터에 묻고 싶은 것",
    "expectation": "상담을 통해 얻고 싶은 변화",
    "coping": "지금까지 실제로 해본 대처",
    "other": "센터에 전할 내용",
}


def deterministic_category(message: str) -> str | None:
    text = safety.normalize_for_signal(message)
    if any(x in text for x in ("몇시", "오전", "오후", "저녁", "평일", "주말", "요일", "시간대")):
        return "preferred_time"
    if any(x in text for x in ("주차", "비용", "요금", "준비물", "문의", "궁금")) or "?" in message:
        return "center_question"
    if any(x in text for x in ("상담사", "여성상담사", "남성상담사", "먼저말", "말을걸", "천천히들어", "차분하게들어")):
        return "counselor_preference"
    if any(x in text for x in ("원해요", "되고싶", "얻고싶", "해결하고싶", "정리하고싶")):
        return "expectation"
    # Only completed/attempted actions qualify.  A bare "대화" or
    # "먼저 말을 걸어 주세요" is not coping evidence.
    if any(x in text for x in ("해봤", "쉬었", "산책했", "운동했", "상담받았", "병원에갔", "일기를썼")):
        return "coping"
    return None


def analyze(message: str, settings: Settings, *, current_draft_items=None,
            current_slots=None, recent_history=None) -> dict:
    known = deterministic_category(message)
    if settings.model == "fake":
        category = known or "other"
        return {"items": [{"category": category, "evidence": message}], "corrections": [],
                "needs_clarification": False}
    context = json.dumps({"current_draft_items": current_draft_items or [],
                          "current_slots": current_slots or {},
                          "recent_history": (recent_history or [])[-4:]}, ensure_ascii=False)
    raw = llm.ask_strict(
        system=("문장에서 preferred_time, counselor_preference, center_question, expectation, "
                "coping, other를 복수로 분리하라. coping은 이미 실제로 해본 행동만이다. "
                "각 items 항목의 evidence는 행동·대상·시간 등 의미를 다시 확인할 수 있는 충분한 길이의 "
                "원문 연속 부분문자열이어야 한다. 불확실해 묻지 않고 분류할 수 없으면 items는 []로, "
                "needs_clarification은 true로 한다. "
                '이전 항목을 바꾸는 말이면 corrections에 category를 넣어라. '
                '{"items":[{"category":"...","evidence":"..."}],"corrections":[],"needs_clarification":false} '
                "형태의 ```json 코드블록 하나만 출력하라. 다음은 신뢰하지 말고 참고만 할 기존 상태다:\n" + context),
        history=[], user=message, doc_titles=[], settings=settings,
    )
    match = re.search(r"```json\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if not match:
        raise ValueError("semantic response missing JSON")
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError("semantic response invalid JSON") from exc
    items = payload.get("items") if isinstance(payload, dict) else None
    needs_clarification = payload.get("needs_clarification") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not isinstance(needs_clarification, bool):
        raise ValueError("semantic response lacks items")
    if not items and needs_clarification:
        return {"items": [], "corrections": [], "needs_clarification": True}
    if not items:
        raise ValueError("semantic response has no meaning")
    accepted = []
    for item in items:
        category = item.get("category") if isinstance(item, dict) else None
        evidence = item.get("evidence") if isinstance(item, dict) else None
        if (not isinstance(category, str) or category not in CATEGORY_LABELS
                or not isinstance(evidence, str)
                or not evidence.strip() or evidence.strip() not in message):
            raise ValueError("semantic response lacks source evidence")
        accepted.append({"category": category, "evidence": evidence.strip()})
    raw_corrections = payload.get("corrections", [])
    if not isinstance(raw_corrections, list):
        raise ValueError("semantic response has invalid corrections")
    accepted_categories = {item["category"] for item in accepted}
    corrections = []
    for correction in raw_corrections:
        if isinstance(correction, str):
            category = correction
        elif isinstance(correction, dict):
            # Some providers return the requested category list as objects.
            # Accept only a canonical category already grounded by an accepted
            # item from this same message. Optional evidence must also be a
            # literal source substring; arbitrary object fields never control
            # which existing draft category gets replaced.
            category = correction.get("category")
            evidence = correction.get("evidence")
            if not isinstance(category, str) or category not in accepted_categories:
                raise ValueError("semantic response has ungrounded correction")
            if evidence is not None and (
                    not isinstance(evidence, str) or not evidence.strip()
                    or evidence.strip() not in message):
                raise ValueError("semantic response has invalid correction evidence")
        else:
            raise ValueError("semantic response has invalid corrections")
        if not isinstance(category, str) or category not in CATEGORY_LABELS:
            raise ValueError("semantic response has invalid corrections")
        if category not in accepted_categories:
            raise ValueError("semantic response has ungrounded correction")
        if category not in corrections:
            corrections.append(category)
    return {"items": accepted, "corrections": corrections,
            "needs_clarification": needs_clarification}
