import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
import time

import anthropic

from app.config import Settings

IS_WINDOWS = sys.platform == "win32"
# subprocess.CREATE_NEW_PROCESS_GROUP은 Windows에서만 정의된다. 상수를 여기서
# 고정해두면 다른 OS에서도 Windows 분기를 테스트로 검증할 수 있다.
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)

MAX_TOKENS = 1024

AUTO_MODEL = "auto"
CLI_MODEL = "claude-cli"
# CLI 기동 오버헤드가 턴당 5~8초라 API 실호출보다 넉넉하게 잡는다.
CLI_TIMEOUT_SEC = 120
CLI_UNDERLYING_MODEL = "claude-haiku-4-5"
CLI_RETRIES = 3
CLI_RETRY_BACKOFF_SEC = 5

CODEX_CLI_MODEL = "codex-cli"
CODEX_DEFAULT_MODEL = "gpt-5.4"
CODEX_TIMEOUT_SEC = 180
CODEX_RETRIES = 2
CODEX_RETRY_BACKOFF_SEC = 5

_AGENT_ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "HOME",
        "CODEX_HOME",
        "XDG_CONFIG_HOME",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "NO_COLOR",
    }
)

# Windows에서 이 값들을 빼면 자식 프로세스가 조용히 죽는다. SYSTEMROOT가 없으면
# winsock 초기화가 실패해 네트워크를 쓰는 CLI가 전부 깨지고, COMSPEC/PATHEXT가
# 없으면 `claude.cmd` 같은 셔임을 찾지 못한다. 인증 파일은 APPDATA 계열에 있다.
_WINDOWS_ENV_ALLOWLIST = frozenset(
    {
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "TEMP",
        "TMP",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
    }
)
MAX_MODEL_OUTPUT_CHARS = 12_000

_ROLE_LABEL = {"user": "사용자", "assistant": "상담사"}


def _cli_prompt(history: list[dict[str, str]], user: str) -> str:
    """`claude -p`는 턴 사이 상태를 안 들고 있으므로 대화 이력을 프롬프트에 편다."""
    lines = [f"{_ROLE_LABEL.get(t['role'], t['role'])}: {t['content']}" for t in history]
    lines.append(f"사용자: {user}")
    return "\n".join(lines)


def _clean_env() -> dict[str, str]:
    """Deny-by-default environment for the Claude CLI child process.

    Claude Code session variables must not leak into the child because they make
    the CLI inherit the parent coding context. App secrets such as API keys,
    stats tokens, or database URLs must not leak either. Claude CLI auth is read
    through the user's normal config under HOME/XDG paths.
    """
    return _clean_agent_env()


def _clean_agent_env() -> dict[str, str]:
    """자식 프로세스에 넘길 deny-by-default 환경.

    Windows 환경변수는 대소문자를 가리지 않으므로(`Path` vs `PATH`) 비교 키를
    대문자로 정규화한다. 원래 키 이름은 그대로 보존해서 넘긴다.
    """
    allowlist = _AGENT_ENV_ALLOWLIST | _WINDOWS_ENV_ALLOWLIST if IS_WINDOWS else _AGENT_ENV_ALLOWLIST
    return {
        key: value
        for key, value in os.environ.items()
        if (key.upper() if IS_WINDOWS else key) in allowlist
    }


def _resolve_executable(argv: list[str]) -> list[str]:
    """argv[0]을 절대경로로 바꾼다.

    Windows의 CreateProcess는 PATHEXT를 보지 않는다. `claude`/`codex`는 그곳에서
    `claude.cmd` 셔임으로 설치되므로 이름 그대로 넘기면 FileNotFoundError가 난다.
    shutil.which는 PATHEXT를 참조하므로 여기서 미리 확장자까지 붙여 해석한다.
    찾지 못하면 원래 argv를 그대로 돌려주고, 실패 처리는 호출자의 재시도·폴백
    경로에 맡긴다(auto 체인이 다음 모델로 넘어간다).
    """
    resolved = shutil.which(argv[0])
    return [resolved, *argv[1:]] if resolved else argv


class ModelOutputTooLarge(RuntimeError):
    pass


def _bounded_output(raw: str) -> str:
    cleaned = raw.strip()
    if len(cleaned) > MAX_MODEL_OUTPUT_CHARS:
        raise ModelOutputTooLarge(
            f"모델 출력이 {MAX_MODEL_OUTPUT_CHARS}자를 초과했습니다."
        )
    return cleaned


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
                    _resolve_executable(argv),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                    cwd=neutral_cwd,
                    env=_clean_env(),
                    stdin=subprocess.DEVNULL,
                )
            if proc.returncode == 0:
                return _bounded_output(proc.stdout)
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


def _codex_model(model_setting: str) -> str:
    """MODEL=codex-cli[:model] + CODEX_MODEL override를 지원한다."""
    prefix = f"{CODEX_CLI_MODEL}:"
    if model_setting.startswith(prefix):
        value = model_setting[len(prefix) :].strip()
        if value:
            return value
    return os.getenv("CODEX_MODEL", CODEX_DEFAULT_MODEL)


def _auto_model_chain() -> list[str]:
    configured = os.getenv("MODEL_CHAIN")
    if configured:
        models = [item.strip() for item in configured.split(",") if item.strip()]
        if models:
            return models
    return [f"{CODEX_CLI_MODEL}:{_codex_model(CODEX_CLI_MODEL)}", CLI_MODEL, "fake"]


def _codex_prompt(system: str, history: list[dict[str, str]], user: str) -> str:
    """Codex exec는 system 인자가 없으므로 상담 시스템 지시와 대화 이력을 한 프롬프트로 편다."""
    return (
        "[시스템 지시]\n"
        f"{system}\n\n"
        "[대화]\n"
        f"{_cli_prompt(history, user)}\n\n"
        "위 시스템 지시를 우선하여 상담사 최종 응답만 출력하라."
    )


def _new_process_group_kwargs() -> dict[str, object]:
    """자식을 별도 프로세스 그룹으로 띄우는 플랫폼별 인자.

    타임아웃 시 CLI가 띄운 손자 프로세스까지 함께 정리하려면 그룹이 필요하다.
    POSIX는 start_new_session, Windows는 CREATE_NEW_PROCESS_GROUP을 쓴다
    (start_new_session은 Windows에서 ValueError를 던진다).
    """
    if IS_WINDOWS:
        return {"creationflags": CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _kill_process_tree(process: "subprocess.Popen[str]") -> None:
    """타임아웃된 자식과 그 하위 프로세스를 강제 종료한다.

    POSIX는 killpg(SIGKILL)로 그룹을 통째로 정리한다. Windows에는 killpg도
    SIGKILL도 없으므로 taskkill /T로 트리를 정리하고, 실패하면 Popen.kill()로
    최소한 직계 자식은 회수한다(고아 손자가 남을 수 있으나 서버는 멈추지 않는다).
    """
    if IS_WINDOWS:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            process.kill()
        return
    # start_new_session=True로 띄웠으므로 자식이 세션 리더 = pgid는 pid와 같다.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _run_codex_process(argv: list[str], timeout: int, cwd: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        _resolve_executable(argv),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        stdin=subprocess.DEVNULL,
        cwd=cwd,
        env=env,
        **_new_process_group_kwargs(),
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_tree(process)
        process.communicate()
        raise
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def run_codex_cli(prompt: str, model: str, timeout: int = CODEX_TIMEOUT_SEC) -> str:
    """Codex CLI 호출 공통 경로. 중립 cwd + read-only sandbox로 리포 오염을 차단한다."""
    last = ""
    for attempt in range(CODEX_RETRIES):
        try:
            with tempfile.TemporaryDirectory(prefix="codex-cli-") as neutral_cwd:
                output_path = Path(neutral_cwd) / "response.txt"
                argv = [
                    "codex",
                    "exec",
                    "--ephemeral",
                    "--skip-git-repo-check",
                    "--ignore-rules",
                    "--sandbox",
                    "read-only",
                    "-C",
                    neutral_cwd,
                    "-m",
                    model,
                    "-o",
                    str(output_path),
                    prompt,
                ]
                proc = _run_codex_process(argv, timeout, neutral_cwd, _clean_agent_env())
                if proc.returncode == 0:
                    raw = output_path.read_text(encoding="utf-8") if output_path.is_file() else proc.stdout
                    cleaned = _bounded_output(raw)
                    if cleaned:
                        return cleaned
                    last = f"empty stdout={proc.stdout.strip()[-200:]!r}"
                else:
                    last = (
                        f"rc={proc.returncode} "
                        f"stdout={proc.stdout.strip()[-200:]!r} stderr={proc.stderr.strip()[-200:]!r}"
                    )
        except subprocess.TimeoutExpired:
            last = f"timeout({timeout}s)"
        if attempt < CODEX_RETRIES - 1:
            time.sleep(CODEX_RETRY_BACKOFF_SEC * (2**attempt))
    raise RuntimeError(f"codex CLI 실패({CODEX_RETRIES}회 시도): {last}")


def _fake_document_summary(system: str) -> str:
    marker = "[untrusted_knowledge]"
    if marker not in system:
        return ""
    payload_text = system.split(marker, 1)[1]
    payload_start = payload_text.find("[")
    if payload_start < 0:
        return ""
    try:
        payload = json.loads(payload_text[payload_start:])
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        return ""
    title = payload[0].get("title")
    body = payload[0].get("body")
    if not isinstance(title, str) or not isinstance(body, str):
        return ""
    excerpt = " ".join(body.split())[:240]
    return f"[fake] 학습 코칭 근거: {title}\n핵심: {excerpt}"


def _fake_reply(doc_titles: list[str], system: str = "") -> str:
    if not doc_titles:
        return "[fake] 관련 문서를 찾지 못했습니다."
    summary = _fake_document_summary(system)
    if summary:
        return summary
    return f"[fake] 참고 문서: {', '.join(doc_titles)}"


def _ask_single_backend(
    model: str,
    system: str,
    history: list[dict[str, str]],
    user: str,
    doc_titles: list[str],
    settings: Settings,
) -> str:
    if model == "fake":
        return _fake_reply(doc_titles, system)

    if model == CLI_MODEL:
        return _ask_cli(system, history, user)

    if model == CODEX_CLI_MODEL or model.startswith(f"{CODEX_CLI_MODEL}:"):
        return run_codex_cli(
            _codex_prompt(system, history, user),
            _codex_model(model),
        )
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=history + [{"role": "user", "content": user}],
    )
    for block in response.content:
        if block.type == "text":
            return _bounded_output(block.text)
    return ""


def ask(
    system: str,
    history: list[dict[str, str]],
    user: str,
    doc_titles: list[str],
    settings: Settings,
) -> str:
    if settings.model == AUTO_MODEL:
        for model in _auto_model_chain():
            try:
                return _ask_single_backend(model, system, history, user, doc_titles, settings)
            except (
                RuntimeError,
                FileNotFoundError,
                subprocess.SubprocessError,
                anthropic.APIError,
            ):
                continue
        return _fake_reply(doc_titles)
    return _ask_single_backend(settings.model, system, history, user, doc_titles, settings)
