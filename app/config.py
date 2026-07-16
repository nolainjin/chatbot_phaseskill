"""애플리케이션 설정 — 환경변수를 한곳에서 읽는다."""

import os
from dataclasses import dataclass


@dataclass
class Settings:
    anthropic_api_key: str
    knowledge_dir: str
    model: str
    trust_proxy_hops: int
    daily_request_cap: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            knowledge_dir=os.getenv("KNOWLEDGE_DIR", "knowledge"),
            model=os.getenv("MODEL", "auto"),
            trust_proxy_hops=int(os.getenv("TRUST_PROXY_HOPS", "0")),
            daily_request_cap=int(os.getenv("DAILY_REQUEST_CAP", "500")),
        )
