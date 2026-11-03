#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Solar 상담 창 녹화 원본(clips/ask_raw/solar_raw.webm·marks.json, record-ask.yml이 올림) → 흐름 2 장면용 클립.
화면은 손대지 않고, 「묻기」를 누른 뒤 답을 기다린 구간만 약 2초로 빨리 감는다(자막에 몇 초였는지 밝힘).
  python3 tools/video/make_ask_clip.py   → clips/solar.webm(1280x720) + clips/solar.json(자막)"""
import json, os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "clips", "ask_raw")
m = json.load(open(os.path.join(RAW, "marks.json"), encoding="utf-8"))
k = m["marks"]
a0, a1, b1, c1 = max(0.0, k["click"] - 2.2), k["click"] + 0.8, k["done"], k["end"] - 1.5   # 입력 끝부분부터, 끝의 1.5초는 뺌(5분 안, 숫자 칸을 더 오래 보이려고)
wait = b1 - a1
speed = max(1.0, wait / 2.0)
d1, d2, d3 = a1 - a0, (b1 - a1) / speed, c1 - b1
flt = (f"[0:v]trim={a0}:{a1},setpts=PTS-STARTPTS[v1];[0:v]trim={a1}:{b1},setpts=(PTS-STARTPTS)/{speed:.3f}[v2];"
       f"[0:v]trim={b1}:{c1},setpts=PTS-STARTPTS[v3];[v1][v2][v3]concat=n=3:v=1:a=0,fps=30,scale=1280:720[v]")
out = os.path.join(HERE, "clips", "solar.webm")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(RAW, "solar_raw.webm"), "-filter_complex", flt, "-map", "[v]",
                "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "32", "-row-mt", "1", "-an", out], check=True)
when = m.get("recorded_kst", "")[:10].replace("-", ". ").replace(". 0", ". ") + "."
meta = {
    "title": "Solar 상담 창(docs/ask/) · 클로드 계정 없이",
    "tag": f"실제 화면 녹화 · {when} · 깃허브 액션",
    "caps": [
        [0, "같은 말을 Solar 상담 창에 넣습니다", f"구동안내서 흐름 2와 같은 말 · 받을 도서관 {m['pickup']} · 시험용(한 IP 10분 6번)"],
        [round(d1, 1), "Solar Pro 4가 같은 판정 도구를 불러 답합니다", f"답을 기다린 약 {wait:.0f}초는 빨리 감아 보여 줍니다"],
        [round(d1 + d2 + 0.3, 1), "Solar의 답과 도구가 정한 판정이 나란히", "판정·조회일·누리집 주소는 도구가 준 그대로 · 대출 상태는 정보나루 전일 기준"],
    ],
    "source": {"run": m.get("run", ""), "recorded_kst": m.get("recorded_kst", ""), "say": m["say"], "cut": [a0, a1, b1, c1], "speed": round(speed, 2)},
}
json.dump(meta, open(os.path.join(HERE, "clips", "solar.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("clip", out, f"{d1 + d2 + d3:.1f}s", os.path.getsize(out) // 1024, "KB")
