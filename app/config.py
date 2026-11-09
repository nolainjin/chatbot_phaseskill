"""애플리케이션 설정 — 환경변수를 한곳에서 읽는다."""

import os
from dataclasses import dataclass


@dataclass  # noqa: MUTABLE_OK  # noqa: SLOTS_OK - evaluators switch model in place
class Settings:
    """Process settings kept mutable for adversarial evaluator model switching."""

    anthropic_api_key: str
    knowledge_dir: str
    model: str
    trust_proxy_hops: int
    daily_request_cap: int
    stats_api_token: str = ""
    retention_raw_days: int = 90
    retention_summary_days: int = 365
    referral_min_check: str = "verified"
    # Center-mode answer classification may use its own API model and effort;
    # empty model means the reply model.
    classify_model: str = ""
    classify_effort: str = "low"

    def __post_init__(self):
        if self.referral_min_check not in {"verified", "web"}:
            raise ValueError("REFERRAL_MIN_CHECK는 verified 또는 web이어야 합니다.")
        if self.classify_effort not in {"low", "medium", "high", "xhigh", "max"}:
            raise ValueError("CLASSIFY_EFFORT는 low·medium·high·xhigh·max 중 하나여야 합니다.")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            knowledge_dir=os.getenv("KNOWLEDGE_DIR", "knowledge"),
            model=os.getenv("MODEL", "auto"),
            trust_proxy_hops=int(os.getenv("TRUST_PROXY_HOPS", "0")),
            daily_request_cap=int(os.getenv("DAILY_REQUEST_CAP", "500")),
            stats_api_token=os.getenv("STATS_API_TOKEN", ""),
            retention_raw_days=int(os.getenv("RETENTION_RAW_DAYS", "90")),
            retention_summary_days=int(os.getenv("RETENTION_SUMMARY_DAYS", "365")),
            referral_min_check=os.getenv("REFERRAL_MIN_CHECK", "verified"),
            classify_model=os.getenv("CLASSIFY_MODEL", ""),
            classify_effort=os.getenv("CLASSIFY_EFFORT", "low"),
        )
