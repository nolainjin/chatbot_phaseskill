"""Questions about the service itself ("엄마한테 전달되나요?", "이거 누가 봐요?").

The client is asking the chatbot, not the center, so the answer comes right away
and the intake resumes. Answers are fixed texts owned by the knowledge pack
(`service_answers`) and built only from facts the privacy notice already states;
the model never writes them. With an API model the answer classifier names the
topic; `detect` is the keyword path for fake/CLI backends and classifier failure.
"""

import re
import string

from app import safety

TOPICS = ("family", "who_sees", "deletion", "retention", "next_steps", "skip_ok", "ai", "center_matter")
FIELDS = ("center", "family", "raw_days", "summary_days", "deletion_days")
DEFAULT_CENTER = "접수를 맡긴 센터"
# Split after sentence marks and commas even without a space ("예요.엄마한테"), and after the
# connectives "-데"/"-지만" ("힘든데 엄마한테도 …"), so an answer said beside a question is not
# dropped with it. Not after "-고": "엄마한테 연락하고 그러나요?" must stay one question.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?？。,])(?![.!?？。,\d])\s*|(?<=데)\s+|(?<=지만)\s+|\n+")


def unknown_fields(text: str) -> set[str]:
    """Fields the answer may not use; unbalanced braces count as one."""
    try:
        names = {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}
    except ValueError:
        return {"<braces>"}
    return {name for name in names if name not in FIELDS}


# Words that only lead into the question ("근데 이거 엄마도 봐요?") answer nothing.
_LEAD_INS = {"근데", "그런데", "근데요", "그런데요", "그리고", "그래서", "혹시", "아", "음", "저", "저기", "참",
             "아무튼", "그럼", "그러면", "아니", "네", "예"}


def strip_questions(message: str) -> str:
    """The message without its sentences about the service: what is left may answer the question asked."""
    kept = [part.strip() for part in _SENTENCE_SPLIT.split(message) if part.strip() and detect(part) is None]
    kept = [part for part in kept if re.sub(r"[^가-힣a-zA-Z0-9]", "", part) not in _LEAD_INS]
    return " ".join(kept) if re.sub(r"[^가-힣a-zA-Z0-9]", "", " ".join(kept)) else ""

# Longer forms first so "부모님" wins over "부모" and "시어머니" over "어머니".
_FAMILY_WORDS = ("시어머니", "시아버지", "할머니", "할아버지", "어머니", "아버지", "부모님", "보호자",
                 "와이프", "엄마", "아빠", "부모", "남편", "아내", "오빠", "누나", "언니", "가족")
# Only unmistakable question endings: "학교에 가요" or "엄마가 제 폰을 봐요" are statements.
_QUESTION_END = re.compile(r"(나요|까요|죠|지요|는지요|건가요|는가요)\s*[?？.]*\s*$")


def _is_question(message: str) -> bool:
    text = message.strip()
    return "?" in text or "？" in text or bool(_QUESTION_END.search(text))


def _has(text: str, words) -> bool:
    return any(word in text for word in words)


def detect(message: str) -> str | None:
    """Keyword topic of a question about the service, or None. Conservative: a
    statement ("엄마가 제 폰을 봐요") is not a question about the service."""
    if not _is_question(message):
        return None
    text = safety.normalize_for_signal(message)
    family = _has(text, _FAMILY_WORDS)
    if family and _has(text, ("전달", "알게", "알려", "연락", "볼수", "보나", "보게", "보는거", "전해", "가나", "가는건",
                              "넘어가")):
        return "family"
    if _has(text, ("누가", "누구", "다른사람", "선생님말고", "상담사말고")) and _has(text, ("보", "봐", "알", "확인")):
        return "who_sees"
    if _has(text, ("지우", "지워", "지울", "지운", "삭제", "없앨", "없애")):
        return "deletion"
    if _has(text, ("저장", "보관")) and _has(text, ("얼마", "언제까지", "기간", "동안", "계속")):
        return "retention"
    if _has(text, ("보내면", "보낸뒤", "보낸다음", "보내고나면", "그다음", "다음엔", "다음에는", "이후")) and _has(
            text, ("어떻게", "뭐", "연락", "되나", "돼요")):
        return "next_steps"
    if _has(text, ("꼭", "다대답", "다답", "다말해", "전부", "모두")) and _has(text, ("대답", "답해", "답을", "말해")) and _has(
            text, ("해야", "되나", "하나요")):
        return "skip_ok"
    if _has(text, ("ai", "에이아이", "인공지능", "사람이에요", "사람인가", "사람이야", "사람맞", "로봇", "기계")):
        return "ai"
    if _has(text, ("상담비", "비용", "요금", "가격", "얼마예요", "얼마에요", "주차", "위치", "어디에있", "몇회", "몇번",
                   "횟수", "예약")):
        return "center_matter"
    return None


def _final_consonant(word: str) -> bool:
    last = word[-1]
    return "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0


def family_phrase(message: str) -> str:
    """'엄마나 다른 가족에게' from the family word in the question; '가족에게' otherwise."""
    found = [(message.find(word), -len(word), word) for word in _FAMILY_WORDS if word in message]
    if not found:
        return "가족에게"
    word = min(found)[2]
    if word == "가족":
        return "가족에게"
    return f"{word}{'이나' if _final_consonant(word) else '나'} 다른 가족에게"


class _Fill(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def compose(topic: str | None, schema, *, center: str | None = None, message: str = "", privacy=None) -> str | None:
    """The owned answer for this topic with its blanks filled, or None."""
    if topic not in TOPICS or schema is None:
        return None
    text = (getattr(schema, "service_answers", None) or {}).get(topic)
    if not isinstance(text, str) or not text.strip() or unknown_fields(text):
        return None  # a typo like {raw_day} must never reach the screen
    values = _Fill(center=(center or "").strip() or DEFAULT_CENTER, family=family_phrase(message))
    if privacy is not None:
        values.update(raw_days=privacy.retention_raw_days, summary_days=privacy.retention_summary_days,
                      deletion_days=privacy.deletion_days)
    try:
        return text.format_map(values).strip()
    except (ValueError, KeyError, IndexError, AttributeError):
        return None
