@echo off
rem 책이지 MCP 참조 서버 — 준비·검증 한 번에 (네트워크·인증키 불필요. 처음 한 번만 PyYAML 설치에 인터넷 사용)
rem 탐색기에서 두 번 눌러도 결과를 읽을 수 있게 끝에서 멈춘다(아무 키나 누르면 닫힘).
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
set "PY="
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul && set "PY=python"
if not defined PY py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY (
  echo Python 3.9 이상이 필요합니다. https://www.python.org 에서 설치할 때 「Add python.exe to PATH」를 켜고 다시 실행하세요.
  pause
  exit /b 1
)
%PY% -c "import yaml" 2>nul || %PY% -m pip install -r requirements.txt
echo == 적합성 시험(48건) ==
%PY% tests\run_scenarios.py
if errorlevel 1 goto fail
echo.
echo == 실험실 점검(14건) ==
%PY% lab\check_store.py
if errorlevel 1 goto fail
echo.
echo == 중계 모드 시험(15건, 모의 중계) ==
%PY% tests\run_relay.py
if errorlevel 1 goto fail
echo.
echo == 공개 모델 호스트 시험(6건, 모의 Ollama) ==
%PY% tests\run_host.py
if errorlevel 1 goto fail
echo.
echo [chaekiji-mcp] 준비 완료 — 시험 83건. 상담 비서 연결은 README의 '상담 비서' 절, 공개 모델은 hosts\ollama_host.py 를 보세요.
pause
exit /b 0

:fail
echo.
echo 시험이 하나 실패했습니다. 위의 메시지를 그대로 담당자에게 알려 주세요.
pause
exit /b 1
