#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책이지 시연영상 녹화 — 장면을 차례로 띄우며 화면 갱신을 한 장씩 받아 적는다(1920x1080).

  python3 tools/video/record.py              # 초안(「초안 · 오늘 날짜」 표시)
  python3 tools/video/record.py --final      # 표시 없이(자리 표시 두 곳에 실제 녹화가 들어간 뒤)
  python3 tools/video/build_video.py         # → out/[시연영상]_부천시_책이지(_초안).mp4 · .srt · 구성표.md

무엇을 보이나
- 명령 창 장면: 실제로 돌린 명령의 출력(t1~t4.txt)을 그대로 다시 보인다. 화면에 「실제 실행 결과(기록 재생)」라고 적힌다.
  t1~t3은 server/lab/consult_cli.py, t4는 sh server/run.sh의 출력(capture.sh로 다시 받는다).
- 시연 웹 장면: 저장소의 index.html을 별도 브라우저 창(390x790)에 실제로 띄워 조작하고, 그 화면을 휴대폰 틀에 그대로 비춘다.
  (화면 속 화면(iframe)에 넣으면 시연 웹이 「미리보기 화면 안에서는 마이크가 막혀 있습니다」를 띄우므로 따로 띄운다.)
  중계 주소(workers.dev)는 막는다 — 시연 웹은 저장소의 자료로 동작한다.
- 담당자가 녹화한 화면(claude.ai 커넥터, 코랩 실행)은 clips/claude.webm · clips/colab.webm이 있으면 그 자리에서 재생하고,
  없으면 「자리 표시(초안)」 카드를 둔다. 자막은 clips/<이름>.json(README 참고).

필요: pip install playwright(Chromium 포함) · ffmpeg · 글꼴(fetch_fonts.sh)."""
import sys, os, re, asyncio, threading, http.server, socketserver, functools, time, socket, json, base64, argparse, datetime
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ap = argparse.ArgumentParser()
ap.add_argument("--out", default=os.path.join(HERE, "rec"))
ap.add_argument("--final", action="store_true", help="「초안」 표시를 뺀다")
ap.add_argument("--badge", default=None, help="오른쪽 위 표시 글(기본: 초안 · 오늘 날짜)")
ap.add_argument("--port", type=int, default=8805)
A = ap.parse_args()
KST = datetime.timezone(datetime.timedelta(hours=9))
TODAY = datetime.datetime.now(KST)
BADGE = A.badge or f"초안 · {TODAY.year}. {TODAY.month}. {TODAY.day}."
FR = os.path.join(A.out, "frames"); os.makedirs(FR, exist_ok=True)
for f in os.listdir(FR):
    os.remove(os.path.join(FR, f))
PORT, SC = A.port, 1.5
for need in ["fonts/Pretendard-Regular.otf", "fonts/D2Coding-Regular.ttf"]:
    if not os.path.exists(os.path.join(HERE, need)):
        sys.exit(f"글꼴이 없습니다: tools/video/{need} — 먼저 sh tools/video/fetch_fonts.sh")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass


def serve():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), functools.partial(Quiet, directory=ROOT)) as h:
        h.serve_forever()


threading.Thread(target=serve, daemon=True).start()
for _ in range(50):
    try:
        socket.create_connection(("127.0.0.1", PORT), timeout=0.2).close(); break
    except OSError:
        time.sleep(0.1)

rd = lambda n: open(os.path.join(HERE, n), encoding="utf-8").read().rstrip("\n").split("\n")
T1, T2, T3, T4 = rd("t1.txt"), rd("t2.txt"), rd("t3.txt"), rd("t4.txt")
CUES, MARKS, FRAMES = [], [], []
BASE = f"http://127.0.0.1:{PORT}"
APP_URL = BASE + "/index.html"
EASE = """([y,ms])=>new Promise(r=>{const el=document.getElementById('body')||document.scrollingElement;const y0=el.scrollTop;const t0=performance.now();
 const step=t=>{const k=Math.min(1,(t-t0)/ms);const e=k<.5?2*k*k:1-Math.pow(-2*k+2,2)/2;el.scrollTop=y0+(y-y0)*e;if(k<1)requestAnimationFrame(step);else r();};requestAnimationFrame(step);})"""
plain = lambda s: re.sub(r"<[^>]+>", "", s)


def clip_meta(name):
    v = os.path.join(HERE, "clips", name + ".webm")
    if not os.path.exists(v):
        return None
    j = os.path.join(HERE, "clips", name + ".json")
    m = json.load(open(j, encoding="utf-8")) if os.path.exists(j) else {}
    m["src"] = f"/tools/video/clips/{name}.webm"
    return m


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1, locale="ko-KR")
        page = await ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append("composer: " + str(e)))
        W = page.wait_for_timeout
        await page.goto(f"{BASE}/tools/video/composer.html?s={SC}", wait_until="load")
        await page.evaluate("document.fonts.ready")
        await W(400)

        actx = await b.new_context(viewport={"width": 390, "height": 790}, device_scale_factor=1.2, locale="ko-KR",
                                   has_touch=True, service_workers="block")
        await actx.route("**/*workers.dev*", lambda r: r.abort())
        app = await actx.new_page()
        app.on("pageerror", lambda e: errs.append("app: " + str(e)))

        cdp = await ctx.new_cdp_session(page)
        acdp = await actx.new_cdp_session(app)
        n = [0]

        def on_frame(prm):
            n[0] += 1
            fn = os.path.join(FR, f"{n[0]:06d}.jpg")
            with open(fn, "wb") as f:
                f.write(base64.b64decode(prm["data"]))
            ts = (prm.get("metadata") or {}).get("timestamp") or time.time()
            FRAMES.append((ts, time.time(), fn))
            asyncio.ensure_future(cdp.send("Page.screencastFrameAck", {"sessionId": prm["sessionId"]}))

        def on_app_frame(prm):
            asyncio.ensure_future(page.evaluate("d=>appFrame(d)", prm["data"]))
            asyncio.ensure_future(acdp.send("Page.screencastFrameAck", {"sessionId": prm["sessionId"]}))

        cdp.on("Page.screencastFrame", on_frame)
        acdp.on("Page.screencastFrame", on_app_frame)
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": 1920, "maxHeight": 1080, "everyNthFrame": 1})
        await W(600)

        t0 = time.time()
        now = lambda: round(time.time() - t0, 2)

        def mark(name, screen=""):
            MARKS.append((now(), name, screen)); print(f"{MARKS[-1][0]:6.1f}s  {name}", flush=True)

        def cue(*parts):
            CUES.append((now(), [plain(x) for x in parts if x]))

        async def ev(js): await page.evaluate(js)

        async def crumb(html): await page.evaluate("h=>crumb(h)", html)

        async def bar(text, small=""):
            cue(text, small)
            await page.evaluate("([t,s])=>bar(t,s)", [text, small])

        async def side(k, h, s, n_=""):
            cue(h.replace("\n", " "), s, n_)
            await page.evaluate("([k,h,s,n])=>sideFade(k,h,s,n)", [k, h, s, n_])

        async def card(k, t, s, items):
            await page.evaluate("([k,t,s,l])=>{card(k,t,s,l);only('card')}", [k, t, s, items])
            cue(t.replace("\n", " "), s.replace("\n", " · ") if s else "")

        async def lines(items, each, tail, first=0):
            await W(first)
            for i, x in enumerate(items):
                await ev(f"cardLine({i})"); cue(x); await W(each)
            await W(tail)

        async def slot(t, s):
            await page.evaluate("([t,s])=>{slot(t,s);only('slot')}", [t, s])
            cue("[자리 표시] " + t.replace("\n", " "), s.replace("\n", " "))

        async def play_clip(m):
            dur = await page.evaluate("([s,t,g])=>clipLoad(s,t,g)", [m["src"], m.get("title", ""), m.get("tag", "실제 화면 녹화")])
            caps = m.get("caps") or []
            if caps:
                await bar(caps[0][1], caps[0][2] if len(caps[0]) > 2 else "")
                await ev("only('clip','bar')")
            else:
                await ev("only('clip')")
            await W(600)
            done = asyncio.ensure_future(page.evaluate("clipPlay()"))
            ts = time.time()
            for c in caps[1:]:
                d = c[0] - (time.time() - ts)
                if d > 0:
                    await asyncio.sleep(d)
                await bar(c[1], c[2] if len(c) > 2 else "")
            await done
            await W(500)
            return dur

        await ev(f"draft({'false' if A.final else 'true'}, {json.dumps(BADGE, ensure_ascii=False)})")
        # ── 1. 제목 ──
        mark("1 제목", "제목 카드")
        await crumb("")
        await card("경기도 부천시 상동도서관 · 2026 공공 AI 대전환 챌린지 세션1", "책이지 — 상호대차 상담 비서",
                   "도서관 상호대차 절차를 대신하는 AI 에이전트\n시연영상(구동안내서의 흐름 1~3 순서)", [])
        await W(7000)

        # ── 2. 왜 ──
        mark("2 왜 만들었나", "문제 카드 — 세 줄이 차례로")
        await crumb("<b>책이지</b> · 왜 만들었나")
        L = ["창구와 전화에서 하루에도 여러 번 되풀이되는 질문입니다",
             "사서는 16개 도서관의 소장·대출 상태와 상호대차 규정 7가지를 하나씩 확인해 답합니다",
             "시민이 직접 하려면 누리집 화면을 아홉 번 넘기고 규정도 스스로 맞춰야 합니다"]
        await card("왜 만들었나", "「그 책 있어요?\n여기서 받을 수 있어요?」", "", L)
        await lines(L, 4600, 1500, first=1500)

        # ── 3. 어떻게 ──
        mark("3 어떻게 푸나", "흐름도 네 칸 — 이용자의 말, 모델, 책이지 도구(MCP), 결과")
        await crumb("<b>책이지</b> · 어떻게 푸나")
        await ev("fhead('어떻게 푸나','말은 AI가 알아듣고, 판정은 규칙이 합니다'); bar('',''); only('fh','flow')")
        await ev("""flow([{h:'이용자의 말',d:'「나미야 잡화점의 기적 빌리고 싶어요, 상동에서 받을게요」'},
                         {h:'모델',d:'Claude · 엑사원 · 라마<br>말을 알아듣고<br>도구를 부름'},
                         {h:'책이지 도구(MCP)',d:'책 찾기<br>16개관 소장·대출<br>(정보나루)<br>규정 7종',cls:'tool'},
                         {h:'결과',d:'판정<br>이용자 안내문<br>접수 메모<br>(접수는 사서가)'}])""")
        cue("말은 AI가 알아듣고, 판정은 규칙이 합니다")
        await W(900)
        steps = ["이용자의 말: 「나미야 잡화점의 기적 빌리고 싶어요, 상동에서 받을게요」",
                 "모델(Claude · 엑사원 · 라마): 말을 알아듣고 도구를 부름",
                 "책이지 도구(MCP): 책 찾기 · 16개관 소장·대출(정보나루) · 규정 7종",
                 "결과: 판정 · 이용자 안내문 · 접수 메모(접수는 사서가)"]
        for i in range(4):
            await ev(f"flowStep({i})"); cue(steps[i]); await W(1800)
        await ev("only('fh','flow','bar')")
        await bar("모델을 바꿔도 판정은 같습니다", "MCP는 AI 모델이 외부 도구를 부르는 공통 규격입니다 · 접수는 사서가 현행 시스템에서 합니다")
        await W(8200)

        # ── 4. 흐름 1 소개 ──
        mark("4 흐름 1 소개", "연결 방법 카드 — 세 줄")
        await crumb("<b>흐름 1</b> / 3 · 창구·전화 상담(주 결과물)")
        L = ["claude.ai 설정의 커넥터에서 「커스텀 커넥터 추가」",
             "주소 <b>chaekiji-relay.altarry2.workers.dev/mcp</b> 입력, 인증키는 필요 없습니다",
             "새 대화에서 커넥터를 켜고, 이용자의 말을 그대로 넣습니다"]
        await card("흐름 1 · 창구·전화 상담", "claude.ai에 주소 한 줄이면\n설치 없이 씁니다", "", L)
        await lines(L, 3100, 2200, first=1200)

        # ── 5. claude.ai 실제 화면(담당자 녹화) 또는 자리 표시 ──
        m = clip_meta("claude")
        if m:
            mark("5 claude.ai 실제 화면", "담당자가 녹화한 claude.ai 화면(커넥터 켜기 → 문의 → 도구 호출 → 답)")
            await play_clip(m)
        else:
            mark("5 자리 표시(claude.ai)", "자리 표시 카드 — claude.ai 실제 화면(30초)이 들어갈 곳")
            await slot("claude.ai에서 같은 문의를 넣는\n실제 화면(30초)",
                       "담당자가 10. 19. 직접 녹화해 이 자리에 넣습니다\n이어서 같은 도구를 PC에서 직접 부른 실제 결과를 보입니다")
            await W(7000)

        # ── 6. 명령 창 1: 나미야 ──
        mark("6 명령 창 1(나미야)", "명령 창(기록 재생) — 판정·근거 → 안내문·링크 → 접수 메모를 차례로 강조")
        await crumb("<b>흐름 1</b> / 3 · 같은 도구를 PC에서 직접 부르기")
        await ev("term('명령 창 · 상담 비서 도구를 한 번 부르기(server/lab/consult_cli.py)'); only('term','bar')")
        await bar("모델 없이 도구만 불러 봅니다", "claude.ai가 부르는 것과 같은 도구(consult_request)입니다")
        await W(1300)
        await ev("termComment('이 PC는 중계에 닿지 않아 오늘 새벽 자료로 실행(원격 판도 이 책은 같은 자료로 답함)')")
        await W(1000)
        await page.evaluate("t=>termType(t,24)", 'CHAEKIJI_MODE=snapshot python lab/consult_cli.py "나미야 잡화점의 기적 빌리고 싶어요" 상동')
        await W(500)
        await page.evaluate("l=>termOut(l,120)", T1)
        await W(900)
        await ev("termFocus(['◀ 판정','◀ 근거'])")
        await bar("판정: 관내 상호대차", "상동은 대출 중, 꿈여울 등 7곳은 대출 가능 · 정보나루 2026. 10. 16. 조회(전일 기준)")
        await W(9000)
        await ev("termFocus(['◀ 안내문','◀ 링크'])")
        await bar("이용자에게 읽어 줄 안내문", "조회일과 공식 누리집의 그 책 화면 주소가 붙습니다")
        await W(10000)
        await ev("termFocus(['◀ 접수 메모','   도서:','   갈래:','   수령관:','   대출 가능 관:','   근거:','   규정:','   접수:'])")
        await bar("사서가 옮겨 적는 접수 메모", "규정 2건 통과 · 5건 창구 확인 · 접수는 창구에서 사서가 합니다")
        await W(9500)

        # ── 7. 명령 창 2: 소년이 온다 ──
        mark("7 명령 창 2(바로 이용)", "명령 창(기록 재생) — 소년이 온다 · 꿈빛 → 바로 이용")
        await ev("term('명령 창 · 받을 도서관을 바꿔서'); only('term','bar')")
        await bar("받을 도서관 서가에 있으면", "상호대차 대신 「바로 이용」으로 안내합니다")
        await W(700)
        await page.evaluate("t=>termType(t,26)", 'CHAEKIJI_MODE=snapshot python lab/consult_cli.py "소년이 온다" 꿈빛')
        await W(400)
        await page.evaluate("l=>termOut(l,95)", T2)
        await W(600)
        await ev("termFocus(['◀ 판정','   수령관:'])")
        await W(9500)

        # ── 8. 명령 창 3: 정보나루가 끊긴 날 ──
        mark("8 명령 창 3(조회 불가)", "명령 창(기록 재생) — 중계를 일부러 끊고 채식주의자 → 소장 확인 불가")
        await ev("term('명령 창 · 정보나루에 닿지 못한 날'); only('term','bar')")
        await bar("자료에 닿지 못하면 「없다」고 하지 않습니다", "「창구에서 조회」로 넘깁니다(v0.3.5에서 고침)")
        await W(700)
        await ev("termComment('중계가 끊긴 상황을 일부러 만듦(닿지 않는 주소)')")
        await W(800)
        await page.evaluate("t=>termType(t,22)", 'CHAEKIJI_MODE=relay CHAEKIJI_RELAY=http://127.0.0.1:9 python lab/consult_cli.py "채식주의자 있나요?" 상동')
        await W(400)
        await page.evaluate("l=>termOut(l,130)", T3)
        await W(600)
        await ev("termFocus(['◀ 판정','◀ 안내문'],120)")
        await W(9500)

        # ── 9. 흐름 2: 공개 모델 ──
        mark("9 흐름 2", "코랩 카드 — 세 줄")
        await crumb("<b>흐름 2</b> / 3 · 같은 상담을 공개 모델로")
        L = ["Ollama + <b>엑사원 3.5 2.4B</b> · <b>라마 3.2 3B</b>(공고에 나온 공통기반 지원 계열)",
             "같은 지시문 · 같은 문의 5건 · 같은 도구(consult_request)",
             "기록표에 문의별 판정·걸린 시간·실패까지 그대로 남깁니다"]
        await card("흐름 2 · 모델을 바꿔도 같은 판정", "같은 상담을 공개 모델로\n코랩 「모두 실행」 한 번", "", L)
        await app.goto(APP_URL, wait_until="load")       # 다음 장면에 쓸 시연 웹을 미리 띄워 둔다(보이지 않는 동안)
        await lines(L, 3100, 1800, first=1100)
        m = clip_meta("colab")
        if m:
            mark("9 코랩 실제 화면", "담당자가 녹화한 코랩 실행 화면과 기록표")
            await play_clip(m)
            await acdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90, "maxWidth": 468, "maxHeight": 948, "everyNthFrame": 1})
            await W(1200)
        else:
            mark("9 자리 표시(코랩)", "자리 표시 카드 — 코랩 실행 화면과 기록표가 들어갈 곳")
            await slot("코랩 실행 화면과 기록표",
                       "10. 19. 실행 뒤 이 자리에 넣습니다\n지금까지는 가짜 Ollama로 두 방식(도구 호출·JSON) 시험 6건만 통과했습니다")
            await acdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90, "maxWidth": 468, "maxHeight": 948, "everyNthFrame": 1})
            await W(7000)

        # ── 10. 흐름 3: 시민 음성 화면 ──
        mark("10 흐름 3 시작", "왼쪽 설명 + 오른쪽 휴대폰(시연 웹 실제 조작)")
        await crumb("<b>흐름 3</b> / 3 · 시민 음성 화면(2027 시범 운영 제안)")
        await ev("side('','','',''); only('side','phone')")
        await W(1200)
        rect = await page.evaluate("(()=>{const r=document.getElementById('appimg').getBoundingClientRect();return [r.left,r.top,r.width,r.height]})()")
        vw, vh = 390, 790

        async def tapclick(loc):
            await loc.scroll_into_view_if_needed(timeout=5000)
            await W(350)
            bb = await loc.bounding_box()
            if bb:
                x = (rect[0] + (bb['x'] + bb['width'] / 2) * rect[2] / vw) / SC
                y = (rect[1] + (bb['y'] + bb['height'] / 2) * rect[3] / vh) / SC
                await page.evaluate(f"tap({x},{y})")
                await W(420)
            await loc.click(timeout=5000)

        async def scroll_to(y, ms=900):
            # 시연 웹은 창 전체가 아니라 본문 상자(#body)가 굴러간다. 화면 갱신이 끊기지 않게 프레임마다 조금씩 굴린다
            await app.evaluate(EASE, [y, int(ms * 0.85)])
            await W(int(ms * 0.15))

        await side("흐름 3 · 시민 음성 화면", "같은 판정을 시민이 직접\n(2027 시범 운영 제안)",
                   "휴대폰 인터넷 창에서 열고 「눌러서 시작하기」를 누릅니다. 예시 단추로 음성 없이도 흐름을 볼 수 있습니다.",
                   "시연 웹 altarry-prog.github.io/chaekiji")
        await W(4600)
        try:
            g = app.locator("#gateGo")
            if await g.count() and await g.is_visible():
                await tapclick(g); await W(1500)
        except Exception as e:
            print("gate skipped", e)
        mark("10 판정", "예시 ② 누름 → 처리 단계 → 판정 화면, 아래로 굴려 다른 분관까지")
        await tapclick(app.locator("text=나미야 잡화점의 기적 빌리고 싶어요").first)
        await side("판정", "상동은 대출 중이라\n다른 분관에서 보내 드립니다",
                   "이 예시 단추는 2026. 8. 18. 실측 장면입니다. 직접 말하거나 입력하면 오늘 새벽 자료로 찾습니다.",
                   "대출 상태는 정보나루 전일 기준")
        await W(7000)
        for y in (200, 400):
            await scroll_to(y, 1500)
        await W(1200)
        await scroll_to(0, 1200)
        mark("10 신청 확인", "「상호대차 신청」 → 확인 시트")
        await tapclick(app.locator("#apply"))
        await side("신청 확인", "대출관 · 수령관 · 소요 ·\n수령 기한 · 미수령 제한",
                   "화면을 읽어 주고, 「네」 한마디나 단추 한 번으로 확인합니다.", "※ 시연이며 실제 접수로 이어지지 않습니다")
        await W(6800)
        mark("10 접수(시연)", "「네, 신청합니다」 → 접수(시연) 화면, 「책이지가 대신 한 일」까지 굴림")
        try:
            await tapclick(app.locator("#confirm")); await W(1300)
        except Exception as e:
            print("confirm skipped", e)
        await side("접수(시연)", "책이지가 대신 한 일을\n한 화면에",
                   "말을 글로 옮기고, 책을 확정하고, 16개관을 확인하고, 규정 7종을 본 뒤 접수까지 이어 줍니다. 이용자는 말 한마디, 확인 한 번입니다.",
                   "※ 시연이며 실제 접수로 이어지지 않습니다")
        await W(3600)
        await scroll_to(150, 1600)
        await W(3400)
        mark("10 누구나", "처음 화면 → 큰글자 → 언어 선택(베트남어)")
        await ev("cover(true)"); await W(600)
        await app.goto(APP_URL + "?r=2", wait_until="load"); await W(900)
        await ev("cover(false)"); await W(400)
        await side("누구나", "큰글자 · 10개 언어 ·\n전화 한 통 모드",
                   "어르신, 외국인 주민, 시각이 불편한 분도 같은 흐름으로 씁니다.",
                   "음성 인식은 기기·브라우저가 지원하는 언어만 되고, 그 밖은 글자로 입력합니다")
        await W(1300)
        try:
            g = app.locator("#gateNo")
            if await g.count() and await g.is_visible():
                await tapclick(g); await W(700)
        except Exception as e:
            print("gateNo skipped", e)
        try:
            await tapclick(app.locator("#bigbtn")); await W(3400)
        except Exception as e:
            print("big skipped", e)
        try:
            await tapclick(app.locator("#langbtn")); await W(1700)
            vi = app.locator("text=Tiếng Việt").first
            if await vi.count():
                await tapclick(vi); await W(3800)
        except Exception as e:
            print("lang skipped", e)
        await W(1500)
        await acdp.send("Page.stopScreencast")

        # ── 11. 명령 창 4: 설치형 ──
        mark("11 설치형", "명령 창(기록 재생) — sh server/run.sh → 「준비 완료 — 시험 85건」")
        await crumb("<b>설치형</b> · 명령 한 줄로 준비·시험")
        await ev("term('명령 창 · 설치형 참조 서버 준비·시험(Windows는 server\\\\run.bat을 두 번 누르기)'); only('term','bar')")
        await bar("설치형: 명령 한 줄로 자동 시험 85건", "인증키·네트워크 없이 돌아갑니다(처음 한 번만 PyYAML 설치)")
        await W(700)
        await page.evaluate("t=>termType(t,45)", "sh server/run.sh")
        await W(300)
        await page.evaluate("l=>termOut(l,90,x=>x.includes('✓')?'ok':(x.startsWith('[chaekiji-mcp]')?'c':''))", T4)
        await W(500)
        await ev("termFocus(['준비 완료'],300)")
        cue("준비 완료 — 시험 85건")
        await W(5000)

        # ── 12. 어디까지 진짜인가 ──
        mark("12 어디까지 진짜인가", "정직 카드 — 네 줄")
        await crumb("<b>책이지</b> · 어디까지 진짜인가")
        L = ["<b>지금</b> 사서가 창구·전화에서 쓰는 판정 도구입니다. 접수는 현행 시스템에서 합니다",
             "<b>다음(2027 시범)</b> 시민 음성 화면, 도서관리시스템과 연결해 접수까지",
             "<b>다른 도시</b> 설정 파일 하나로 적용합니다(정보나루는 전국 공통 자료)",
             "<b>정직 고지</b> 대출 상태는 정보나루 전일 기준이고, 시연 웹의 신청은 실제 접수가 아닙니다"]
        await card("어디까지 진짜인가", "판정까지는 지금, 접수는 연동 뒤", "", L)
        await lines([re.sub(r"<b>(.*?)</b> ", r"\1: ", x) for x in L], 3700, 1600, first=1100)

        # ── 13. 끝 ──
        mark("13 끝", "끝 카드 — 주소·팀")
        await crumb("")
        await card("책이지 · 상호대차 상담 비서", "말 한마디로 내 손안에 책이",
                   "시연 웹 altarry-prog.github.io/chaekiji\n소스 공공 GitLab(참가신청서의 링크) · github.com/altarry-prog/chaekiji\n팀 책이지 · 경기도 부천시 상동도서관", [])
        await W(8000)
        t_end = now(); mark("종료")
        await W(300)
        await cdp.send("Page.stopScreencast")
        await W(300)
        await actx.close(); await ctx.close(); await b.close()
        json.dump({"t0": t0, "end": t_end, "badge": None if A.final else BADGE, "cues": CUES, "marks": MARKS, "errors": errs,
                   "frames": [(a, c, os.path.basename(f)) for a, c, f in FRAMES]},
                  open(os.path.join(A.out, "captions.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        print("frames", len(FRAMES), "cues", len(CUES), "errors", errs[:3])

asyncio.run(main())
