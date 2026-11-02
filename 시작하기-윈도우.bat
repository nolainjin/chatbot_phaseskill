@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 챗봇 실행

rem 비개발자용 더블클릭 진입점.
rem 이 파일의 유일한 임무는 "파이썬을 찾아서 run.py에 넘기는 것"이다.
rem 나머지 안내는 전부 run.py(파이썬)가 맡는다 — 인코딩과 로직을 다루기 훨씬 안전하다.
rem
rem 파이썬 자체가 없으면 run.py를 실행할 수 없으므로, 그 경우만 여기서 안내한다.

set PYTHON_CMD=

rem py 런처(윈도우 공식 설치본에 포함)를 먼저 본다. 여러 버전이 깔려 있어도 안전하다.
py -3 --version >nul 2>&1
if %errorlevel%==0 (
    set PYTHON_CMD=py -3
    goto :run
)

rem py가 없으면 python을 본다. Microsoft Store 스텁은 --version이 실패한다.
python --version >nul 2>&1
if %errorlevel%==0 (
    set PYTHON_CMD=python
    goto :run
)

echo.
echo   ════════════════════════════════════════════════════
echo   파이썬이 설치되어 있지 않습니다
echo   ════════════════════════════════════════════════════
echo.
echo   이 프로그램을 실행하려면 파이썬이 먼저 필요합니다.
echo.
echo   1. 아래 주소에서 내려받아 설치하세요
echo      https://www.python.org/downloads/
echo.
echo   2. 설치 화면 첫 페이지 맨 아래
echo      "Add python.exe to PATH" 를 반드시 체크하세요
echo      (이걸 빼먹으면 설치해도 여기서 다시 막힙니다)
echo.
echo   3. 설치가 끝나면 이 파일을 다시 실행하세요
echo   ════════════════════════════════════════════════════
echo.
pause
exit /b 1

:run
%PYTHON_CMD% run.py %*
if %errorlevel% neq 0 pause
