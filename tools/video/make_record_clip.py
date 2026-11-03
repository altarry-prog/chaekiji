#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""흐름 2 장면용 클립 — 저장소에 있는 AI 몫 지표 기록표(server/lab/out/)를 그대로 화면에 띄워 넘겨 보는 영상(clips/model2.webm).

[11. 2.] 공통기반 지원(예정) 모델 3종(GPT-OSS·엑사원·Solar)의 AI 몫 지표(고정 문의 24건 × 3회, 11. 1.~2.)로 바꿈.
예전 판은 10. 18. 공개 모델 실측 기록표(코랩 노트북 코드를 깃허브 액션에서 돌린 것)를 보였다(이 파일의 깃 이력).
기록표 글은 한 글자도 바꾸지 않고, 마크다운을 화면용으로만 그린다. 자막은 clips/model2.json.

  python3 tools/video/make_record_clip.py      # → tools/video/clips/model2.webm (약 11초, 1280x720)

필요: pip install markdown playwright · ffmpeg 없어도 됨(플레이라이트가 webm으로 바로 씀)."""
import os, asyncio, shutil, glob, markdown
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "server", "lab", "out")
FONT = os.path.join(HERE, "fonts")
W, H = 1280, 720

CSS = """
@font-face{font-family:P;font-weight:400;src:url('file://%(f)s/Pretendard-Regular.otf')}
@font-face{font-family:P;font-weight:600;src:url('file://%(f)s/Pretendard-SemiBold.otf')}
@font-face{font-family:P;font-weight:700;src:url('file://%(f)s/Pretendard-Bold.otf')}
@font-face{font-family:M;src:url('file://%(f)s/D2Coding-Regular.ttf')}
html{background:#f6f8fa}
body{margin:0;font-family:P,sans-serif;color:#1f2328;font-size:19px;line-height:1.6;word-break:keep-all}
.bar{position:sticky;top:0;background:#24292f;color:#fff;font-size:16px;padding:10px 28px;display:flex;gap:14px;align-items:center;z-index:2}
.bar b{font-weight:600}.bar span{opacity:.75}
main{max-width:1120px;margin:22px auto 400px;background:#fff;border:1px solid #d0d7de;border-radius:8px;padding:18px 44px 40px}
h1{font-size:30px;border-bottom:1px solid #d8dee4;padding-bottom:8px}h2{font-size:24px;border-bottom:1px solid #d8dee4;padding-bottom:6px;margin-top:30px}
table{border-collapse:collapse;margin:12px 0;font-size:17px}th,td{border:1px solid #d0d7de;padding:6px 12px;text-align:left}th{background:#f6f8fa}
code{font-family:M,monospace;font-size:15px;background:#eff1f3;padding:1px 5px;border-radius:4px}
details{margin:8px 0;padding:6px 12px;background:#fbfbfc;border:1px solid #e5e8eb;border-radius:6px;font-size:16px}
summary{font-weight:600;cursor:pointer}
.hl{outline:4px solid #f2b705;outline-offset:3px;border-radius:4px;transition:outline-color .3s}
thead th{position:sticky;top:43px;z-index:1;box-shadow:0 1px 0 #d0d7de}   /* [11. 2.] 아래로 넘겨도 모델 이름 칸이 보이게 */
"""


def page(md_path, label):
    text = open(md_path, encoding="utf-8").read()
    body = markdown.markdown(text, extensions=["tables", "md_in_html"])
    rel = os.path.relpath(md_path, ROOT)
    return ("<!doctype html><meta charset=utf-8><style>" + CSS % {"f": FONT} + "</style>"
            f"<div class=bar><b>저장소 파일</b><span>{rel}</span><span style='margin-left:auto'>{label} · 글은 원문 그대로, 화면용으로만 그림</span></div>"
            f"<main>{body}</main>")


EASE = """([y,ms])=>new Promise(r=>{const el=document.scrollingElement;const y0=el.scrollTop;const t0=performance.now();
 const step=t=>{const k=Math.min(1,(t-t0)/ms);const e=k<.5?2*k*k:1-Math.pow(-2*k+2,2)/2;el.scrollTop=y0+(y-y0)*e;if(k<1)requestAnimationFrame(step);else r();};requestAnimationFrame(step);})"""


async def hl_rows(pg, words):
    await pg.evaluate("""ws=>{const rows=[...document.querySelectorAll('main table')][0].querySelectorAll('tr');
      rows.forEach(r=>{const c=r.querySelector('td');if(c&&ws.some(w=>c.textContent.includes(w)))r.classList.add('hl')})}""", words)


async def main():
    tmp = os.path.join(HERE, "rec", "clipwork")
    shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
    idx = os.path.join(tmp, "index.html"); r1 = os.path.join(tmp, "open.html"); r2 = os.path.join(tmp, "solar.html")
    open(idx, "w", encoding="utf-8").write(page(os.path.join(OUT, "README.md"), "실측 기록 목록"))
    open(r1, "w", encoding="utf-8").write(page(os.path.join(OUT, "ai_metrics_record_actions_2026-11-01_1529.md"), "GPT-OSS·엑사원 기록표(11. 1.)"))
    open(r2, "w", encoding="utf-8").write(page(os.path.join(OUT, "ai_metrics_solar_record_actions_2026-11-02_0945.md"), "Solar 기록표(11. 2.)"))
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": W, "height": H}, record_video_dir=tmp, record_video_size={"width": W, "height": H})
        pg = await ctx.new_page()
        # [11. 3.] 5분 안에 Solar 상담 창 화면을 더하려고 두 쪽만(약 11초): 공개 모델 2종 표 → Solar 표
        # 0~5.5초: GPT-OSS·엑사원 기록표 「한눈에」 — 다른 책으로 답함 · 판정 갈래 · 안내문 사실
        await pg.goto("file://" + r1); await pg.evaluate("document.fonts.ready"); await pg.wait_for_timeout(200)
        t1 = pg.locator("main table").first
        await hl_rows(pg, ["다른 책으로 답함", "판정 갈래가 기준과 같다", "안내문 사실 모두 옮김"])
        y = await pg.evaluate("e=>{const r=[...e.querySelectorAll('tr')].find(t=>t.textContent.includes('다른 책으로 답함'));return r.getBoundingClientRect().top+scrollY-300}", await t1.element_handle())
        await pg.evaluate(EASE, [y, 900]); await pg.wait_for_timeout(4300)
        # 5.5~11초: Solar 기록표 「한눈에」 — 한국어판 제목으로 바꿔 넘김 · 판정 갈래 · 안내문 사실
        await pg.goto("file://" + r2); await pg.evaluate("document.fonts.ready"); await pg.wait_for_timeout(200)
        t2 = pg.locator("main table").first
        await hl_rows(pg, ["한국어판 제목으로 바꿔 넘겼다", "판정 갈래가 기준과 같다", "안내문 사실 모두 옮김"])
        y = await pg.evaluate("e=>{const r=[...e.querySelectorAll('tr')].find(t=>t.textContent.includes('한국어판 제목으로'));return r.getBoundingClientRect().top+scrollY-200}", await t2.element_handle())
        await pg.evaluate(EASE, [y, 900]); await pg.wait_for_timeout(4300)
        vid = await pg.video.path()
        await ctx.close(); await b.close()
    dst = os.path.join(HERE, "clips", "model2.webm")
    # [11. 3.] 첫 쪽을 여는 0.5초(글꼴이 오기 전 빈 화면)는 잘라 냄
    import subprocess
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "0.5", "-i", vid, "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "30", "-row-mt", "1", "-an", dst], check=True)
    os.remove(vid)
    print("clip", dst, os.path.getsize(dst) // 1024, "KB")


asyncio.run(main())
