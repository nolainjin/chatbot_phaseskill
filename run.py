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
import threading
import time
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
VENV_DIR = REPO_ROOT / ".venv"
REQUIREMENTS = REPO_ROOT / "requirements.lock"
ENV_FILE = REPO_ROOT / ".env"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

MIN_PYTHON = (3, 11)
IS_WINDOWS = sys.platform == "win32"
PYTHON_DOWNLOAD_URL = "https://www.python.org/downloads/"


def _print_block(title: str, lines: list[str]) -> None:
    """실패 안내를 눈에 띄게 묶어서 출력한다.

    비개발자에게 트레이스백을 보여주면 아무것도 전달되지 않는다. 무슨 일이
    일어났고 다음에 뭘 하면 되는지만 남긴다.
    """
    print()
    print("  " + "━" * 52)
    print(f"  {title}")
    print("  " + "━" * 52)
    for line in lines:
        print(f"  {line}" if line else "")
    print("  " + "━" * 52)
    print()


def _force_utf8_console() -> None:
    """콘솔 출력을 UTF-8로 고정한다.

    한국어 Windows 콘솔 기본 코드페이지는 cp949라, 아래 한글 안내문을 그대로
    print하면 UnicodeEncodeError로 런처가 죽는다. 서버를 띄우기도 전에.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            # line_buffering — 파일·파이프로 넘길 때 print가 블록 버퍼링되면
            # 자식 프로세스(pip) 출력과 순서가 뒤엉켜 안내문이 묻힌다.
            reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


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

class RepairFailed(RuntimeError):
    """복구 단계 실패 — 사용자에게 보여줄 로그를 함께 들고 있다."""

    def __init__(self, step: str, log: str):
        super().__init__(step)
        self.step = step
        self.log = log


def _run_quiet(step: str, argv: list[str], note: str = "") -> None:
    """복구 명령을 조용히 실행한다. 실패했을 때만 로그를 드러낸다.

    pip는 정상 동작 중에도 'Cache entry deserialization failed' 같은 경고를
    수십 줄 뱉는다. 처음 실행하는 비개발자에게는 그게 전부 오류로 보인다.
    성공하면 아무것도 보여주지 않고, 실패할 때만 원문을 붙여 올린다.
    """
    print(f"  · {step}…{f' {note}' if note else ''}", flush=True)
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise RepairFailed(step, str(exc)) from exc
    if proc.returncode != 0:
        raise RepairFailed(step, (proc.stdout + proc.stderr).strip()[-1500:])


def repair_environment(results: list[CheckResult]) -> None:
    """점검에서 걸린 항목 중 고칠 수 있는 것을 실제로 고친다."""
    failed = {r.name for r in results if not r.ok}

    if "가상환경(.venv)" in failed:
        _run_quiet("실행 환경 만드는 중", [sys.executable, "-m", "venv", str(VENV_DIR)])

    if failed & {"가상환경(.venv)", "의존성 패키지"}:
        _run_quiet(
            "필요한 구성요소 내려받는 중",
            [
                str(venv_python()), "-m", "pip", "install",
                "--quiet", "--disable-pip-version-check", "--no-input",
                "-r", str(REQUIREMENTS),
            ],
            note="(몇 분 걸립니다)",
        )

    if "설정 파일(.env)" in failed:
        print("  · 설정 파일 준비 중…", flush=True)
        ENV_FILE.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# 실행
# ─────────────────────────────────────────────────────────────────────────────

def _open_browser_when_ready(url: str, probe_url: str, timeout_sec: int = 40) -> None:
    """서버가 응답하기 시작하면 브라우저를 연다.

    주소를 직접 입력하게 하지 않는다. 다만 서버가 뜨기 전에 열면 오류 화면을
    보게 되므로, 뜰 때까지 기다렸다가 연다. 열지 못해도 서버는 그대로 둔다.
    """
    import urllib.request

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(probe_url, timeout=2).read()
        except Exception:
            time.sleep(0.5)
            continue
        try:
            webbrowser.open(url)
        except Exception:
            pass  # 브라우저를 못 열어도 주소는 화면에 찍혀 있다
        return


def serve(host: str, port: int, model: str, knowledge: str, reload: bool,
          open_browser: bool = True) -> int:
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

    base = f"http://{host}:{port}"
    print()
    print(f"  챗봇      {base}/")
    print(f"  관리자    {base}/stats.html")
    print(f"  모델      MODEL={model}   지식폴더 KNOWLEDGE_DIR={knowledge}")
    print()
    print("  브라우저가 자동으로 열립니다. 열리지 않으면 위 주소를 붙여넣으세요.")
    print("  종료하려면 이 창에서 Ctrl+C 를 누르세요.")
    print()

    if open_browser:
        threading.Thread(
            target=_open_browser_when_ready,
            args=(f"{base}/", f"{base}/api/config"),
            daemon=True,
        ).start()

    try:
        return subprocess.run(argv, cwd=str(REPO_ROOT), env=env, check=False).returncode
    except KeyboardInterrupt:
        print("\n  종료했습니다.")
        return 0


def handle_check_failures(results: list[CheckResult], args) -> int:
    """점검 실패를 처리하고, 준비가 끝나면 서버를 띄운다.

    대상 사용자가 전부 비개발자라는 전제로 설계했다.

    - 확인(y/N)을 받지 않는다. 고칠 수 있는 건 그냥 고친다. "의존성을
      설치할까요?"는 판단 근거가 없는 사람에게 던지면 안 되는 질문이다.
    - 대신 무엇을 하는지는 한 줄씩 보여준다. 조용히 하지는 않는다.
    - 실패하면 트레이스백 대신 다음에 뭘 해야 하는지를 말한다.
    """
    blocked = [r for r in results if not r.ok and not r.repairable]
    if blocked:
        _print_block("이 컴퓨터에서는 아직 실행할 수 없습니다", [
            f"{r.name}: {r.detail}" for r in blocked
        ] + [
            "",
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 이상을 설치한 뒤 다시 실행해 주세요.",
            f"내려받기: {PYTHON_DOWNLOAD_URL}",
            "설치 화면에서 'Add Python to PATH'를 반드시 체크하세요.",
        ])
        return 2

    broken = [r for r in results if not r.ok]
    if broken:
        print("  처음 실행이라 준비가 필요합니다. 자동으로 설정합니다.")
        print("  (인터넷 연결이 필요하며 몇 분 걸릴 수 있습니다)\n")
        try:
            repair_environment(results)
        except RepairFailed as exc:
            _print_block(f"자동 설정 중 문제가 생겼습니다 ({exc.step})", [
                "확인해 볼 것:",
                "  · 인터넷에 연결되어 있는지",
                "  · 회사·학교 네트워크라면 방화벽이 막고 있지 않은지",
                f"  · '{VENV_DIR.name}' 폴더를 지우고 다시 실행하면 해결되기도 합니다",
                "",
                "아래는 전달용 상세 내용입니다:",
                "",
                *exc.log.splitlines()[-15:],
            ])
            return 3
        except OSError as exc:
            _print_block("자동 설정 중 문제가 생겼습니다", [f"{type(exc).__name__}: {exc}"])
            return 3

        still_broken = [r for r in check_environment() if not r.ok]
        if still_broken:
            _print_block("설정을 마쳤지만 아직 준비되지 않은 항목이 있습니다", [
                f"{r.name}: {r.detail}" for r in still_broken
            ] + [
                "",
                f"'{VENV_DIR.name}' 폴더를 지우고 다시 실행해 보세요.",
            ])
            return 4

        print("\n  준비 완료.")

    return serve(args.host, args.port, args.model, args.knowledge, args.reload,
                 open_browser=args.open_browser)


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
    parser.add_argument("--no-browser", action="store_true", help="브라우저 자동 열기 끄기")
    args = parser.parse_args()
    args.open_browser = not args.no_browser

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


def _pause_before_exit(code: int) -> None:
    """실패로 끝났을 때 콘솔 창이 즉시 닫히는 것을 막는다.

    더블클릭 실행에서는 오류 메시지를 띄우자마자 창이 사라져 사용자에게는
    "아무 일도 안 일어났다"로 보인다. 안내를 읽을 시간을 준다. CI·파이프처럼
    비대화형 실행에서는 멈추면 안 되므로 tty일 때만 기다린다.
    """
    if code == 0 or not sys.stdin.isatty():
        return
    try:
        input("  창을 닫으려면 Enter 를 누르세요… ")
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    try:
        exit_code = main()
    except KeyboardInterrupt:
        exit_code = 0
    except Exception as exc:  # noqa: BLE001 - 비개발자에게 트레이스백을 띄우지 않는다
        _print_block("예상치 못한 오류로 실행하지 못했습니다", [
            f"{type(exc).__name__}: {exc}",
            "",
            "이 내용을 그대로 전달해 주시면 확인하겠습니다.",
        ])
        exit_code = 1
    _pause_before_exit(exit_code)
    sys.exit(exit_code)
