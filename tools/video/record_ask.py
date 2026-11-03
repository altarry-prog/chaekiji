#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""시연영상 흐름 2용 실제 화면: 공개된 Solar 상담 창(docs/ask/)에 구동안내서 흐름 2와 같은 말을 넣고 답이 나오기까지를 녹화한다.
깃허브 액션(record-ask.yml)에서 돈다(작업 공간의 망에서는 중계 주소가 막혀 있어서). 화면은 손대지 않은 실제 응답이며,
기다린 구간을 빨리 감는 일은 받아 온 뒤 make_ask_clip.py가 한다(그 구간을 marks.json에 적어 둠).

  python3 tools/video/record_ask.py --say "한강 소년이 온다 빌리고 싶어요, 역곡도서관에서 받을게요" --pickup 역곡 --out out_ask
"""
import argparse, asyncio, datetime, json, os, time
from playwright.async_api import async_playwright

URL = "https://altarry-prog.github.io/chaekiji/docs/ask/"
KST = datetime.timezone(datetime.timedelta(hours=9))


async def main(a):
    os.makedirs(a.out, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1, locale="ko-KR", bypass_csp=True,   # 상담 창의 보안 정책(CSP)이 대기 함수를 막아 녹화 도구에서만 풂
                                  record_video_dir=a.out, record_video_size={"width": 1280, "height": 720})
        t0 = time.time(); marks = {}
        pg = await ctx.new_page()
        await pg.goto(URL, wait_until="networkidle")
        await pg.wait_for_function("document.querySelector('#p') && document.querySelector('#p').options.length > 1", timeout=30000)
        val = await pg.evaluate("(n)=>{const o=[...document.querySelectorAll('#p option')].find(o=>o.textContent.includes(n));return o?o.value:null}", a.pickup)
        if val:
            await pg.select_option("#p", val)
        await pg.select_option("#l", "ko")
        await pg.wait_for_timeout(700)
        marks["type"] = round(time.time() - t0, 2)
        await pg.click("#t")
        await pg.type("#t", a.say, delay=60)
        await pg.wait_for_timeout(600)
        marks["click"] = round(time.time() - t0, 2)
        await pg.click("#go")
        await pg.wait_for_function("!document.querySelector('#go').disabled && !document.querySelector('#out .wait')", timeout=95000)
        marks["done"] = round(time.time() - t0, 2)
        await pg.wait_for_timeout(2500)
        await pg.evaluate("()=>{const o=document.querySelector('#out');window.scrollTo({top:o.getBoundingClientRect().top+scrollY-12,behavior:'smooth'})}")
        await pg.wait_for_timeout(2500)
        await pg.evaluate("()=>window.scrollBy({top:260,behavior:'smooth'})")
        await pg.wait_for_timeout(3000)
        marks["end"] = round(time.time() - t0, 2)
        text = await pg.inner_text("#out")
        vid = await pg.video.path()
        await ctx.close(); await b.close()
    os.replace(vid, os.path.join(a.out, "solar_raw.webm"))
    meta = {"url": URL, "say": a.say, "pickup": a.pickup, "marks": marks, "answer": text,
            "recorded_kst": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "run": os.environ.get("RUN_URL", "")}
    json.dump(meta, open(os.path.join(a.out, "marks.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: meta[k] for k in ("marks", "recorded_kst")}, ensure_ascii=False))
    print(text[:600])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--say", required=True); ap.add_argument("--pickup", default="역곡"); ap.add_argument("--out", default="out_ask")
    asyncio.run(main(ap.parse_args()))
