#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""흐름 2 장면용 클립 — 저장소에 있는 공개 모델 실측 기록표(server/lab/out/)를 그대로 화면에 띄워 넘겨 보는 영상(clips/model2.webm).

코랩 실행 화면을 녹화하지 못해(행정망 PC에서 코랩이 열리지 않음) 그 자리에 「실제 기록표」를 보인다.
기록표 글은 한 글자도 바꾸지 않고, 마크다운을 화면용으로만 그린다. 자막은 clips/model2.json.

  python3 tools/video/make_record_clip.py      # → tools/video/clips/model2.webm (약 22초, 1280x720)

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


async def main():
    tmp = os.path.join(HERE, "rec", "clipwork")
    shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
    idx = os.path.join(tmp, "index.html"); rec = os.path.join(tmp, "record.html")
    open(idx, "w", encoding="utf-8").write(page(os.path.join(OUT, "README.md"), "실측 기록 목록"))
    open(rec, "w", encoding="utf-8").write(page(os.path.join(OUT, "model2_record_actions_2026-10-18_1446.md"), "4차 기록표(사람이 고치지 않은 원 기록)"))
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": W, "height": H}, record_video_dir=tmp, record_video_size={"width": W, "height": H})
        pg = await ctx.new_page()
        await pg.goto("file://" + idx); await pg.evaluate("document.fonts.ready"); await pg.wait_for_timeout(300)
        # 0~6초: 목록 — 공개 모델 네 차례 표
        tb = pg.locator("table").first
        await tb.scroll_into_view_if_needed(); y = await pg.evaluate("e=>e.getBoundingClientRect().top+scrollY-150", await tb.element_handle())
        await pg.evaluate(EASE, [y, 900]); await pg.wait_for_timeout(300)
        await pg.evaluate("e=>e.classList.add('hl')", await tb.element_handle())
        await pg.wait_for_timeout(4600)
        # 6~14초: 4차 기록표 — 한눈에 표
        await pg.goto("file://" + rec); await pg.evaluate("document.fonts.ready"); await pg.wait_for_timeout(300)
        t1 = pg.locator("table").first
        y = await pg.evaluate("e=>e.getBoundingClientRect().top+scrollY-170", await t1.element_handle())
        await pg.evaluate(EASE, [y, 1000])
        await pg.evaluate("e=>e.classList.add('hl')", await t1.element_handle())
        await pg.wait_for_timeout(6500)
        # 14~22초: 문의 5(베트남어) — 판정은 같지만 답 원문은 한국어, 도서관 이름도 틀림
        h = pg.locator("h2", has_text="문의 5").first
        await pg.evaluate("()=>document.querySelectorAll('details').forEach(d=>{if(d.closest('main')&&[...document.querySelectorAll('h2')].findIndex(x=>x.textContent.includes('문의 5'))>=0)d.open=false})")
        await pg.evaluate("()=>{const hs=[...document.querySelectorAll('h2')];const i=hs.findIndex(x=>x.textContent.includes('문의 5'));let n=hs[i].nextElementSibling;while(n&&n.tagName!=='H2'){if(n.tagName==='DETAILS')n.open=true;n=n.nextElementSibling}}")
        y = await pg.evaluate("e=>e.getBoundingClientRect().top+scrollY-70", await h.element_handle())
        await pg.evaluate(EASE, [y, 1400]); await pg.wait_for_timeout(2600)
        y2 = await pg.evaluate("e=>e.getBoundingClientRect().top+scrollY+260", await h.element_handle())
        await pg.evaluate(EASE, [y2, 1600]); await pg.wait_for_timeout(2600)
        vid = await pg.video.path()
        await ctx.close(); await b.close()
    dst = os.path.join(HERE, "clips", "model2.webm")
    shutil.move(vid, dst)
    print("clip", dst, os.path.getsize(dst) // 1024, "KB")


asyncio.run(main())
