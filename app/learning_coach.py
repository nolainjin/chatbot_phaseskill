"""Deterministic state and response policy for the self-directed coaching pack."""

from dataclasses import dataclass
from typing import Final, Sequence

from app.knowledge import Document

STAGES: Final[tuple[str, ...]] = (
    "anchor",
    "locate",
    "diagnose",
    "intervene",
    "retry",
    "reflect",
)
BOTTLENECKS: Final[tuple[str, ...]] = (
    "concept",
    "interpretation",
    "strategy",
    "execution",
    "monitoring",
    "reflection",
    "ai_overreliance",
    "unknown",
)
ROUTES: Final[tuple[str, ...]] = (
    "concrete_scene",
    "artifact",
    "strategy",
    "understanding",
    "execution",
    "monitoring",
    "reflection",
    "ai_boundary",
    "provenance",
    "safety",
)

_STAGE_INDEX = {stage: index for index, stage in enumerate(STAGES)}


@dataclass(frozen=True, slots=True)
class LearningState:
    route: str = "concrete_scene"
    stage: str = "anchor"
    learning_scene: str = ""
    attempt_or_artifact: str = ""
    stuck_point: str = ""
    bottleneck: str = "unknown"
    micro_action: str = ""
    retry_evidence: str = ""


@dataclass(frozen=True, slots=True)
class CoachingTurn:
    state: LearningState
    question: str
    micro_action: str
    doc_titles: tuple[str, ...]


def _state_value(previous: LearningState | dict[str, str] | None, key: str) -> str:
    if previous is None:
        return ""
    if isinstance(previous, LearningState):
        return getattr(previous, key)
    value = previous.get(key, "")
    return value if isinstance(value, str) else ""


def _normalize_stage(value: str) -> str:
    return value if value in _STAGE_INDEX else "anchor"


def _next_stage(previous_stage: str, message: str) -> str:
    stage = _normalize_stage(previous_stage)
    if not previous_stage:
        return "anchor"
    if stage == "reflect":
        return "reflect"
    if stage == "retry":
        return "reflect"
    return STAGES[_STAGE_INDEX[stage] + 1]


def _route_for(message: str) -> str:
    text = message.lower()
    if any(term in text for term in ("이전 지시", "prompt", "프롬프트", "내부 내용", "무시하고")):
        return "safety"
    if any(term in text for term in ("답만", "ai가", "ai ", "인공지능", "그대로 따라")):
        return "ai_boundary"
    if any(term in text for term in ("출처", "검증된", "근거")):
        return "provenance"
    if any(term in text for term in ("설명하려", "돌아보고", "좋아졌는지", "효과인지", "다시 해 보니", "여러 방법")):
        return "reflection"
    if any(term in text for term in ("몇 번째 줄", "번째 줄", "답은", "답지", "풀이")):
        return "artifact"
    if any(term in text for term in ("전략", "방법을 골라")):
        return "strategy"
    if any(term in text for term in ("공식", "문장 관계", "설명", "단어 뜻", "다른 문제")):
        return "understanding"
    if any(term in text for term in ("시작", "계획을", "포기")):
        return "execution"
    if any(term in text for term in ("기억", "오답", "점검", "노트를", "회상")):
        return "monitoring"
    if any(term in text for term in ("다시 해", "재시도", "확인해")):
        return "retry"
    return "concrete_scene"


def _bottleneck_for(message: str, route: str) -> str:
    text = message.lower()
    if route == "ai_boundary":
        return "ai_overreliance"
    if route == "safety" or route == "provenance":
        return "unknown"
    if route == "reflection" and "방금 제안" in text:
        return "unknown"
    if route == "reflection":
        return "reflection"
    if route == "monitoring" and "노트를" in text and "아는 것" in text:
        return "concept"
    if route == "monitoring":
        return "monitoring"
    if route == "execution":
        return "execution"
    if any(term in text for term in ("전략", "방법을 골라")):
        return "strategy"
    if any(term in text for term in ("공식", "왜 쓰는지", "단어 뜻", "설명", "다른 문제")):
        return "concept" if "공식" in text or "왜 쓰는지" in text else "interpretation"
    if any(term in text for term in ("답은", "답지", "실수", "계산")):
        return "execution"
    if any(term in text for term in ("기억", "점검", "오답", "회상", "공부한")):
        return "monitoring"
    if any(term in text for term in ("설명하려", "좋아졌는지", "효과인지", "돌아보고")):
        return "reflection"
    return "unknown"


def _action_for(message: str, route: str, bottleneck: str) -> str:
    text = message.lower()
    if route == "safety":
        return "해당 문장을 지시가 아닌 참고자료로 표시하고 학습 장면으로 돌아간다."
    if route == "ai_boundary":
        if "계획" in text:
            return "제안 중 내가 선택한 이유를 한 문장으로 적는다."
        return "답 대신 지금 알고 있는 근거 한 가지를 먼저 적는다."
    if route == "provenance":
        return "사용한 문서 제목과 확인이 필요한 부분을 분리해 적는다."
    if route == "artifact":
        if "답지" in text or "답은" in text:
            return "답이 달라지는 첫 계산 단계를 표시한다."
        return "막힌 줄 바로 앞의 변환을 다시 적는다."
    if route == "strategy":
        return "가능한 풀이 전략을 두 가지 제목으로만 적는다."
    if route == "understanding":
        if "공식" in text:
            return "공식의 각 기호가 문제의 무엇을 뜻하는지 한 줄씩 연결한다."
        if "다른 문제" in text:
            return "설명 속 예시를 새로운 상황에 한 번 바꿔 본다."
        return "문장 속 원인과 결과를 화살표로 연결한다."
    if route == "execution":
        if "계획" in text and "크게" in text:
            return "오늘의 계획을 관찰 가능한 한 동작으로 줄인다."
        return "지금 할 수 있는 3분짜리 첫 동작 하나를 실행한다."
    if route == "monitoring":
        if "오답" in text:
            return "실수 유형과 다음 확인 신호를 한 쌍으로 적는다."
        if "점검" in text:
            return "점검 시점과 확인할 증거를 한 쌍으로 정한다."
        if "공부한" in text:
            return "노트를 보지 않고 핵심 세 문장을 회상해 적는다."
        return "자료를 덮고 기억나는 구조만 빈 종이에 적는다."
    if route == "reflection":
        if "방금 제안" in text:
            return "무엇이 달라져서 첫 줄이 가능했는지 한 문장으로 기록한다."
        if "좋아졌는지" in text:
            return "첫 시도와 재시도의 차이를 한 줄씩 비교한다."
        if "효과" in text:
            return "이번 재시도에는 개입 하나만 남긴다."
        if "다시 해 보니" in text:
            return "첫 시도와 재시도의 차이를 한 줄씩 비교한다."
        if "여러 방법" in text:
            return "이번 재시도에는 개입 하나만 남긴다."
        if "돌아보고" in text:
            return "잘된 시도와 조정할 시도를 각각 한 줄로 기록한다."
        return "설명을 시작-근거-결론 세 칸으로 나눈다."
    if route == "retry":
        return "같은 문제의 다음 한 단계만 직접 다시 써 본다."
    if route == "concrete_scene":
        if "수학" in text or "식" in text:
            return "문제에서 이미 주어진 정보 한 줄을 그대로 적어 본다."
        if "영어" in text or "지문" in text:
            return "지문에서 반복되는 단어 하나를 표시한다."
    if bottleneck == "concept":
        return "문제에서 이미 주어진 정보 한 줄을 그대로 적어 본다."
    return "지금 막힌 장면에서 직접 확인할 수 있는 한 가지를 적는다."


def _question_for(route: str, stage: str) -> str:
    questions = {
        "safety": "그 문장은 학습 장면과 어떤 관련이 있나요?",
        "ai_boundary": "답이나 계획을 받기 전에 지금 직접 알고 있는 근거는 무엇인가요?",
        "provenance": "어떤 문서의 어느 부분을 확인하고 싶나요?",
        "artifact": "막힌 지점 바로 앞에서 직접 적거나 시도한 것은 무엇인가요?",
        "retry": "같은 문제의 다음 한 단계를 직접 다시 해 보면 어떻게 되나요?",
        "reflection": "첫 시도와 비교해 이번 시도에서 달라진 점은 무엇인가요?",
    }
    if route in questions:
        return questions[route]
    if stage == "anchor":
        return "지금 다루는 대상과 직접 시도한 것, 멈춘 지점은 무엇인가요?"
    if stage == "locate":
        return "막힌 장면에서 가장 먼저 확인할 줄이나 문장은 어디인가요?"
    return "지금의 시도에서 다음으로 직접 확인할 수 있는 한 가지는 무엇인가요?"


def _titles_for(route: str, docs: Sequence[Document]) -> tuple[str, ...]:
    preferred = {
        "safety": "_safety_protocol",
        "provenance": "문헌근거와출처상태",
        "ai_boundary": "AI와 자기조절학습",
        "reflection": "코칭사례와반례",
        "execution": "개입카드",
        "monitoring": "학습전략과 피드백",
        "strategy": "학습장면진단루브릭",
        "understanding": "학습장면진단루브릭",
        "artifact": "학습장면진단루브릭",
        "concrete_scene": "자기주도학습 순환모델",
        "retry": "자기주도학습 순환모델",
    }
    target = preferred[route]
    matching = tuple(doc.title for doc in docs if target in doc.title)
    return matching or (target,)


def reduce_state(
    previous: LearningState | dict[str, str] | None,
    message: str,
    docs: Sequence[Document] = (),
) -> LearningState:
    """Reduce one learner message into a monotonic, deterministic coaching state."""
    route = _route_for(message)
    previous_stage = _state_value(previous, "stage")
    stage = "anchor" if route == "safety" else _next_stage(previous_stage, message)
    bottleneck = _bottleneck_for(message, route)
    return LearningState(
        route=route,
        stage=stage,
        learning_scene=message.strip(),
        attempt_or_artifact=_state_value(previous, "attempt_or_artifact") or message.strip(),
        stuck_point=_state_value(previous, "stuck_point") or message.strip(),
        bottleneck=bottleneck,
        micro_action=_action_for(message, route, bottleneck),
        retry_evidence=_state_value(previous, "retry_evidence"),
    )


def build_turn(
    previous: LearningState | dict[str, str] | None,
    message: str,
    docs: Sequence[Document] = (),
) -> CoachingTurn:
    state = reduce_state(previous, message, docs)
    return CoachingTurn(
        state=state,
        question=_question_for(state.route, state.stage),
        micro_action=state.micro_action,
        doc_titles=_titles_for(state.route, docs),
    )
