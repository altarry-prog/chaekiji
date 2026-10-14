@echo off
rem 책이지 MCP 참조 서버 — 준비·검증 한 번에 (demo 모드, 네트워크·인증키 불필요)
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 가 필요합니다. python.org 에서 설치 후 다시 실행하세요.
  exit /b 1
)
python -c "import yaml" 2>nul || python -m pip install -r requirements.txt
echo == 적합성 시험(33건) ==
python tests\run_scenarios.py
if errorlevel 1 exit /b 1
echo.
echo == 실험실 점검(14건) ==
python lab\check_store.py
if errorlevel 1 exit /b 1
echo.
echo [chaekiji-mcp] 준비 완료. MCP 클라이언트 연결 방법은 README의 '실행' 절을 보세요.
