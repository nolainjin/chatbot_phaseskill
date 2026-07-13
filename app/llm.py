"""Claude 호출. MODEL 설정이 백엔드를 고른다.

- ``fake``: Anthropic 미호출. 검색된 문서 제목을 인용하는 오프라인 스텁 —
  API 키 없이 테스트/스모크를 돌리기 위한 스위치다.
- ``claude-cli``: 로컬에 인증된 ``claude`` CLI를 서브프로세스로 부른다. API 키
  없이 실제 Claude 응답을 받는 시연용 백엔드다. 슬롯 추출은 실모드와 같은
  경로(``intake.extract_real``)를 탄다.
- 그 외(``claude-haiku-4-5`` 등): Anthropic API 실호출. 운영 설정이다.
"""

import os
import subprocess
import tempfile
import time

import anthropic

from app.config import Settings

MAX_TOKENS = 1024

CLI_MODEL = "claude-cli"
# CLI 기동 오버헤드가 턴당 5~8초라 API 실호출보다 넉넉하게 잡는다.
CLI_TIMEOUT_SEC = 120
CLI_UNDERLYING_MODEL = "claude-haiku-4-5"
CLI_RETRIES = 3
CLI_RETRY_BACKOFF_SEC = 5

_ROLE_LABEL = {"user": "사용자", "assistant": "상담사"}


def _cli_prompt(history: list[dict[str, str]], user: str) -> str:
    """`claude -p`는 턴 사이 상태를 안 들고 있으므로 대화 이력을 프롬프트에 편다."""
    lines = [f"{_ROLE_LABEL.get(t['role'], t['role'])}: {t['content']}" for t in history]
    lines.append(f"사용자: {user}")
    return "\n".join(lines)


def _clean_env() -> dict[str, str]:
    """CLAUDE* 환경변수를 걷어낸 사본.

    Claude Code 세션 안에서 이 앱을 띄우면 CLAUDE_CODE_SESSION_ID 등이 상속된다.
    그대로 두면 자식 `claude`가 자신을 부모 세션의 하위 세션으로 인식해 부모의
    대화 컨텍스트를 끌고 온다 — 상담 응답에 코딩 얘기가 섞이고 슬롯이 {}로 빈다(실측).
    배포 환경엔 이 변수들이 없으므로 이 필터는 무해하다.
    """
    return {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}


def run_claude_cli(argv: list[str], timeout: int = CLI_TIMEOUT_SEC) -> str:
    """`claude` CLI 호출 공통 경로. 코딩 에이전트 정체성을 네 겹으로 차단하고 재시도한다.

    - ``--system-prompt``(호출자): 기본 프롬프트를 교체(append 아님). append면 코딩
      지시가 상담 페르소나에 섞인다.
    - ``--exclude-dynamic-system-prompt-sections``(호출자): 환경·git 등 동적 섹션 제거.
    - ``cwd``: 빈 임시 디렉터리. 리포 안에서 돌리면 CLAUDE.md를 읽는다.
    - ``env``/``stdin``: 부모 세션 상속 차단(_clean_env), 부모 stdin 상속 차단.

    장시간 대량 호출(평가 하네스 등)에서 간헐적으로 rc≠0이 난다 — 한 번의 일시
    실패로 대화 전체를 죽이지 않도록 백오프 재시도한다. 실패 메시지에는 stdout도
    담는다(CLI가 사유를 stdout으로 뱉는 경우가 있어 stderr만 보면 빈 문자열이다).
    """
    last = ""
    for attempt in range(CLI_RETRIES):
        try:
            with tempfile.TemporaryDirectory(prefix="claude-cli-") as neutral_cwd:
                proc = subprocess.run(
                    argv,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                    cwd=neutral_cwd,
                    env=_clean_env(),
                    stdin=subprocess.DEVNULL,
                )
            if proc.returncode == 0:
                return proc.stdout.strip()
            last = (
                f"rc={proc.returncode} "
                f"stdout={proc.stdout.strip()[-200:]!r} stderr={proc.stderr.strip()[-200:]!r}"
            )
        except subprocess.TimeoutExpired:
            last = f"timeout({timeout}s)"
        if attempt < CLI_RETRIES - 1:
            time.sleep(CLI_RETRY_BACKOFF_SEC * (2**attempt))
    raise RuntimeError(f"claude CLI 실패({CLI_RETRIES}회 시도): {last}")


def _ask_cli(system: str, history: list[dict[str, str]], user: str) -> str:
    return run_claude_cli(
        [
            "claude",
            "-p",
            _cli_prompt(history, user),
            "--system-prompt",
            system,
            "--exclude-dynamic-system-prompt-sections",
            "--model",
            CLI_UNDERLYING_MODEL,
            "--allowed-tools",
            "",
        ]
    )


def ask(
    system: str,
    history: list[dict[str, str]],
    user: str,
    doc_titles: list[str],
    settings: Settings,
) -> str:
    if settings.model == "fake":
        if not doc_titles:
            return "[fake] 관련 문서를 찾지 못했습니다."
        return f"[fake] 참고 문서: {', '.join(doc_titles)}"

    if settings.model == CLI_MODEL:
        return _ask_cli(system, history, user)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.model,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=history + [{"role": "user", "content": user}],
    )
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""
