#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""README 맨 위 비교 움짤(docs/img/compare.gif)을 compare.html에서 만든다. 영상의 비교 장면과 같은 그림이다.

  python3 tools/video/cmp/shoot_app.py          # 오른쪽 휴대폰 그림을 먼저(같은 날 자료로)
  python3 tools/video/cmp/make_gif.py [출력.gif]   # 기본: tools/video/out/compare.gif → main의 docs/img/compare.gif로 옮김

- 실제 걸린 시간을 6배 빠르게(초당 8장, 한 장에 0.75초씩), 1280×720으로 찍어 960×540으로 줄인다. 끝 화면은 3.5초 머문다.
- 색은 ffmpeg 팔레트(128색, 흩뿌림 없음)로 줄인다. 흩뿌림을 넣으면 파일이 25% 커지는데 이 크기에서는 차이가 보이지 않았다(10. 30.)."""
import asyncio, os, shutil, subprocess, sys
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "out", "compare.gif")
FR = os.path.join(HERE, "..", "out", "cmp_frames")
SPD, FPS, END, HOLD = 6.0, 8, 80.0, 28


async def frames():
    shutil.rmtree(FR, ignore_errors=True); os.makedirs(FR)
    ts = [0.0] * 4; t = 0.0
    while t < END:
        ts.append(round(t, 3)); t += SPD / FPS
    ts += [END] * HOLD
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 1280, "height": 720})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto("file://" + os.path.join(HERE, "compare.html") + f"?spd={SPD:g}")
        await pg.evaluate("document.fonts.ready"); await pg.wait_for_timeout(600)
        for n, t in enumerate(ts):
            await pg.evaluate(f"setT({t})"); await pg.wait_for_timeout(int(1000 / FPS) - 25)
            await pg.screenshot(path=f"{FR}/{n:03d}.png")
        await b.close()
    if errs:
        sys.exit("화면 오류: " + "; ".join(errs[:3]))
    return len(ts)


n = asyncio.run(frames())
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
pal = os.path.join(FR, "palette.png")
sc = "scale=960:540:flags=lanczos"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", f"{FR}/%03d.png",
                "-vf", f"{sc},palettegen=max_colors=128:stats_mode=full", pal], check=True)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", f"{FR}/%03d.png", "-i", pal,
                "-lavfi", f"{sc}[x];[x][1:v]paletteuse=dither=none:diff_mode=rectangle", "-loop", "0", OUT], check=True)
print(f"{OUT} · {n}장 · {os.path.getsize(OUT) // 1024}KB")
