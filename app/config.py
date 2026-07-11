"""환경변수를 한곳에서 읽는 설정 모듈.

다른 모듈은 os.environ을 직접 읽지 않고 이 모듈의 Settings를 통해서만 설정값에
접근한다.
"""

from __future__ import annotations

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
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            knowledge_dir=os.environ.get("KNOWLEDGE_DIR", "knowledge"),
            model=os.environ.get("MODEL", "claude-haiku-4-5"),
            trust_proxy_hops=int(os.environ.get("TRUST_PROXY_HOPS", "0")),
            daily_request_cap=int(os.environ.get("DAILY_REQUEST_CAP", "500")),
        )
