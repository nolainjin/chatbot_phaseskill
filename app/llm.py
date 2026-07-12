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

import anthropic

from app.config import Settings

MAX_TOKENS = 1024

CLI_MODEL = "claude-cli"
# CLI 기동 오버헤드가 턴당 5~8초라 API 실호출보다 넉넉하게 잡는다.
CLI_TIMEOUT_SEC = 120
CLI_UNDERLYING_MODEL = "claude-haiku-4-5"

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


def _ask_cli(system: str, history: list[dict[str, str]], user: str) -> str:
    """`claude` CLI를 상담 모델로 쓴다. 코딩 에이전트 정체성을 네 겹으로 차단한다.

    - ``--system-prompt``: 기본 프롬프트를 교체(append 아님). append면 코딩 지시가
      상담 페르소나에 섞인다.
    - ``--exclude-dynamic-system-prompt-sections``: 환경·git 상태 등 동적 섹션 제거.
    - ``cwd``: 빈 임시 디렉터리. 리포 안에서 돌리면 CLAUDE.md를 읽는다.
    - ``env``/``stdin``: 부모 세션 상속 차단(_clean_env), 부모 stdin 상속 차단.
    """
    with tempfile.TemporaryDirectory(prefix="lmwiki-cli-") as neutral_cwd:
        proc = subprocess.run(
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
            ],
            capture_output=True,
            text=True,
            timeout=CLI_TIMEOUT_SEC,
            check=False,
            cwd=neutral_cwd,
            env=_clean_env(),
            stdin=subprocess.DEVNULL,
        )
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI 실패(rc={proc.returncode}): {proc.stderr.strip()[-300:]}")
    return proc.stdout.strip()


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
