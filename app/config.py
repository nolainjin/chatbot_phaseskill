"""애플리케이션 설정 — 환경변수를 한곳에서 읽는다."""

import os
from dataclasses import dataclass
from typing import Final

VOICE_STT_MODEL: Final = "qwen3-asr-0.6b-8bit"
VOICE_TTS_MODEL: Final = "supertonic-3"
VOICE_MIN_RECORDING_MS: Final = 800
VOICE_MAX_RECORDING_MS: Final = 60000
VOICE_SILENCE_AUTO_STOP: Final = False


def _parse_env_bool(raw_value: str | None) -> bool:
    return raw_value is not None and raw_value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    anthropic_api_key: str
    knowledge_dir: str
    model: str
    trust_proxy_hops: int
    daily_request_cap: int
    stats_api_token: str = ""
    voice_enabled: bool = False
    provider_bin: str = ""

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
        )
