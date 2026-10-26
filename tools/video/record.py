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
ap.add_argument("--mute", action="store_true", help="내레이션 없이(자막만)")
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
META = json.load(open(os.path.join(HERE, "t_meta.json"), encoding="utf-8"))   # capture.py — 찍은 날 고른 책·판정·조회일·시험 수
# 장면별 내레이션(tts.yml이 만든 mp3와 길이) — 파일 이름 앞 두 자리가 장면 번호
NARR_DIR = os.path.join(HERE, "narration", "audio", "script")
NARR, NARR_EV, NARR_LEAD = {}, [], 0.4
try:
    for it in json.load(open(os.path.join(NARR_DIR, "기록.json"), encoding="utf-8"))["items"]:
        NARR[it["file"][:2]] = (it["file"], float(it["seconds"]))
except (OSError, ValueError, KeyError):
    pass
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
        scene_t = {}

        def scene(key, name, screen=""):
            # 장면 시작 — 내레이션이 있으면 이 시각(+NARR_LEAD)에 그 장면 음성을 얹는다(build_video.py)
            mark(name, screen); scene_t[key] = time.time()
            if key in NARR and not A.mute:
                NARR_EV.append((round(now() + NARR_LEAD, 2), NARR[key][0], NARR[key][1]))

        async def hold(key, pad=0.5):
            # 내레이션이 다 끝날 때까지 장면을 붙잡아 둔다(음성이 다음 장면으로 넘치지 않게)
            if key not in NARR or A.mute:
                return
            need = NARR_LEAD + NARR[key][1] + pad - (time.time() - scene_t[key])
            if need > 0:
                await W(int(need * 1000))

        def share(key, fracs, mins):
            # 내레이션 길이를 장면 안의 카드들에 나눠 준다(내레이션이 없으면 mins 그대로)
            n = NARR.get(key, (None, 0))[1] if not A.mute else 0
            return [int(max(m, f * n) * 1000) for f, m in zip(fracs, mins)]

        # ── 0. 첫 화면: claude.ai 실제 화면(창구 질문을 그대로) ──
        m = clip_meta("claude")
        scene("00", "0 첫 화면(claude.ai 실제 화면)", "2026. 10. 20. 크롬 실제 화면 캡처 20초 — 창구 질문을 그대로 넣고 판정·안내문이 나오기까지(기다린 약 50초는 빨리 감음)")
        await crumb("<b>책이지</b> · 창구에서 받는 질문을 그대로")
        if m:
            await play_clip(m)
        else:
            await slot("claude.ai에서 같은 문의를 넣는\n실제 화면(20초)", "clips/claude.webm이 없어 자리 표시를 둡니다")
            await W(6000)
        await hold("00")

        # ── 1. 제목 · 왜 ──
        scene("01", "1 제목·왜 만들었나", "제목 카드 → 상호대차 카드 두 장(정의·부천 규모, 신청 전 세 가지 확인)")
        await crumb("")
        w1, w2, w3 = share("01", [0.30, 0.42, 0.28], [5.5, 6.5, 5.0])
        await card("경기도 부천시 상동도서관 · 2026 공공 AI 대전환 챌린지 세션1", "책이지 — 상호대차 상담 비서",
                   "도서관 상호대차 상담을 돕는 AI 에이전트\n검색 도구가 아니라 신청 요건을 판정·안내하는 상담 비서", [])
        await W(w1)
        await crumb("<b>책이지</b> · 왜 만들었나")
        # [10/19 담당자 승인 카드를 두 장으로 — 10/26 입상 분석 5-2] 정의·운영실적(2025. 12.)·만족도(2025. 11. 조사, 586/607)
        await card("왜 만들었나", "상호대차 서비스 · 부천시립도서관 44개소",
                   "다른 도서관의 책을 가까운 도서관에서 빌려 보는 서비스\n2025년 한 해 320,140권 제공 · 이용자 만족도 96.5%", [])
        await W(w2)
        await card("왜 만들었나", "신청 전에는 세 가지 확인이 필요합니다", "자료 확인 · 소장·대출 확인 · 신청 요건 확인", [])
        await W(w3)
        await hold("01")

        # ── 2. 어떻게 ──
        scene("02", "2 어떻게 푸나", "흐름도 네 칸 — 이용자의 말, 모델, 책이지 도구(MCP), 결과")
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
            await ev(f"flowStep({i})"); cue(steps[i]); await W(2000)
        await ev("only('fh','flow','bar')")
        await bar("도구를 제대로 부르면, 모델을 바꿔도 판정은 같습니다",
                  "MCP는 AI 모델이 외부 도구를 부르는 공통 규격입니다 · 대출 상태는 정보나루 전일 기준 · 접수는 사서가 현행 시스템에서 합니다")
        await W(5000)
        await hold("02")

        # ── 3. 흐름 1 소개 ──
        scene("03", "3 흐름 1 소개", "연결 방법 카드 — 세 줄")
        await crumb("<b>흐름 1</b> / 3 · 창구·전화 상담(주 결과물)")
        L = ["claude.ai 「사용자 정의 → 커넥터」에서 「커스텀 커넥터 추가」",
             "주소 <b>chaekiji-relay.altarry2.workers.dev/mcp</b> 입력, 인증은 「로그인 없음」",
             "새 대화에서 커넥터를 켜고, 이용자의 말을 그대로 넣습니다"]
        await card("흐름 1 · 창구·전화 상담", "claude.ai에 주소 한 줄이면\n설치 없이 씁니다", "", L)
        await lines(L, 3000, 1200, first=1000)
        await hold("03")

        # ── 5. 명령 창 1: 관내 상호대차(찍는 날 자료로 고른 책 — capture.py) ──
        A1 = META["t1"]
        here1 = "대출 중" if re.search(r"수령관: 상동 \(현재 대출 중\)", "\n".join(T1)) else "없음"
        rule1 = re.search(r"규정: (\d+)건 통과 · (\d+)건 불가 · (\d+)건 창구 확인", "\n".join(T1))
        scene("05", "5 명령 창 1(관내 상호대차)", f"명령 창(기록 재생) — {A1['title']} · 상동 → 판정·근거 → 안내문·링크 → 접수 메모를 차례로 강조")
        await crumb("<b>흐름 1</b> / 3 · 같은 도구를 PC에서 직접 부르기")
        await ev("term('명령 창 · 상담 비서 도구를 한 번 부르기(server/lab/consult_cli.py)'); only('term','bar')")
        await bar("모델 없이 도구만 불러 봅니다", "claude.ai가 부르는 것과 같은 도구(consult_request)입니다")
        await W(1200)
        await ev("termComment('이 PC는 중계에 닿지 않아 오늘 새벽 자료로 실행(원격 판도 이 책은 같은 자료로 답함)')")
        await W(900)
        await page.evaluate("t=>termType(t,24)", f'CHAEKIJI_MODE=snapshot python lab/consult_cli.py "{A1["utterance"]}" 상동')
        await W(400)
        await page.evaluate("l=>termOut(l,110)", T1)
        await W(700)
        await ev("termFocus(['◀ 판정','◀ 근거'])")
        await bar(f"판정: {A1['route']}",
                  f"상동은 {here1}, {A1['available'][0]} 등 {len(A1['available'])}곳은 대출 가능 · 정보나루 {A1['asof']} 조회(전일 기준)")
        await W(7500)
        await ev("termFocus(['◀ 안내문','◀ 링크'])")
        await bar("이용자에게 읽어 줄 안내문", "조회일과 공식 누리집의 그 책 화면 주소가 붙습니다")
        await W(8000)
        await ev("termFocus(['◀ 접수 메모','   도서:','   갈래:','   수령관:','   대출 가능 관:','   근거:','   규정:','   접수:'])")
        rtxt = f"규정 {rule1.group(1)}건 통과 · {rule1.group(3)}건 창구 확인" if rule1 else "규정 확인"
        await bar("사서가 옮겨 적는 접수 메모", f"{rtxt} · 접수는 창구에서 사서가 합니다")
        await W(6500)
        await hold("05")

        # ── 6. 명령 창 2: 바로 이용 ──
        A2 = META["t2"]
        scene("06", "6 명령 창 2(바로 이용)", f"명령 창(기록 재생) — {A2['title']} · 상동 → 바로 이용")
        await ev("term('명령 창 · 다른 책으로'); only('term','bar')")
        await bar("받을 도서관 서가에 있으면", "상호대차 대신 「바로 이용」으로 안내합니다")
        await W(600)
        await page.evaluate("t=>termType(t,26)", f'CHAEKIJI_MODE=snapshot python lab/consult_cli.py "{A2["utterance"]}" 상동')
        await W(400)
        await page.evaluate("l=>termOut(l,90)", T2)
        await W(500)
        await ev("termFocus(['◀ 판정','   수령관:'])")
        await W(4500)
        await hold("06")

        # ── 7. 명령 창 3: 정보나루가 끊긴 날 ──
        scene("07", "7 명령 창 3(조회 불가)", "명령 창(기록 재생) — 중계를 일부러 끊고 채식주의자 → 소장 확인 불가")
        await ev("term('명령 창 · 정보나루에 닿지 못한 날'); only('term','bar')")
        await bar("자료에 닿지 못하면 「없다」고 하지 않습니다", "「창구에서 조회」로 넘깁니다(v0.3.5에서 고침)")
        await W(600)
        await ev("termComment('중계가 끊긴 상황을 일부러 만듦(닿지 않는 주소)')")
        await W(700)
        await page.evaluate("t=>termType(t,22)", 'CHAEKIJI_MODE=relay CHAEKIJI_RELAY=http://127.0.0.1:9 python lab/consult_cli.py "채식주의자 있나요?" 상동')
        await W(400)
        await page.evaluate("l=>termOut(l,120)", T3)
        await W(500)
        await ev("termFocus(['◀ 판정','◀ 안내문'],120)")
        await W(4800)
        await hold("07")

        # ── 8. 흐름 2: 공개 모델 — 저장소의 실측 기록표 ──
        scene("08", "8 흐름 2(공개 모델)", "코랩 카드 → 저장소의 공개 모델 실측 기록표(2026. 10. 18. 깃허브 액션 실행, 글은 원문 그대로)")
        await crumb("<b>흐름 2</b> / 3 · 같은 상담을 공개 모델로")
        L = ["Ollama + <b>엑사원 3.5 2.4B</b> · <b>라마 3.2 3B</b>(공고에 나온 공통기반 지원 계열)",
             "같은 지시문 · 같은 문의 5건 · 같은 도구(consult_request)",
             "기록표에 문의별 판정·걸린 시간·실패까지 그대로 남깁니다"]
        await card("흐름 2 · 같은 상담을 공개 모델로", "같은 상담을 공개 모델로\n코랩 「모두 실행」 한 번", "", L)
        await app.goto(APP_URL, wait_until="load")       # 다음 장면에 쓸 시연 웹을 미리 띄워 둔다(보이지 않는 동안)
        await lines(L, 2100, 500, first=800)
        m = clip_meta("model2")
        if m:
            await play_clip(m)
        else:
            await slot("공개 모델 실측 기록표", "clips/model2.webm이 없습니다 — make_record_clip.py")
            await W(5000)
        await acdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90, "maxWidth": 468, "maxHeight": 948, "everyNthFrame": 1})
        await hold("08", pad=0.3)

        # ── 9. 흐름 3: 시민 음성 화면 ──
        scene("09", "9 흐름 3 시작", "왼쪽 설명 + 오른쪽 휴대폰(시연 웹 실제 조작)")
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
        await W(3800)
        try:
            g = app.locator("#gateGo")
            if await g.count() and await g.is_visible():
                await tapclick(g); await W(1500)
        except Exception as e:
            print("gate skipped", e)
        mark("9 판정", "예시 ② 누름 → 처리 단계 → 판정 화면, 아래로 굴려 다른 분관까지")
        await tapclick(app.locator("text=나미야 잡화점의 기적 빌리고 싶어요").first)
        await side("판정", "상동은 대출 중이라\n다른 분관에서 보내 드립니다",
                   "이 예시 단추는 2026. 8. 18. 실측 장면입니다. 직접 말하거나 입력하면 오늘 새벽 자료로 찾습니다.",
                   "대출 상태는 정보나루 전일 기준")
        await W(6000)
        for y in (200, 400):
            await scroll_to(y, 1500)
        await W(1200)
        await scroll_to(0, 1200)
        mark("9 신청 확인", "「상호대차 신청」 → 확인 시트")
        await tapclick(app.locator("#apply"))
        await side("신청 확인", "대출관 · 수령관 · 소요 ·\n수령 기한 · 미수령 제한",
                   "화면을 읽어 주고, 「네」 한마디나 단추 한 번으로 확인합니다.", "※ 시연이며 실제 접수로 이어지지 않습니다")
        await W(6000)
        mark("9 접수(시연)", "「네, 신청합니다」 → 접수(시연) 화면, 「책이지가 대신 한 일」까지 굴림")
        try:
            await tapclick(app.locator("#confirm")); await W(1300)
        except Exception as e:
            print("confirm skipped", e)
        await side("접수(시연)", "책이지가 대신 한 일을\n한 화면에",
                   "말을 글로 옮기고, 책을 확정하고, 16개관을 확인하고, 규정 7종을 본 뒤 접수까지 이어 줍니다. 이용자는 말 한마디, 확인 한 번입니다.",
                   "※ 시연이며 실제 접수로 이어지지 않습니다")
        await W(3600)
        await scroll_to(150, 1600)
        await W(2600)
        mark("9 누구나", "처음 화면 → 큰글자 → 언어 선택(베트남어)")
        await ev("cover(true)"); await W(600)
        await app.goto(APP_URL + "?r=2", wait_until="load"); await W(900)
        await ev("cover(false)"); await W(400)
        await side("누구나", "큰글자 · 10개 언어 ·\n전화 한 통 모드",
                   "어르신, 외국인 주민, 시각이 불편한 분도 같은 흐름으로 쓸 수 있습니다.",
                   "음성 인식은 기기·브라우저가 지원하는 언어만 되고, 그 밖은 글자로 입력합니다")
        await W(1300)
        try:
            g = app.locator("#gateNo")
            if await g.count() and await g.is_visible():
                await tapclick(g); await W(700)
        except Exception as e:
            print("gateNo skipped", e)
        try:
            await tapclick(app.locator("#bigbtn")); await W(2800)
        except Exception as e:
            print("big skipped", e)
        try:
            await tapclick(app.locator("#langbtn")); await W(1700)
            vi = app.locator("text=Tiếng Việt").first
            if await vi.count():
                await tapclick(vi); await W(3200)
        except Exception as e:
            print("lang skipped", e)
        await W(1200)
        await hold("09", pad=0.4)
        await acdp.send("Page.stopScreencast")


        # ── 10. 명령 창 4: 설치형 ──
        NT = META.get("tests") or 104
        scene("10", "10 설치형", f"명령 창(기록 재생) — sh server/run.sh → 「준비 완료 — 시험 {NT}건」")
        await crumb("<b>설치형</b> · 명령 한 줄로 준비·시험")
        await ev("term('명령 창 · 설치형 참조 서버 준비·시험(Windows는 server\\\\run.bat을 두 번 누르기)'); only('term','bar')")
        await bar(f"설치형: 명령 한 줄로 자동 시험 {NT}건", "인증키·네트워크 없이 돌아갑니다(처음 한 번만 PyYAML 설치) · 전체 자동 시험은 193건(중계·원격·대조 포함)")
        await W(600)
        await page.evaluate("t=>termType(t,45)", "sh server/run.sh")
        await W(300)
        await page.evaluate("l=>termOut(l,70,x=>x.includes('✓')?'ok':(x.startsWith('[chaekiji-mcp]')?'c':''))", T4)
        await W(400)
        await ev("termFocus(['준비 완료'],300)")
        cue(f"준비 완료 — 시험 {NT}건")
        await W(2500)
        await hold("10")

        # ── 11. 어디까지 진짜인가 ──
        scene("11", "11 어디까지 진짜인가", "정직 카드 — 네 줄")
        await crumb("<b>책이지</b> · 어디까지 진짜인가")
        L = ["<b>지금</b> 사서가 창구·전화에서 쓰도록 만든 판정 도구입니다. 접수는 현행 시스템에서 합니다",
             "<b>다음(2027 시범)</b> 시민 음성 화면, 도서관리시스템과 연결해 접수까지",
             "<b>다른 도시</b> 도서관 코드·규정을 설정하면 같은 방식으로(정보나루는 전국 공통 자료)",
             "<b>정직 고지</b> 대출 상태는 정보나루 전일 기준이고, 시연 웹의 신청은 실제 접수가 아닙니다"]
        await card("어디까지 진짜인가", "판정까지는 지금, 접수는 연동 뒤", "", L)
        await lines([re.sub(r"<b>(.*?)</b> ", r"\1: ", x) for x in L], 3500, 1200, first=1000)
        await hold("11")

        # ── 12. 끝 ──
        scene("12", "12 끝", "끝 카드 — 주소·팀")
        await crumb("")
        await card("책이지 · 상호대차 상담 비서", "말 한마디로 내 손안에 책이",
                   "시연 웹 altarry-prog.github.io/chaekiji\n소스 공공 GitLab gitlab.aigov.go.kr/altarry/chaekiji-challenge\n깃허브 github.com/altarry-prog/chaekiji\n팀 책이지 · 경기도 부천시 상동도서관" + ("\n음성 해설: AI 합성(MeloTTS)" if NARR and not A.mute else ""), [])
        await W(5000)
        await hold("12", pad=0.9)
        t_end = now(); mark("종료")
        await W(300)
        await cdp.send("Page.stopScreencast")
        await W(300)
        await actx.close(); await ctx.close(); await b.close()
        json.dump({"t0": t0, "end": t_end, "badge": None if A.final else BADGE, "cues": CUES, "marks": MARKS, "errors": errs,
                   "narr": NARR_EV, "narr_dir": os.path.relpath(NARR_DIR, HERE),
                   "frames": [(a, c, os.path.basename(f)) for a, c, f in FRAMES]},
                  open(os.path.join(A.out, "captions.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        print("frames", len(FRAMES), "cues", len(CUES), "narr", len(NARR_EV), "errors", errs[:3])

asyncio.run(main())
