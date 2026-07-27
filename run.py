#!/usr/bin/env python3
"""크로스플랫폼 실행 런처 — Windows / macOS / Linux 공통 진입점.

    python run.py            # 환경 점검 -> (필요시) 준비 -> 서버 실행
    python run.py --check    # 점검만 하고 종료 (아무것도 바꾸지 않는다)
    python run.py --port 9000 --knowledge knowledge-math

.bat/.sh 쌍 대신 파이썬 한 파일로 둔 이유는 두 벌을 따로 손보다 갈라지는 걸
막기 위해서다. 이 파일은 표준 라이브러리만 쓰므로 의존성 설치 전에도 돌아간다.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
VENV_DIR = REPO_ROOT / ".venv"
REQUIREMENTS = REPO_ROOT / "requirements.lock"
ENV_FILE = REPO_ROOT / ".env"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

MIN_PYTHON = (3, 11)
IS_WINDOWS = sys.platform == "win32"


def _force_utf8_console() -> None:
    """콘솔 출력을 UTF-8로 고정한다.

    한국어 Windows 콘솔 기본 코드페이지는 cp949라, 아래 한글 안내문을 그대로
    print하면 UnicodeEncodeError로 런처가 죽는다. 서버를 띄우기도 전에.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def venv_python() -> Path:
    """venv 안의 파이썬 실행파일 경로 (Windows는 Scripts/, 그 외는 bin/)."""
    if IS_WINDOWS:
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def running_inside_venv() -> bool:
    try:
        return Path(sys.executable).resolve() == venv_python().resolve()
    except OSError:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 환경 점검
# ─────────────────────────────────────────────────────────────────────────────

class CheckResult:
    """점검 항목 하나의 결과."""

    def __init__(self, name: str, ok: bool, detail: str, repairable: bool = False):
        self.name = name
        self.ok = ok
        self.detail = detail
        self.repairable = repairable


def check_environment() -> list[CheckResult]:
    """실행 전 환경을 점검한다. 아무것도 고치지 않고 사실만 보고한다."""
    results = []

    version_ok = sys.version_info >= MIN_PYTHON
    results.append(CheckResult(
        "Python 버전",
        version_ok,
        f"{sys.version_info.major}.{sys.version_info.minor} "
        f"(필요: {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 이상)",
        repairable=False,  # 파이썬 자체는 런처가 설치해줄 수 없다
    ))

    venv_ok = venv_python().is_file()
    results.append(CheckResult(
        "가상환경(.venv)",
        venv_ok,
        str(venv_python()) if venv_ok else "없음",
        repairable=True,
    ))

    deps_ok = venv_ok and _dependencies_installed()
    results.append(CheckResult(
        "의존성 패키지",
        deps_ok,
        "설치됨" if deps_ok else f"미설치 또는 불완전 ({REQUIREMENTS.name})",
        repairable=True,
    ))

    env_ok = ENV_FILE.is_file()
    results.append(CheckResult(
        "설정 파일(.env)",
        env_ok,
        "있음" if env_ok else f"없음 ({ENV_EXAMPLE.name}에서 복사 필요)",
        repairable=True,
    ))

    return results


def _dependencies_installed() -> bool:
    """venv 파이썬에서 핵심 패키지를 실제로 임포트해 본다."""
    probe = "import fastapi, uvicorn, yaml, anthropic"
    try:
        proc = subprocess.run(
            [str(venv_python()), "-c", probe],
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


# ─────────────────────────────────────────────────────────────────────────────
# 환경 복구
# ─────────────────────────────────────────────────────────────────────────────

def repair_environment(results: list[CheckResult]) -> None:
    """점검에서 걸린 항목 중 고칠 수 있는 것을 실제로 고친다."""
    failed = {r.name for r in results if not r.ok}

    if "가상환경(.venv)" in failed:
        print("  · 가상환경 생성 중…")
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)

    if failed & {"가상환경(.venv)", "의존성 패키지"}:
        print(f"  · 의존성 설치 중… ({REQUIREMENTS.name})")
        subprocess.run(
            [str(venv_python()), "-m", "pip", "install", "-q", "-r", str(REQUIREMENTS)],
            check=True,
        )

    if "설정 파일(.env)" in failed:
        print(f"  · {ENV_EXAMPLE.name} -> {ENV_FILE.name} 복사")
        ENV_FILE.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# 실행
# ─────────────────────────────────────────────────────────────────────────────

def serve(host: str, port: int, model: str, knowledge: str, reload: bool) -> int:
    """uvicorn을 venv 파이썬으로 띄운다."""
    env = os.environ.copy()
    env["MODEL"] = model
    env["KNOWLEDGE_DIR"] = knowledge
    # 자식 파이썬도 UTF-8 모드로 — 한국어 Windows 로케일(cp949) 영향을 끊는다.
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    argv = [
        str(venv_python()), "-m", "uvicorn", "app.main:app",
        "--host", host, "--port", str(port),
    ]
    if reload:
        argv.append("--reload")

    print()
    print(f"  챗봇      http://{host}:{port}/")
    print(f"  관리자    http://{host}:{port}/stats.html")
    print(f"  모델      MODEL={model}   지식폴더 KNOWLEDGE_DIR={knowledge}")
    print("  (중지: Ctrl+C)")
    print()

    try:
        return subprocess.run(argv, cwd=str(REPO_ROOT), env=env, check=False).returncode
    except KeyboardInterrupt:
        return 0


def handle_check_failures(results: list[CheckResult], args) -> int:
    """점검 실패를 어떻게 처리할지 정하고, 통과하면 서버를 띄운다.

    이 함수가 런처의 성격을 결정한다. 고려할 것:

    - `r.repairable == False`인 실패(= Python 버전)는 런처가 손댈 수 없다.
      이건 무조건 안내 후 중단이다. python.org 설치 링크를 알려주는 게 친절하다.
    - 나머지(venv/의존성/.env)는 `repair_environment(results)`로 자동 복구가 된다.
      자동으로 고칠 것인가, 아니면 사용자에게 확인을 받을 것인가?
        · 자동 복구: 윈도우 노트북 사용자가 아무 생각 없이 `python run.py`만
          치면 되게 만든다. 대신 pip 설치가 조용히 일어나 놀랄 수 있다.
        · 확인 후 복구: 무슨 일이 일어나는지 보여주고 y/N을 받는다. 안전하지만
          한 단계가 늘고, 더블클릭 실행에서는 입력을 받기 애매하다.
      `input()`으로 확인을 받는다면 비대화형 실행(CI, 파이프)에서 멈추지 않도록
      `sys.stdin.isatty()`를 함께 봐야 한다.
    - 복구 후에는 재점검을 해야 하는가? (`check_environment()` 재호출)

    반환값은 프로세스 종료 코드다. 서버를 띄웠다면 `serve(...)`의 반환값을
    그대로 돌려주면 된다:
        return serve(args.host, args.port, args.model, args.knowledge, args.reload)
    """
    # TODO: 여기를 구현해 주세요.
    raise NotImplementedError("handle_check_failures를 구현해 주세요")


def main() -> int:
    _force_utf8_console()

    parser = argparse.ArgumentParser(
        description="챗봇 크로스플랫폼 실행 런처",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--check", action="store_true", help="환경 점검만 하고 종료")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--model", default=os.getenv("MODEL", "fake"))
    parser.add_argument("--knowledge", default=os.getenv("KNOWLEDGE_DIR", "knowledge"))
    parser.add_argument("--reload", action="store_true", help="코드 변경 시 자동 재시작")
    args = parser.parse_args()

    print(f"\n  환경 점검  ({sys.platform})")
    print("  " + "─" * 52)
    results = check_environment()
    for result in results:
        mark = "OK  " if result.ok else "FAIL"
        print(f"  [{mark}] {result.name:<16} {result.detail}")
    print()

    if args.check:
        return 0 if all(r.ok for r in results) else 1

    return handle_check_failures(results, args)


if __name__ == "__main__":
    sys.exit(main())
