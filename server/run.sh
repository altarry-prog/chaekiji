#!/usr/bin/env sh
# 책이지 MCP 참조 서버 — 준비·검증 한 번에 (시험은 네트워크·인증키 없이 돈다. 처음 한 번만 PyYAML 설치에 인터넷 사용)
set -e
cd "$(dirname "$0")"
trap 'rc=$?; if [ "$rc" -ne 0 ]; then echo; echo "[chaekiji-mcp] 멈췄습니다. 위의 메시지를 그대로 담당자에게 알려 주세요."; fi' EXIT
PY=python3
command -v "$PY" >/dev/null 2>&1 || PY=python
if [ -x .venv/bin/python ] && .venv/bin/python -c "import yaml" 2>/dev/null; then PY=.venv/bin/python; fi   # 전에 만든 가상환경이 있으면 그것을 쓴다
if ! "$PY" -c "import yaml" 2>/dev/null; then
  echo "[chaekiji-mcp] PyYAML 설치(처음 한 번, 인터넷 사용)"
  if ! "$PY" -m pip install -q -r requirements.txt; then
    # 「외부 관리」 파이썬(데비안 12·우분투 23.04 이후의 시스템 파이썬, 맥 Homebrew 등)은 pip 설치를 막는다 — 이 폴더 안 가상환경(.venv)에 설치
    echo "[chaekiji-mcp] 이 파이썬은 바로 설치를 막아 두었습니다 — 이 폴더 안 가상환경(.venv)에 설치합니다"
    if "$PY" -m venv .venv && .venv/bin/python -m pip install -q -r requirements.txt; then
      PY=.venv/bin/python
    else
      rm -rf .venv                                        # 만들다 만 가상환경은 남기지 않는다
      echo "PyYAML을 설치하지 못했습니다. 아래 가운데 하나로 설치한 뒤 다시 실행하세요."
      echo "  · 데비안·우분투: sudo apt install python3-yaml   (가상환경이 안 되면: sudo apt install python3-venv)"
      echo "  · 맥(Homebrew): brew install pyyaml"
      echo "  · 또는 python.org의 파이썬 3.9 이상을 설치"
      exit 1
    fi
  fi
fi
echo "== 적합성 시험(50건) =="
"$PY" tests/run_scenarios.py
echo
echo "== 실험실 점검(14건) =="
"$PY" lab/check_store.py
echo
echo "== 중계 모드 시험(30건, 모의 중계) =="
"$PY" tests/run_relay.py
echo
echo "== 공개 모델 호스트 시험(10건, 모의 Ollama) =="
"$PY" tests/run_host.py
echo
echo "[chaekiji-mcp] 준비 완료 — 시험 104건. 상담 비서 연결은 README의 '상담 비서' 절, 공개 모델은 hosts/ollama_host.py 를 보세요."
if [ "$PY" = ".venv/bin/python" ]; then                  # [10/19 밤] 리허설 지적 — 가상환경에 설치했으면 다음 명령도 그 파이썬으로
  echo "※ 이 PC는 파이썬 패키지 설치를 막아 두어 이 폴더의 가상환경(.venv)에 설치했습니다."
  echo "  다음 명령(lab/consult_cli.py · hosts/ollama_host.py · 클로드 데스크톱 설정의 command)은 python 대신 아래 파이썬으로 실행하세요."
  echo "  $(pwd)/.venv/bin/python"
fi
