"""애플리케이션 설정 — 환경변수를 한곳에서 읽는다."""

import os
from dataclasses import dataclass
from typing import Final

VOICE_STT_MODEL: Final = "qwen3-asr-0.6b-8bit"
VOICE_TTS_MODEL: Final = "supertonic-3:F1"
VOICE_MIN_RECORDING_MS: Final = 800
VOICE_MAX_RECORDING_MS: Final = 60000
VOICE_SILENCE_AUTO_STOP: Final = True


def _parse_env_bool(raw_value: str | None) -> bool:
    return raw_value is not None and raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_env_profile(
    raw_value: str | None, default: str, *, prefix: str = ""
) -> str | None:
    value = default if raw_value is None else raw_value.strip()
    if not value or len(value) > 128 or not value.isprintable():
        return None
    return f"{prefix}{value}"


def _tts_model_label() -> str | None:
    """Supertonic 화자 표기. 성별 스위치(VOICE_TTS_GENDER)로 여성 F1 / 남성 M4."""
    explicit = os.getenv("VOICE_SUPERTONIC_VOICE")
    if explicit is not None:
        return _parse_env_profile(explicit, "F1", prefix="supertonic-3:")
    gender = os.getenv("VOICE_TTS_GENDER", "female").strip().lower()
    return _parse_env_profile(None, "M4" if gender == "male" else "F1", prefix="supertonic-3:")


@dataclass  # noqa: MUTABLE_OK  # noqa: SLOTS_OK - evaluators switch model in place
class Settings:
    """Process settings kept mutable for adversarial evaluator model switching."""

    anthropic_api_key: str
    knowledge_dir: str
    model: str
    trust_proxy_hops: int
    daily_request_cap: int
    stats_api_token: str = ""
    voice_enabled: bool = False
    provider_bin: str = ""
    voice_stt_model: str | None = VOICE_STT_MODEL
    voice_tts_model: str | None = VOICE_TTS_MODEL

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            knowledge_dir=os.getenv("KNOWLEDGE_DIR", "knowledge"),
            model=os.getenv("MODEL", "auto"),
            trust_proxy_hops=int(os.getenv("TRUST_PROXY_HOPS", "0")),
            daily_request_cap=int(os.getenv("DAILY_REQUEST_CAP", "500")),
            stats_api_token=os.getenv("STATS_API_TOKEN", ""),
            voice_enabled=_parse_env_bool(os.getenv("VOICE_ENABLED")),
            provider_bin=os.getenv("PROVIDER_BIN", ""),
            voice_stt_model=_parse_env_profile(
                os.getenv("VOICE_STT_PROVIDER"), VOICE_STT_MODEL
            ),
            voice_tts_model=_tts_model_label(),
        )
