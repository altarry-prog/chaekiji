#!/usr/bin/env sh
# 책이지 MCP 참조 서버 — 준비·검증 한 번에 (demo 모드, 네트워크·인증키 불필요)
set -e
cd "$(dirname "$0")"
PY=python3
command -v "$PY" >/dev/null 2>&1 || PY=python
"$PY" -c "import yaml" 2>/dev/null || "$PY" -m pip install -r requirements.txt
echo "== 적합성 시험(48건) =="
"$PY" tests/run_scenarios.py
echo
echo "== 실험실 점검(14건) =="
"$PY" lab/check_store.py
echo
echo "== 중계 모드 시험(17건, 모의 중계) =="
"$PY" tests/run_relay.py
echo
echo "== 공개 모델 호스트 시험(6건, 모의 Ollama) =="
"$PY" tests/run_host.py
echo
echo "[chaekiji-mcp] 준비 완료 — 시험 85건. 상담 비서 연결은 README의 '상담 비서' 절, 공개 모델은 hosts/ollama_host.py 를 보세요."
