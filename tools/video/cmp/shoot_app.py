#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""비교 장면 오른쪽(책이지 시연 화면)의 휴대폰 그림을 찍는다. 직원 측정(2026. 10. 27.)과 같은 순서로:
① 「눌러서 시작하기」 ② 마이크를 누르고 책 제목 말하기 ③ 「방문 안내 보기」
(받을 도서관 상동에 책이 있어 「바로 이용」 방문 안내까지. server/lab/out/apply_steps_staff_2026-10-27.md)

  python3 -m http.server 8790 --bind 127.0.0.1      # 저장소 루트에서(시연 웹을 띄움)
  python3 tools/video/cmp/shoot_app.py [http://127.0.0.1:8790/index.html]

- 바깥 주소로 나가는 요청은 모두 막는다(정보나루·중계 호출 0회). 화면은 띄운 시연 웹의 그날 새벽 자료(data/holdings-today.json)로 판정한다.
- 책은 그날 자료에서 상동에 대출 가능한 시연 도서를 고른다(불편한 편의점 먼저: 예시 단추 ②와 같은 책).
  지구 끝의 온실은 말해도 예시 장면(책바다)이라 빼고, 나미야 잡화점의 기적은 예시 단추 ①(상동 대출 중 장면)과 헷갈리지 않게 맨 뒤.
- 이 환경에는 마이크가 없어 음성 인식만 흉내 낸다(말한 글자를 낱말 단위로 차례로 넘김). 그 밖의 화면 동작은 실제 시연 웹 그대로다.
- 처음 안내는 이미 본 것으로 둔다(다시 온 이용자). 처음 온 이용자는 처음 안내의 「시작하기」가 ①의 누름을 대신한다.
- 결과: app_gate.png · app_home.png · app_listen.png · app_result.png · app_visit.png(390×790, 2배)와
  app_shots.js(찍은 날의 자료 조회일, 고른 책, 누른 곳의 좌표. compare.html이 읽음)."""
import asyncio, json, os, sys, urllib.request
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8790/index.html"
ORIGIN = "/".join(BASE.split("/")[:3])
W, H = 390, 790

snap = json.load(urllib.request.urlopen(BASE.rsplit("/", 1)[0] + "/data/holdings-today.json"))   # 띄운 시연 웹이 읽는 바로 그 파일
ASOF = snap["asof"]                                   # 예: 2026-10-30
TITLES = {"9791161571188": "불편한 편의점", "9788936434120": "소년이 온다",
          "9791195794799": "설민석의 한국사 대모험", "9788972756194": "나미야 잡화점의 기적"}
BOOK = next((t for k, t in TITLES.items() if snap["holdings"].get(k, {}).get("상동") == "ok"), None)
if not BOOK:
    sys.exit(f"{ASOF} 자료에 상동에 대출 가능한 시연 도서가 없어 「바로 이용」 흐름을 찍을 수 없습니다")

FAKE_SR = """
(() => {
  try { localStorage.setItem('chaekiji.intro', '1'); } catch (e) {}
  const SAY = %s;
  class FakeSR {
    constructor(){ this.lang = 'ko-KR'; this.interimResults = true; this.maxAlternatives = 3; this.continuous = false; }
    start(){
      const me = this, words = SAY.split(' '); let acc = '';
      setTimeout(() => me.onstart && me.onstart(), 60);
      words.forEach((w, i) => setTimeout(() => {
        acc = acc ? acc + ' ' + w : w; const row = [{transcript: acc}]; row.isFinal = false;
        me.onresult && me.onresult({results: [row]}); }, 700 + i * 700));
      setTimeout(() => { const row = [{transcript: SAY}]; row.isFinal = true; me.onresult && me.onresult({results: [row]}); },
                 700 + words.length * 700 + 1800);
    }
    stop(){} abort(){}
  }
  window.SpeechRecognition = FakeSR; window.webkitSpeechRecognition = FakeSR;
})();
""" % json.dumps(BOOK, ensure_ascii=False)


async def center(pg, sel):
    b = await pg.locator(sel).first.bounding_box()
    return [round(b["x"] + b["width"] / 2), round(b["y"] + b["height"] / 2)]


async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch()
        ctx = await br.new_context(viewport={"width": W, "height": H}, device_scale_factor=2, locale="ko-KR",
                                   has_touch=True, service_workers="block")
        outside = []
        async def guard(route):
            if route.request.url.startswith(ORIGIN):
                await route.continue_()
            else:
                outside.append(route.request.url); await route.abort()
        await ctx.route("**/*", guard)
        await ctx.add_init_script(FAKE_SR)
        pg = await ctx.new_page()
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.clock.install(time=f"{ASOF}T01:30:00Z")          # 그날 오전 10:30(한국 시각)
        await pg.goto(BASE, wait_until="load"); await pg.wait_for_timeout(1500)
        taps = {}
        g = pg.locator("#gateGo")
        if not (await g.count() and await g.is_visible()):
            sys.exit("「눌러서 시작하기」 화면이 보이지 않습니다")
        await pg.screenshot(path=f"{HERE}/app_gate.png"); taps["gate"] = await center(pg, "#gateGo")
        await g.click(); await pg.wait_for_timeout(2200)
        await pg.screenshot(path=f"{HERE}/app_home.png"); taps["mic"] = await center(pg, "#micbtn")
        await pg.locator("#micbtn").click()
        await pg.wait_for_function("(w) => { const e = document.getElementById('lst2'); return e && e.classList.contains('heard') && e.textContent.includes(w); }",
                                   arg=BOOK.split(" ")[-1], timeout=15000)
        await pg.wait_for_timeout(250)
        await pg.screenshot(path=f"{HERE}/app_listen.png")
        await pg.wait_for_selector("#s-result.on #apply", timeout=25000); await pg.wait_for_timeout(1500)
        res = await pg.evaluate("document.getElementById('s-result').innerText")
        if "바로 이용" not in res:
            sys.exit("판정이 「바로 이용」이 아닙니다: " + res[:200])
        await pg.screenshot(path=f"{HERE}/app_result.png"); taps["apply"] = await center(pg, "#apply")
        btn = (await pg.locator("#apply").inner_text()).strip()
        await pg.locator("#apply").click(); await pg.wait_for_timeout(1500)
        await pg.screenshot(path=f"{HERE}/app_visit.png")
        done = await pg.evaluate("document.getElementById('s-done').innerText")
        await br.close()
    if outside:
        print("막은 바깥 요청:", outside[:5])
    y, m, d = ASOF.split("-")
    meta = {"asof": ASOF, "asofKo": f"{int(m)}. {int(d)}.", "book": BOOK, "button": btn, "viewport": [W, H], "taps": taps}
    with open(f"{HERE}/app_shots.js", "w", encoding="utf-8") as f:
        f.write("/* shoot_app.py가 만든 값(손으로 고치지 않음) */\nwindow.APP_SHOTS = " + json.dumps(meta, ensure_ascii=False) + ";\n")
    print(json.dumps(meta, ensure_ascii=False))
    print("결과 화면:", " / ".join(res.split("\n")[:6]))
    print("방문 안내:", " / ".join(done.split("\n")[:5]))
    print("바깥 요청", len(outside), "· 오류", len(errs), errs[:2])
    if outside or errs:
        sys.exit(1)

asyncio.run(main())
