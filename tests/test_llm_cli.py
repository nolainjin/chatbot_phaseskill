"""claude-cli 백엔드 — argv 조립과 실패 처리.

실제 CLI는 부르지 않는다(턴당 수 초 + 구독 토큰 소모). subprocess.run을 가로채
넘어가는 인자만 검증한다. 실호출 확인은 scripts/smoke_cli.sh가 맡는다.
"""

import subprocess
import types

import pytest

from app import llm
from app.config import Settings


def _settings(model: str) -> Settings:
    return Settings(
        anthropic_api_key="",
        knowledge_dir="knowledge",
        model=model,
        trust_proxy_hops=0,
        daily_request_cap=500,
    )


def _capture(monkeypatch, returncode=0, stdout="응답", stderr=""):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return seen


def test_cli_backend_replaces_system_prompt_and_uses_haiku(monkeypatch):
    seen = _capture(monkeypatch)

    reply = llm.ask(
        system="너는 접수면담 챗봇이다.",
        history=[{"role": "user", "content": "안녕"}, {"role": "assistant", "content": "네"}],
        user="잠을 못 자요",
        doc_titles=[],
        settings=_settings(llm.CLI_MODEL),
    )

    argv = seen["argv"]
    assert reply == "응답"
    assert argv[0] == "claude"
    # append가 아니라 replace — 코딩 에이전트 프롬프트가 상담 페르소나에 섞이면 안 된다.
    assert "--system-prompt" in argv
    assert "--append-system-prompt" not in argv
    assert argv[argv.index("--system-prompt") + 1] == "너는 접수면담 챗봇이다."
    assert argv[argv.index("--model") + 1] == "claude-haiku-4-5"
    # 대화 이력이 프롬프트에 펼쳐진다 — claude -p는 턴 사이 상태를 안 들고 있다.
    prompt = argv[argv.index("-p") + 1]
    assert "사용자: 안녕" in prompt
    assert "상담사: 네" in prompt
    assert prompt.endswith("사용자: 잠을 못 자요")


def test_cli_backend_isolates_parent_claude_session(monkeypatch):
    """부모 Claude Code 세션 상속 차단 — 뚫리면 슬롯이 조용히 {}로 빈다."""
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "parent-session")
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("PATH", "/usr/bin")
    seen = _capture(monkeypatch)

    llm.ask(
        system="s",
        history=[],
        user="u",
        doc_titles=[],
        settings=_settings(llm.CLI_MODEL),
    )

    kwargs = seen["kwargs"]
    assert not [k for k in kwargs["env"] if k.startswith("CLAUDE")]
    assert kwargs["env"]["PATH"] == "/usr/bin"  # 나머지 환경은 살아 있어야 인증이 된다
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["cwd"]  # 리포 밖 중립 디렉터리 — CLAUDE.md를 읽지 않게
    assert "--exclude-dynamic-system-prompt-sections" in seen["argv"]


def test_cli_backend_retries_then_raises_with_stdout(monkeypatch):
    """일시 실패로 대화를 죽이지 않되, 끝내 실패하면 stdout까지 담아 사유를 보여준다.

    실측 회귀: 평가 하네스 60회 중 29회가 rc≠0으로 죽었는데 stderr가 비어 있어
    사유를 못 봤다. CLI는 실패 사유를 stdout으로 뱉기도 한다.
    """
    attempts = {"n": 0}
    slept: list[float] = []

    def fake_run(_argv, **_kwargs):
        attempts["n"] += 1
        return types.SimpleNamespace(returncode=1, stdout="usage limit reached", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(llm.time, "sleep", slept.append)

    with pytest.raises(RuntimeError, match="usage limit reached"):
        llm.ask(
            system="s",
            history=[],
            user="u",
            doc_titles=[],
            settings=_settings(llm.CLI_MODEL),
        )

    assert attempts["n"] == llm.CLI_RETRIES
    assert slept == [5, 10]  # 백오프 — 마지막 시도 뒤에는 안 잔다


def test_fake_backend_still_bypasses_cli(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("fake 모드는 CLI를 부르면 안 된다")

    monkeypatch.setattr(subprocess, "run", explode)

    reply = llm.ask(
        system="s",
        history=[],
        user="u",
        doc_titles=["문서A"],
        settings=_settings("fake"),
    )
    assert reply == "[fake] 참고 문서: 문서A"
