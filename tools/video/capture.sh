#!/bin/sh
# 명령 창 장면의 출력(t1~t4.txt)을 다시 받는다. 저장소 루트에서: sh tools/video/capture.sh
# 주의: 매일 갱신 자료(data/holdings-today.json)가 바뀌면 판정·관 수·조회일이 달라진다.
#       record.py의 자막(「꿈여울 등 7곳」, 「2026. 10. 16. 조회」 등)도 함께 고친다.
set -e
cd "$(dirname "$0")/../../server"
PY=$(command -v python || command -v python3)
V=../tools/video
CHAEKIJI_MODE=snapshot $PY lab/consult_cli.py "나미야 잡화점의 기적 빌리고 싶어요" 상동 > $V/t1.txt
CHAEKIJI_MODE=snapshot $PY lab/consult_cli.py "소년이 온다" 꿈빛 > $V/t2.txt
CHAEKIJI_MODE=relay CHAEKIJI_RELAY=http://127.0.0.1:9 $PY lab/consult_cli.py "채식주의자 있나요?" 상동 > $V/t3.txt
cd ..
sh server/run.sh > tools/video/t4.txt 2>&1
tail -1 tools/video/t4.txt
