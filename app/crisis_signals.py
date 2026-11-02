"""모델 호출 전 자살·자해 표현을 보수적으로 감지하는 결정론 규칙.

문장 목록 대신 의도/행동/대상 조합을 매칭한다. 부정·인용은 안전 확인으로
보내며, 원문이나 매칭 구간은 반환·기록하지 않는다. 진단용 분류가 아니다.
"""

from dataclasses import dataclass
import re

from app.safety import normalize_for_signal


@dataclass(frozen=True)
class CrisisHit:
    family_id: str


# 공통 신호 정규화나 사용자 기록은 바꾸지 않고, 이 판정의 사본만 보정한다.
_TYPOS = (
    ("시퍼", "싶어"),
    ("시프", "싶"),
    ("가타", "같아"),
    ("잇", "있"),
    ("왓", "왔"),
    ("겟", "겠"),
)

# 제외는 발화 전체를 무효화하지 않는다. 매칭 구간이 이 관용 표현 안에
# 완전히 들어갈 때만 제외한다. 별도의 위기나 더 넓은 위험 문맥은 우선한다.
_IDIOMS = re.compile(
    r"(?:힘들|힘드|배고프|배고파|피곤|더워|졸려|추워|웃겨|미치)[가-힣]{0,4}죽겠"
    r"|미치겠"
    r"|쥐구멍(?:에|으로)(?:라도)?숨고싶"
    r"|(?:회사|직장)(?:를|을)?그만두고싶"
    r"|다때려치우고여행(?:을)?가고싶"
    r"|심장(?:이|은)?터질(?:것|거)같"
)


def _gap(limit: int) -> str:
    """공백 제거 뒤에도 서로 다른 문장의 단어들을 이어 붙이지 않는다."""
    return rf"[^.!?。！？;]{{0,{limit}}}"


_G4, _G8, _G12, _G24 = (_gap(n) for n in (4, 8, 12, 24))
_SELF = r"(?:내|제|나의|저의|스스로|나자신|내자신|저자신)"
_LIFE = r"(?:삶|인생|목숨|생명|생을|사는것|사는게|살아가는것)"
_SELF_SUBJECT = r"(?:^|[.!?。！？;]|내가|제가|나는|저는|나만|저만)"
_ABSENCE_CONTEXT = r"(?:이세상에서|세상에서|그냥|차라리|이대로|아예|영영|이제){0,2}"

# 어간과 바람·행동을 따로 조합한다. '않으면 지각한다' 같은 조건문은
# 바람이 아니며, 부사/조사는 한 문장 안의 제한된 간격에서만 허용한다.
_WISH = (
    rf"(?:(?:았|었)?으면|면){_G8}(?:좋|바라|바랍|바래|싶|해요|합니다|하네|하는|하겠|편|낫)"
    rf"|(?:길|기를){_G8}(?:바라|바랍|바래|소망|원하|원해|빌|비는)"
    r"|(?:았|었)?으면(?=$|[.!?。！？;])"
)
_WAKE = r"(?:깨어나|깨어났|깨나|깨|깼)"
_NOT_WAKE = rf"(?:안{_G4}{_WAKE}|{_WAKE}(?:지|질)(?:는|도)?않|{_WAKE}지말)"
_NOT_OPEN_EYES = rf"눈(?:을|이|은|도)?{_G12}(?:안{_G4}(?:뜨|떴)|뜨(?:지|질)(?:는|도)?않|뜨지말)"
_BETTER = r"(?:낫|나을|나아)"
_BENEFIT = rf"(?:{_BETTER}|편(?:하|해|할|했)|짐(?:이|도|을)?(?:덜|줄)|부담(?:이|도|을)?(?:덜|줄))"
_OWN_ABSENCE = rf"(?:내가|제가|나는|저는){_G12}없(?:는(?:게|것|편)|으면|었으면|을때)"
_PERMANENT = r"(?:영영|영원히|아주)"
_DEPARTURE = (
    rf"(?:떠나|떠날|떠났|사라지|사라질|사라졌|없어지|없어졌)"
    rf"(?:{_G8}(?:싶|바라|버리|버릴|겠)|(?:{_WISH}))"
)
_END_INTENT = (
    rf"끝내(?:버리|버려|버릴|버렸|고{_G4}싶|는(?:게|것이|편이){_G8}{_BETTER})"
)
_EXHAUSTION = (
    rf"(?:버틸{_G4}(?:힘|기운|기력|자신){_G8}없"
    rf"|못{_G4}버티|버티(?:지|질){_G4}못)"
)
_RELEASE = (
    r"(?:다|모두|전부)?(?:(?:내려)?(?:놓아|놔)(?:버리|버려|버릴|버렸)?"
    r"|(?:내려)?놓(?:고|을|겠|는)|(?:내려)?놨|포기(?:하|할|해|했))"
)
_HIGH_PLACE = r"(?:옥상|교량|난간|창문|높은곳|다리(?:위|에서|에|엔|로|쪽))"
_HIGH_ACTION = r"(?:올라(?:가|갔|갈|간|서|와|왔)|오르|올랐|내려다(?:보|봤|볼)|서있|서서)"
_FAREWELL = r"(?:작별(?:의)?인사|마지막인사)"
_BELONGINGS = r"(?:물건|소지품|살림|짐|가진것)"

# 목적어가 생략된 종료/포기만 일상 활동의 목적어와 함께 제외한다.
# 제외 구간은 문장 경계로 가려 앞뒤의 별도 위기와 결합하지 못하게 한다.
# 삶을 명시한 구간은 가리지 않는다. 원문이나 공통 정규화는 바꾸지 않는다.
_ACTIVITY = r"(?:회사(?:일)?|직장|업무|프로젝트|회의|숙제|과제|작업|수업|게임|일을|일은|일도|일만)"
_ORDINARY_ACTION = re.compile(
    rf"{_ACTIVITY}{_G12}(?:{_END_INTENT})"
    rf"|{_ACTIVITY}{_G12}{_RELEASE}{_G12}(?:쉬|휴식|휴가|여행)"
)
_ORDINARY_TRAVEL = re.compile(rf"아주{_G12}여행{_G8}떠나{_G8}싶")

# 계열 순서는 로그/테스트에 쓸 첫 hit를 결정할 뿐, 위험도 순위가 아니다.
_RULES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (family, re.compile(pattern))
    for family, pattern in (
        (
            "direct_intent",
            r"자살|자해|죽(?:고|어버리고)싶|죽는(?:게|것이)낫"
            r"|살고싶지않|살기싫|그만살고싶|더는살기싫",
        ),
        (
            "disappearance",
            r"(?:사라지|없어지)(?:고싶|길바라|기를바라)"
            rf"|{_SELF_SUBJECT}{_ABSENCE_CONTEXT}(?:사라지|없어지|사라졌|없어졌)(?:면|으면|고나면){_G12}(?:편|좋|낫|다행)"
            rf"|{_SELF}(?:가|는)?(?:이세상에|세상에)?없었으면"
            rf"|{_SELF}자리(?:가|는|만)?{_G8}비워(?:지|졌){_G12}(?:편|좋|낫|영영)"
            rf"|{_OWN_ABSENCE}{_G24}{_BENEFIT}"
            rf"|{_BENEFIT}{_G12}{_OWN_ABSENCE}"
            rf"|{_PERMANENT}{_G12}{_DEPARTURE}"
            rf"|{_DEPARTURE}{_G12}{_PERMANENT}"
            rf"|세상(?:에|엔|에는|어디에도|그어디에도){_G12}{_SELF}(?:가|는)?(?:설|있을|살)?자리{_G8}없"
            rf"|{_SELF}자리{_G12}세상{_G12}없",
        ),
        (
            "no_future",
            rf"(?:내일|다음날|다음아침|아침){_G8}(?:안오|안왔|오지않|오지말|없었){_G4}(?:으면|았으면|길|기를)"
            rf"|{_NOT_WAKE}(?:{_WISH})"
            rf"|{_NOT_OPEN_EYES}(?:{_WISH})"
            rf"|(?:다시는)?아침(?:을)?맞지않{_G4}(?:으면|았으면|길|기를)",
        ),
        (
            "life_end",
            rf"{_LIFE}{_G12}(?:끝내|끝났으면|마감|마치고싶|그만두고싶)"
            rf"|{_END_INTENT}"
            rf"|(?:이렇게|이대로|이런식으로){_G4}살(?:아갈)?바에(?:는|야)?",
        ),
        (
            "no_reason_to_live",
            rf"(?:살|살아갈|살아야할|사는|사는게|사는것이){_G4}(?:이유|의미){_G8}(?:없|모르|못찾)"
            rf"|왜살아야{_G4}(?:모르|하)",
        ),
        (
            "conditional_death",
            rf"(?:내가|제가|나는|저는|나만|저만)죽(?:으면|는다면|고나면|어도)"
            rf"|{_SELF}죽음{_G8}(?:편|좋|낫)",
        ),
        (
            "self_harm",
            rf"(?:몸|손목|팔|피부)(?:을|를|에)?{_G8}(?:다치게|상처(?:를)?(?:내|낼|냈)|해치|해칠|긋|그을|그었|화풀이)"
            rf"|(?:나를|저를|스스로|내자신|제자신|나자신|저자신){_G4}(?:해치|해칠|다치게)"
            r"|상처(?:를)?(?:내고싶|낼것같|낼거같|내려)",
        ),
        (
            "farewell_note",
            rf"유서(?!깊)(?:를|도|는)?{_G12}(?:쓰|써|썼|적|남|작성|준비|정리|완성)"
            rf"|(?:^|{_SELF})유서(?:$|를|는|가|도)"
            rf"|마지막편지{_G12}(?:쓰|써|썼|적|남|작성|준비|완성)"
            rf"|{_FAREWELL}{_G12}(?:미리{_G8}(?:하|해|했)|해(?:두|놓)|준비)"
            rf"|미리{_G12}{_FAREWELL}{_G8}(?:하|해|했)"
            rf"|{_BELONGINGS}{_G12}정리{_G12}(?:나눠|나누어|나누려|나누고)"
            rf"|{_BELONGINGS}{_G12}(?:나눠|나누어){_G12}정리"
            rf"|(?:나눠|나누어)주{_G12}{_BELONGINGS}{_G12}정리",
        ),
        (
            "means_collection",
            rf"(?:수면제|진통제|알약|(?<![예계요절])약)(?:들)?(?:을|를|은|도)?{_G8}"
            r"(?:모으|모아|모았|모을|모은|쌓아|쌓았)",
        ),
        (
            "high_place",
            rf"(?:옥상|다리위|교량|난간|높은곳){_G12}(?:뛰어내|몸을던|아래(?:를)?(?:내려다|바라|보고|보는))"
            rf"|다리에서{_G8}(?:뛰어내|아래(?:를)?(?:내려다|바라|보고|보는))"
            rf"|{_HIGH_PLACE}{_G24}{_HIGH_ACTION}"
            rf"|{_HIGH_ACTION}{_G12}{_HIGH_PLACE}"
            r"|뛰어내리고싶",
        ),
        (
            "giving_up",
            rf"(?:{_LIFE}|살아가기|{_EXHAUSTION}){_G24}{_RELEASE}"
            rf"|{_RELEASE}{_G24}(?:{_LIFE}|살아가기|{_EXHAUSTION})",
        ),
    )
)


def detect_crisis(message: str) -> CrisisHit | None:
    """위기 계열 id만 반환한다. 원문·보정 사본·매칭 구간은 보관하지 않는다."""
    normalized = normalize_for_signal(message)
    for typo, correction in _TYPOS:
        normalized = normalized.replace(typo, correction)
    contextual = _ORDINARY_ACTION.sub(
        lambda match: match[0] if re.search(_LIFE, match[0]) else "." * len(match[0]),
        normalized,
    )
    idiom_spans = [
        match.span() for pattern in (_IDIOMS, _ORDINARY_TRAVEL)
        for match in pattern.finditer(normalized)
    ]
    for family, pattern in _RULES:
        candidate = contextual if family in {"life_end", "giving_up"} else normalized
        for match in pattern.finditer(candidate):
            if not any(start <= match.start() and match.end() <= end for start, end in idiom_spans):
                return CrisisHit(family_id=family)
    return None
