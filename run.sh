#!/usr/bin/env sh
# 책이지 MCP 참조 서버 — 준비·검증 한 번에 (demo 모드, 네트워크·인증키 불필요)
set -e
cd "$(dirname "$0")"
PY=python3
command -v "$PY" >/dev/null 2>&1 || PY=python
"$PY" -c "import yaml" 2>/dev/null || "$PY" -m pip install -r requirements.txt
echo "== 적합성 시험(33건) =="
"$PY" tests/run_scenarios.py
echo
echo "== 실험실 점검(14건) =="
"$PY" lab/check_store.py
echo
echo "[chaekiji-mcp] 준비 완료. MCP 클라이언트 연결 방법은 README의 '실행' 절을 보세요."
