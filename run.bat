@echo off
rem 책이지 MCP 참조 서버 — 준비·검증 한 번에 (demo 모드, 네트워크·인증키 불필요)
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 가 필요합니다. python.org 에서 설치 후 다시 실행하세요.
  exit /b 1
)
python -c "import yaml" 2>nul || python -m pip install -r requirements.txt
echo == 적합성 시험(48건) ==
python tests\run_scenarios.py
if errorlevel 1 exit /b 1
echo.
echo == 실험실 점검(14건) ==
python lab\check_store.py
if errorlevel 1 exit /b 1
echo.
echo == 중계 모드 시험(14건, 모의 중계) ==
python tests\run_relay.py
if errorlevel 1 exit /b 1
echo.
echo == 공개 모델 호스트 시험(6건, 모의 Ollama) ==
python tests\run_host.py
if errorlevel 1 exit /b 1
echo.
echo [chaekiji-mcp] 준비 완료 — 시험 82건. 상담 비서 연결은 README의 '상담 비서' 절, 공개 모델은 hosts\ollama_host.py 를 보세요.
