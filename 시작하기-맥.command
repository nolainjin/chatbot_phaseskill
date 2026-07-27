#!/bin/bash
# 비개발자용 더블클릭 진입점 (macOS).
# Finder에서 더블클릭하면 터미널이 열리면서 실행된다.
# .command 확장자는 macOS가 실행 가능한 스크립트로 인식하는 확장자다.
#
# 처음 받은 파일은 실행 권한이 없을 수 있다. 그때는 터미널에서 한 번:
#   chmod +x "시작하기-맥.command"

cd "$(dirname "$0")" || exit 1

if command -v python3 >/dev/null 2>&1; then
    python3 run.py "$@"
    status=$?
    if [ $status -ne 0 ]; then
        read -r -p "  창을 닫으려면 Enter 를 누르세요… "
    fi
    exit $status
fi

cat <<'MESSAGE'

  ════════════════════════════════════════════════════
  파이썬이 설치되어 있지 않습니다
  ════════════════════════════════════════════════════

  이 프로그램을 실행하려면 파이썬이 먼저 필요합니다.

  아래 주소에서 내려받아 설치한 뒤 이 파일을 다시 실행하세요.
  https://www.python.org/downloads/

  (터미널에 익숙하시다면: brew install python)
  ════════════════════════════════════════════════════

MESSAGE
read -r -p "  창을 닫으려면 Enter 를 누르세요… "
exit 1
