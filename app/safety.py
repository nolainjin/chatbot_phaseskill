"""Prompt-injection guardrails for the demo chatbot.

This module is deliberately deterministic. The LLM can make the wording warmer,
but trust-boundary decisions must not depend on the same model being attacked.
"""

from __future__ import annotations

import base64
import binascii
import html
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import unquote

_WHITESPACE_RE = re.compile(r"\s+")
_BASE64_RE = re.compile(r"\b[A-Za-z0-9+/_-]{8,}={0,2}\b")
_BASE64_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/_-]{4,}={0,2}(?![A-Za-z0-9+/_=-])"
)
_HEX_RE = re.compile(r"\b(?:0x)?[0-9a-fA-F]{12,}\b")
_WORD_RE = re.compile(r"[a-zA-Z]{4,}")
_FORMAT_CATEGORIES = {"Cf", "Mn"}
_CONFUSABLE_TRANSLATION = str.maketrans(
    {
        "а": "a",
        "е": "e",
        "і": "i",
        "о": "o",
        "р": "p",
        "с": "c",
        "ѕ": "s",
        "у": "y",
        "ν": "v",
        "ο": "o",
        "ρ": "p",
        "ѵ": "v",
        "ո": "n",
        "ɡ": "g",
        "ԁ": "d",
        "ԛ": "q",
        "ⅼ": "l",
    }
)

_ATTACK_PATTERNS: dict[str, tuple[str, ...]] = {
    "instruction_override": (
        r"\b(ignore|disregard|forget|bypass|override)\b.{0,80}\b(previous|prior|above|system|developer|instruction|rules?)\b",
        r"\b(system|developer)\s+override\b",
        r"\bdo\s+not\s+follow\b.{0,40}\b(system|developer|previous|above)\b",
        r"\b(from\s+now\s+on|pretend|act\s+as)\b.{0,80}\b(ignore|unrestricted|developer|system|assistant)\b",
        r"\bbegin\s+your\s+(reply|response)\s+with\b",
        r"(?:忽略|无视|忘记|请忽略).{0,40}(指令|规则|系统|提示)",
        r"(?:無視|忘れて|従わない).{0,40}(指示|ルール|システム|プロンプト)",
        r"(?:ignora|ignorez|ignoriere|игнорируй).{0,60}(instrucciones|instructions|anweisungen|инструкции)",
        r"(이전|앞선|위|지금까지|이제까지|모든|전부|기존)\s*\S{0,3}\s*(지시|규칙|명령|지침|설정|프롬프트).{0,40}(무시|잊어|잊고|삭제|따르지|버려|취소)",
        r"이전\s*(지시|규칙|명령).{0,30}(무시|잊어|삭제|따르지|버려)",
        r"앞선\s*(지시|규칙|명령).{0,30}(무시|잊어|삭제|따르지|버려)",
        r"위\s*(지시|규칙|명령).{0,30}(무시|잊어|삭제|따르지|버려)",
        r"이전\s*(내용|대화|문맥).{0,30}(무시|잊어|잊고|삭제|따르지|버려)",
    ),
    "role_hijack": (
        r"\byou\s+are\s+now\b",
        r"\bdeveloper\s+mode\b",
        r"\bDAN\b",
        r"\bjailbreak\b",
        r"\b(unrestricted|uncensored)\s+(assistant|model|ai)\b",
        r"너는\s*이제",
        r"역할을\s*(바꿔|변경)",
        r"상담사(가|로)?\s*아니",
    ),
    "prompt_leak": (
        r"\bsystem\s*prompt\b",
        r"\bdeveloper\s*(message|instruction|prompt)\b",
        r"\bhidden\s*prompt\b",
        r"\breveal\b.{0,40}\b(prompt|instruction|system)\b",
        r"\b(print|show|output|list|display|quote|dump|echo|recite|transcribe)\b.{0,60}\b(prompt|instruction|instructions|guidelines|rules|configuration|system|developer|persona)\b",
        r"\bwhat\s+(were|are)\s+you\s+(told|instructed|given)\b",
        r"\brepeat\b.{0,80}\b(above|before|conversation\s+started|first\s+line)\b",
        r"시스템\s*프롬프트.{0,20}(보여|출력|공개|반복|알려|말해|읽어)",
        r"시스템\s*프롬프트(?:의\s*(?:내용|전문|원문))?\s*(?:이|가|은|는)?\s*(?:뭐|무엇)(?:야|인가|인지|입니까)?",
        r"개발자\s*(메시지|지시|프롬프트)",
        r"숨겨진\s*(프롬프트|지시)",
        r"내부\s*(프롬프트|지시|규칙)",
        r"프롬프트.{0,20}(보여|출력|공개|말해|읽어)",
        r"(지침|규칙|지시문|설정|역할\s*설명|안내문).{0,40}(그대로|전문|원문|전부|처음부터|나열|옮겨|따라\s*써|복사|출력|보여|알려)",
        r"(처음|최초|시작).{0,30}(받은|주어진).{0,30}(설정|지침|규칙|프롬프트).{0,40}(그대로|전문|원문|알려|보여|출력)",
        r"(운영|내부|숨겨진)\s*(규칙|지침|정책).{0,40}(전문|원문|그대로|출력|말해|보여|반복)",
        r"개발자\s*(메시지|지시|프롬프트).{0,40}(원문|그대로|반복|출력|공개)",
    ),
    "data_exfiltration": (
        r"\b(show|reveal|print|dump|tell|give|list|display)\b.{0,50}\b(api[_\s-]?key|secret|token|password|credential)\b",
        r"\b(api[_\s-]?key|secret|token|password|credential)\b.{0,50}\b(show|reveal|print|dump|tell|give|list|display)\b",
        r"(api\s*키|비밀\s*키|토큰|비밀번호).{0,20}(보여|출력|공개|덤프|알려|말해|읽어|반복|뭐)",
    ),
    "sensitive_internal_inquiry": (
        r"\b(account|account\s+id|email|user\s+id|identity|plan|subscription|provider|model)\b.{0,50}\b(confirm|show|reveal|tell|what|which|who)\b",
        r"\b(what|which|who).{0,50}\b(account|account\s+id|email|user\s+id|identity|plan|subscription|provider|model)\b",
        r"\b(cli|api)\b.{0,50}\b(auth|authentication|login|credential|token)\b",
        r"\b(system\s+prompt|runtime|filesystem|file\s*system|config(?:uration)?)\b.{0,50}\b(show|dump|print|reveal|read|list|tell|what|which)\b",
        r"\.env\b",
        r"\b(sqlite|database|db\s*schema|schema)\b.{0,40}\b(show|dump|print|reveal)\b",
        r"환경\s*변수.{0,30}(보여|출력|공개|알려|덤프|뭐|목록)",
        r"(계정|사용자|이메일|신원|요금제|구독|제공자).{0,30}(확인|보여|출력|공개|알려|말해|뭐|누구|어떤)",
        r"(?:(?:사용|구동|기반).{0,12}모델|(?:ai|챗봇|너|당신).{0,12}모델|모델.{0,12}(?:이름|버전|제공자)).{0,20}(확인|보여|출력|공개|알려|말해|뭐|무엇|어떤)",
        r"(cli|api).{0,30}(인증|로그인|자격|토큰|키).{0,30}(보여|출력|공개|알려|말해|확인)",
        r"(파일\s*시스템|런타임|설정|구성|config).{0,30}(보여|출력|공개|읽어|목록|알려|말해|뭐)",
        r"대화\s*기록.{0,20}(보여|출력|공개|덤프)",
        r"(db|데이터베이스|sqlite).{0,20}(구조|덤프|전체|보여|출력)",
    ),
    "markup_escape": (
        r"</\s*message\s*>",
        r"<\s*message\s+role\s*=\s*['\"]?\s*system",
        r"<\s*(script|iframe|img)\b",
        r"!\[[^\]]*\]\(\s*https?://",
        r"<!--.{0,120}\b(ignore|system|assistant|developer|instruction)\b",
        r"display\s*:\s*none",
        r"color\s*:\s*white",
        r"^\s*(사용자|상담사|user|assistant|system)\s*:",
        r"\[\s*시스템\s*지시\s*\]",
        r"\[\s*대화\s*\]",
        r"<\|im_(start|end)\|>",
        r"<\|endoftext\|>",
        r"\[/?INST\]",
        r"<</?SYS>>",
    ),
}

_FUZZY_TARGETS = {
    "ignore",
    "bypass",
    "override",
    "reveal",
    "delete",
    "system",
    "developer",
    "prompt",
    "instruction",
    "instructions",
    "previous",
}

_OUTPUT_LEAK_PATTERNS = (
    r"\[시스템 지시\]",
    r"\[접수 슬롯 상태",
    r"채워진 슬롯:",
    r"미충족 슬롯",
    r"레드플래그 규칙",
    r"턴 예산",
    r"다음 질문 슬롯",
    r"\[untrusted_knowledge\]",
    r"안전 규칙\(다른 모든 규칙에 우선\)",
    r"```\s*slots",
    r"응답을 마친 뒤 마지막 줄",
    r"아래 지식 문서 내용을 근거로 답하라",
    r"SYSTEM_INSTRUCTIONS",
    r"USER_DATA_TO_PROCESS",
    r"\bsystem\s*prompt\b",
    r"\bdeveloper\s*(message|instruction|prompt)\b",
    r"(?:내|나의|제)\s*시스템\s*프롬프트",
    r"시스템\s*프롬프트\s*(?:내용|전문|원문)",
    r"\b[A-Z][A-Z0-9_]{6,}(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)\b",
    r"\b(?:api[_\s-]?key|secret|password|bearer\s+token)\b",
    r"\b(?:sk-ant-|sk-[A-Za-z0-9]|ghp_|AKIA)[A-Za-z0-9_\-]{8,}\b",
    r"\b(?:anthropic|openai|codex|claude|gpt)[-_ ]?(?:api|model|cli|\d)\b",
    r"\b(?:i|we)\s+(?:use|am\s+running\s+on)\s+(?:a\s+|the\s+)?(?:model|provider)\b",
    r"\b(?:account|user)\s*(?:id|email|identity|plan|subscription)\b",
    r"\b(?:filesystem|runtime|environment\s+variable|configuration)\b",
    r"_safety_protocol\.md",
    r"_persona\.md",
    r"_tone\.md",
    r"<\s*/?\s*[a-zA-Z][^>]*>",
    r"\bon[a-z]+\s*=",
    r"\b(?:javascript:|data:text/html)",
)
_REMOTE_MARKDOWN_IMAGE_RE = re.compile(
    r"!\[[^\]]*\]\(\s*<?\s*(?:https?:|//)[^)]+\)|^\s*\[[^\]]+\]:\s*(?:https?:|//)",
    re.IGNORECASE | re.MULTILINE,
)
_RAW_ACTIVE_HTML_RE = re.compile(
    r"<\s*/?\s*[a-zA-Z][^>]*>|\bon[a-z]+\s*=|\b(?:javascript:|data:text/html)",
    re.IGNORECASE,
)
_TOOL_CALL_RE = re.compile(
    r"""["']tool["']\s*:\s*["'](?:filesystem|shell|http|browser)[._/:\w-]*["']""",
    re.IGNORECASE,
)
_MALFORMED_BASE64_RE = re.compile(r"\b[A-Za-z0-9+/]{16,}={3,}\b")
_MAX_ENCODED_FRAGMENTS = 8


@dataclass(frozen=True)
class SafetyAssessment:
    blocked: bool
    categories: tuple[str, ...]
    decoded_fragments: tuple[str, ...] = ()


def normalize_text(text: str) -> str:
    """Normalize obvious obfuscation before detection."""
    normalized = unicodedata.normalize("NFKC", text).casefold().translate(_CONFUSABLE_TRANSLATION)
    normalized = "".join(
        ch
        for ch in normalized
        if ch != "\u00ad" and unicodedata.category(ch) not in _FORMAT_CATEGORIES
    )
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    normalized = re.sub(r"(.)\1{2,}", r"\1", normalized)
    return normalized.strip()


def normalize_for_signal(text: str) -> str:
    """Space-insensitive form for Korean/English safety and routing signals."""
    return _WHITESPACE_RE.sub("", normalize_text(text))


def neutralize_untrusted_prompt_text(text: str) -> str:
    """Render user/model text safe to include as data inside a prompt."""
    neutral = html.unescape(str(text))
    neutral = re.sub(
        r"(?mi)^\s*(사용자|상담사|user|assistant|system)\s*:",
        "[role-label]:",
        neutral,
    )
    neutral = re.sub(
        r"\[\s*시스템\s*지시\s*\]",
        "[redacted-marker]",
        neutral,
        flags=re.IGNORECASE,
    )
    neutral = re.sub(
        r"\[\s*대화\s*\]", "[redacted-marker]", neutral, flags=re.IGNORECASE
    )
    neutral = neutral.replace("```", "[code-fence]").replace("<", "＜").replace(">", "＞")
    return " ".join(neutral.split())[:200]


def _looks_printable(decoded: bytes) -> bool:
    if not decoded:
        return False
    printable = sum(1 for b in decoded if b in (9, 10, 13) or 32 <= b <= 126 or b >= 128)
    return printable / len(decoded) >= 0.85


def _encoded_fragments(text: str) -> tuple[str, ...]:
    """Return whole and safely joinable Base64 candidates."""
    fragments = list(_BASE64_RE.findall(text))
    tokens = _BASE64_TOKEN_RE.findall(text)
    if len(tokens) > 1 and sum(len(token.rstrip("=")) for token in tokens) >= 8:
        fragments.append("".join(tokens))
    compact = re.sub(r"[^A-Za-z0-9+/_=-]", "", text)
    if len(compact.rstrip("=")) >= 8:
        fragments.append(compact)
    return tuple(dict.fromkeys(fragments))[: _MAX_ENCODED_FRAGMENTS + 1]


def _decode_base64_candidate(match: str) -> str | None:
    padded = match + ("=" * ((4 - len(match) % 4) % 4))
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            decoded = decoder(padded)
        except (binascii.Error, ValueError):
            continue
        if _looks_printable(decoded):
            return decoded.decode("utf-8", errors="ignore")
    return None


def _decode_fragments(text: str) -> tuple[str, ...]:
    """Decode short suspicious Base64/hex/rot13 payloads for detection only."""
    fragments: list[str] = []
    for match in _encoded_fragments(text):
        decoded = _decode_base64_candidate(match)
        if decoded:
            fragments.append(decoded)

    hex_tokens = _HEX_RE.findall(text)
    if len(hex_tokens) > 1:
        hex_tokens.append("".join(token[2:] if token.startswith("0x") else token for token in hex_tokens))
    for match in hex_tokens:
        raw = match[2:] if match.startswith("0x") else match
        if len(raw) % 2:
            continue
        try:
            decoded = bytes.fromhex(raw)
        except ValueError:
            continue
        if _looks_printable(decoded):
            fragments.append(decoded.decode("utf-8", errors="ignore"))

    if re.search(r"\b(rot13|decode|apply)\b", text, re.IGNORECASE):
        rot = text.translate(
            str.maketrans(
                "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
                "NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm",
            )
        )
        if rot != text:
            fragments.append(rot)
    return tuple(dict.fromkeys(fragments))


def _is_typoglycemia_variant(word: str, target: str) -> bool:
    if word == target:
        return True
    if len(word) != len(target) or len(word) < 5:
        return False
    return word[0] == target[0] and word[-1] == target[-1] and sorted(word[1:-1]) == sorted(
        target[1:-1]
    )


def _typoglycemia_categories(text: str) -> set[str]:
    matched: set[str] = set()
    for word in _WORD_RE.findall(text):
        token = word.casefold().rstrip("s")
        for target in _FUZZY_TARGETS:
            if _is_typoglycemia_variant(token, target.rstrip("s")):
                matched.add(target.rstrip("s"))

    categories: set[str] = set()
    if "ignore" in matched and ({"previous", "system", "instruction", "developer"} & matched):
        categories.add("typoglycemia_instruction_override")
    if "reveal" in matched and ({"prompt", "system", "instruction"} & matched):
        categories.add("typoglycemia_prompt_leak")
    if "bypass" in matched and ({"system", "instruction", "developer"} & matched):
        categories.add("typoglycemia_instruction_override")
    return categories


def assess_prompt_injection(text: str) -> SafetyAssessment:
    """Return a deterministic assessment of likely prompt-injection intent."""
    normalized = normalize_text(text)
    decoded = _decode_fragments(text)
    candidates = (normalized, *(normalize_text(fragment) for fragment in decoded))

    categories: set[str] = set()
    encoded_fragments = _encoded_fragments(text)
    if len(encoded_fragments) > _MAX_ENCODED_FRAGMENTS:
        categories.add("decoder_fragment_limit")
    if _MALFORMED_BASE64_RE.search(text):
        categories.add("malformed_encoding")
    for candidate in candidates:
        for category, patterns in _ATTACK_PATTERNS.items():
            if any(re.search(pattern, candidate, re.IGNORECASE | re.DOTALL) for pattern in patterns):
                categories.add(category)
        categories.update(_typoglycemia_categories(candidate))

    return SafetyAssessment(
        blocked=bool(categories),
        categories=tuple(sorted(categories)),
        decoded_fragments=decoded,
    )


def sanitize_model_reply(reply: str, fallback: str) -> str:
    """Block direct or bounded encoded leaks before rendering or persistence."""
    decoded = _decode_fragments(reply)
    candidates = (
        normalize_text(reply),
        normalize_text(unquote(reply)),
        normalize_text(html.unescape(reply)),
        *(normalize_text(fragment) for fragment in decoded),
    )
    if len(reply) > 1500 and ("##" in reply or "[" in reply or "```" in reply):
        return fallback
    if _RAW_ACTIVE_HTML_RE.search(reply) or _REMOTE_MARKDOWN_IMAGE_RE.search(reply):
        return fallback
    if _TOOL_CALL_RE.search(reply) or any(
        re.search(pattern, candidate, re.IGNORECASE | re.DOTALL)
        for candidate in candidates
        for pattern in _OUTPUT_LEAK_PATTERNS
    ):
        return fallback
    return reply
