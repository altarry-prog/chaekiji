#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책이지 시연영상 녹화 — 장면을 차례로 띄우며 화면 갱신을 한 장씩 받아 적는다(1920x1080).

  python3 tools/video/record.py              # 초안(「초안 · 오늘 날짜」 표시)
  python3 tools/video/record.py --final      # 표시 없이(자리 표시 두 곳에 실제 녹화가 들어간 뒤)
  python3 tools/video/build_video.py         # → out/[시연영상]_경기도 부천시청_책이지(_초안).mp4 · .srt · 구성표.md

무엇을 보이나
- 표지: 녹화를 시작하기 전에 시연 웹 첫 화면을 받아 끝 칸과 같은 모양의 표지에 넣는다(영상 첫 장이자 썸네일, 소리 없음).
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
# 화면 글에 쓰는 예시(담당자 승인으로 바꿈). 흐름도의 이용자 말, 「다음 단계」 칸에 덧붙일 줄(없으면 None)
EX_SAY = os.environ.get("CHAEKIJI_VIDEO_SAY", "한강 소년이 온다 빌리고 싶어요, 역곡도서관에서 받을게요")
NEXT_EXTRA = os.environ.get("CHAEKIJI_VIDEO_NEXT", "정보화사업 연계로 전국 도서관이 같은 도구로 상호대차를 안내") or None
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

        # 표지(영상 첫 장이자 썸네일): 찍는 날의 시연 웹 첫 화면을 선명하게 받아 휴대폰 틀에 넣고, 녹화를 시작하기 전에 다 그려 둔다
        try:
            cctx = await b.new_context(viewport={"width": 390, "height": 790}, device_scale_factor=2.4, locale="ko-KR",
                                       has_touch=True, service_workers="block")
            await cctx.route("**/*workers.dev*", lambda r: r.abort())
            await cctx.add_init_script("try{localStorage.setItem('chaekiji.intro','1')}catch(e){}")   # v1.12.20: 표지는 처음 안내가 아니라 첫 화면
            cpg = await cctx.new_page()
            await cpg.goto(APP_URL, wait_until="load"); await cpg.wait_for_timeout(1200)
            g = cpg.locator("#gateNo")
            if await g.count() and await g.is_visible():
                await g.click(); await cpg.wait_for_timeout(900)
            cover_src = "data:image/png;base64," + base64.b64encode(await cpg.screenshot(type="png")).decode()
            await cctx.close()
        except Exception as e:
            print("cover shot skipped", e); cover_src = "/tools/video/cmp/app_home.png"
        COVER = ["책이지: 상호대차 AI 에이전트", "말 한마디로<br>내 손안에 책이", "팀 책이지 · 부천시립상동도서관",
                 "2026 공공 AI 대전환 챌린지 세션1 · 시연 영상", cover_src, "시연 웹 첫 화면"]
        await page.evaluate(f"draft({'false' if A.final else 'true'}, {json.dumps(BADGE, ensure_ascii=False)})")
        if not await page.evaluate("(a)=>cov(...a)", COVER):
            errs.append("composer: 표지 그림을 읽지 못함")
        await page.evaluate("only('cov')")
        await W(900)

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
            cue(h.replace("\n(", "(").replace("\n", " "), s, n_)
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

        scene_t = {}

        def scene(key, name, screen=""):
            # 장면 시작 — 내레이션이 있으면 이 시각(+NARR_LEAD)에 그 장면 음성을 얹는다(build_video.py)
            mark(name, screen); scene_t[key] = time.time()
            if key in NARR and not A.mute:
                NARR_EV.append((round(now() + NARR_LEAD, 2), NARR[key][0], NARR[key][1]))

        async def hold(key, pad=0.35):
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

        # ── 표지: 끝 칸과 같은 모양, QR 자리에 시연 웹 첫 화면(녹화 전에 다 그려 둔 그대로, 소리 없이) ──
        scene("CV", "· 표지", "끝 칸과 같은 모양(과제명·한 줄 표어·팀·챌린지 이름)에 찍는 날의 시연 웹 첫 화면을 휴대폰 틀로 크게, 소리 없이 약 2.4초")
        cue(COVER[0] + " · 말 한마디로 내 손안에 책이", COVER[2], COVER[3])   # 자막 세 줄이 「·」로 시작하지 않게
        await W(2400)

        # ── 1. 제목 · 왜(인포: 제목 칸 → 큰 숫자 세 칸과 신청 전 세 가지) ──
        scene("01", "1 제목·왜 만들었나", "제목(과제명·한 줄 설명·세 가지 특징) → 상호대차 큰 숫자 세 칸(44개소·320,140권·96.5%)과 신청 전 세 가지 확인")
        await crumb("")
        w1, w2 = share("01", [0.36, 0.64], [7.0, 12.0])
        await page.evaluate("([k,t,s,c])=>{hero(k,t,s,c);only('hero')}",
                            ["부천시립상동도서관 · 2026 공공 AI 대전환 챌린지 세션1", "책이지: <em>상호대차 AI 에이전트</em>",
                             "이용자의 말 한마디로 상호대차 신청 가능 여부를 판정·안내",
                             ["지금 판은 사서의 창구·전화 상담용", "말은 AI가 알아듣고 <b>판정은 규칙이</b>", "AI 연결 표준(MCP)"]])
        cue("책이지: 상호대차 AI 에이전트", "이용자의 말 한마디로 상호대차 신청 가능 여부를 판정·안내 · 지금 판은 사서의 창구·전화 상담용")
        for i in range(3):
            await W(700 if i == 0 else 550); await ev(f"heroChip({i})")
        await W(max(800, w1 - 1800))
        await crumb("<b>책이지</b> · 왜 만들었나")
        await page.evaluate("(a)=>{stats(...a);only('stats','bar')}",
                            ["상호대차 서비스란", "다른 도서관의 책을 <em>가까운 도서관에서</em>", "「도서관법」이 정한 공공도서관의 업무입니다",
                             [{"v": "44", "u": "개소", "l": "부천시립도서관 상호대차 체계", "n": "하나의 체계로 운영"},
                              {"v": "320,140", "u": "권", "l": "2025년 한 해 시민에게 제공", "n": "부천시립도서관 상호대차 운영 실적", "hot": True},
                              {"v": "96.5", "u": "%", "l": "이용자 만족도", "n": "2025. 11. 조사 · 607명 중 586명"}],
                             "그런데 신청 전에는 세 가지를 확인해야 합니다",
                             [{"tt": "어떤 책인지", "dd": "자료 확인(제목·판본)"}, {"tt": "어디서 빌릴 수 있는지", "dd": "소장·대출 확인"},
                              {"tt": "신청할 수 있는지", "dd": "신청 요건(규정 7종) 확인"}]])
        await bar("부천시립도서관은 2025년 한 해 32만 권을 상호대차로 제공했습니다", "44개소 하나의 체계 · 이용자 만족도 96.5%(2025. 11. 조사)")
        step = max(500, int(w2 * 0.12))
        for i in range(3):
            await W(step); await ev(f"statsTile({i})")
        await W(step); await ev("statsNeed()")
        await bar("신청 전에는 세 가지 확인이 필요합니다", "어떤 책인지 · 어디서 빌릴 수 있는지 · 신청할 수 있는지(지금은 사서와 이용자가 매번 직접 확인)")
        for i in range(3):
            await W(int(step * 0.7)); await ev(f"statsStep({i})")
        await W(max(600, w2 - step * 4 - int(step * 2.1)))
        await hold("01")

        # ── 4. 같은 책으로 재 보니(비교 장면, 4배속) ──
        scene("04", "4 같은 책으로 재 보니(비교)", "왼쪽 누리집 실제 화면 8장(개인정보 가림)에 누른 수·시간이 오름, 오른쪽 책이지 시연 화면은 측정과 같은 순서(「눌러서 시작하기」 · 마이크 누르고 책 제목 말하기 · 「방문 안내 보기」)로 3번 만에 「20초에 안내」. 실제 걸린 시간을 4배 빨리. 직원 3명이 시연 도서 5권으로 잰 가운데값(책마다 평균, 2026. 10. 27.)")
        await crumb("")
        await page.evaluate("s=>cmpLoad(s)", "/tools/video/cmp/compare.html?spd=4")
        await ev("only('cmpf')")
        cue("같은 책으로 재 보니 책이지 시연 화면은 3번 눌러 20초, 누리집은 18번 눌러 1분 20초",
            "개발에 참여하지 않은 직원 3명이 시연 도서 5권으로 잰 가운데값(책마다 평균, 2026. 10. 27.) · 끝: 누리집은 신청 버튼, 책이지는 「바로 이용」 방문 안내 · 화면은 따로 찍음(누리집은 개인정보 가림)")
        await W(400)
        await page.evaluate("cmpPlay(4)")
        await W(700)
        await hold("04", pad=0.4)

        # ── 2. 어떻게(인포: 누가 무엇을 하나) ──
        scene("02", "2 어떻게 푸나", "흐름 네 칸(이용자·AI 모델·규칙 도구(MCP)·결과와 사서)을 색으로 나눠 차례로 → 「도구를 제대로 부르면 모델을 바꿔도 판정은 같습니다」")
        await crumb("<b>책이지</b> · 어떻게 푸나")
        await page.evaluate("(a)=>{flow2(...a);only('flow2')}",
                            ["어떻게 푸나", "말은 AI가 알아듣고, <em>판정은 규칙이</em> 합니다",
                             [{"tg": "이용자", "c": "u", "h": "이용자의 말", "d": f"「{EX_SAY}」"},
                              {"tg": "AI 모델", "c": "a", "h": "알아듣고 도구를 부름", "d": "Claude · 엑사원 · 라마<br>책과 받을 도서관을 알아들음"},
                              {"tg": "규칙 도구(MCP)", "c": "r", "h": "찾고 확인하고 판정", "d": "책 찾기<br>16개관 소장·대출(정보나루)<br>규정 7종"},
                              {"tg": "결과 · 사서", "c": "o", "h": "안내문과 접수 메모", "d": "판정 · 이용자 안내문<br>접수 메모(접수는 사서가)"}],
                             "도구를 제대로 부르면, 모델을 바꿔도 판정은 같습니다",
                             "MCP는 AI 모델이 외부 도구를 부르는 공통 규격 · 대출 상태는 정보나루 전일 기준 · 접수는 사서가 현행 시스템에서"])
        cue("말은 AI가 알아듣고, 판정은 규칙이 합니다")
        steps = [f"이용자의 말: 「{EX_SAY}」", "AI 모델(Claude · 엑사원 · 라마): 말을 알아듣고 도구를 부름",
                 "규칙 도구(MCP): 책 찾기 · 16개관 소장·대출(정보나루) · 규정 7종", "결과: 판정 · 이용자 안내문 · 접수 메모(접수는 사서가)"]
        g2 = share("02", [0.16, 0.16, 0.16, 0.16], [1.6, 1.6, 1.6, 1.6])
        await W(800)
        for i in range(4):
            await ev(f"flow2Step({i})"); cue(steps[i]); await W(g2[i])
        await ev("flow2Say()")
        cue("도구를 제대로 부르면, 모델을 바꿔도 판정은 같습니다", "MCP는 AI 모델이 외부 도구를 부르는 공통 규격 · 대출 상태는 정보나루 전일 기준 · 접수는 사서가 현행 시스템에서")
        await W(3500)
        await hold("02")

        # ── 3. 흐름 1 소개(인포: 세 단계) ──
        scene("03", "3 흐름 1 소개", "연결 세 단계 칸(커넥터 추가 · 주소 넣기 · 말을 그대로)")
        await crumb("<b>흐름 1</b> / 3 · 창구·전화 상담(주 결과물)")
        S3 = [{"h": "커넥터 추가", "d": "claude.ai 「사용자 정의」의 「커넥터」에서 「커스텀 커넥터 추가」"},
              {"h": "주소 한 줄 넣기", "d": "인증은 「로그인 없음」", "pill": "chaekiji-relay.altarry2.workers.dev/mcp"},
              {"h": "말을 그대로", "d": "새 대화에서 커넥터를 켜고, 이용자의 말을 그대로 넣습니다"}]
        await page.evaluate("(a)=>{steps3(...a);only('steps3')}", ["흐름 1 · 창구·전화 상담", "claude.ai에 주소 한 줄이면 <em>설치 없이</em> 씁니다", S3])
        cue("claude.ai에 주소 한 줄이면 설치 없이 씁니다")
        g3 = share("03", [0.28, 0.28, 0.28], [2.6, 2.6, 2.6])
        await W(700)
        for i in range(3):
            await ev(f"steps3On({i})"); cue(S3[i]["h"] + ": " + S3[i]["d"] + ((" " + S3[i]["pill"]) if S3[i].get("pill") else "")); await W(g3[i])
        await hold("03")

        # ── 0. 흐름 1 실제 화면: claude.ai(창구 질문을 그대로, 담당자 10. 30. 「흐름 1 소개 뒤로」) ──
        m = clip_meta("claude")
        scene("00", "3-2 흐름 1 실제 화면(claude.ai)", "2026. 10. 20. 크롬 실제 화면 캡처 20초. 창구 질문을 그대로 넣고 판정·안내문이 나오기까지(기다린 약 50초는 빨리 감음, 첫 3초 커넥터 목록의 다른 커넥터 이름은 흐림 처리)")
        await crumb("<b>흐름 1</b> / 3 · claude.ai 실제 화면(2026. 10. 20.)")
        if m:
            await play_clip(m)
        else:
            await slot("claude.ai에서 같은 문의를 넣는\n실제 화면(20초)", "clips/claude.webm이 없어 자리 표시를 둡니다")
            await W(6000)
        await hold("00")

        # ── 5. 명령 창 1: 관내 상호대차(찍는 날 자료로 고른 책, capture.py) · 오른쪽에 읽는 법 ──
        A1 = META["t1"]
        P1 = A1.get("pickup", "상동")
        here1 = "대출 중" if re.search(rf"수령관: {P1} \((?:현재|조회일 기준) 대출 중\)", "\n".join(T1)) else "없음"   # [10/28] 접수 메모가 「(조회일 기준 대출 중)」으로 바뀜
        rule1 = re.search(r"규정: (\d+)건 통과 · (\d+)건 불가 · (\d+)건 창구 확인", "\n".join(T1))
        rtxt = f"규정 {rule1.group(1)}건 통과 · {rule1.group(3)}건 창구 확인" if rule1 else "규정 확인"
        scene("05", "5 명령 창 1(관내 상호대차)", f"명령 창(기록 재생) {A1['title']} · {P1}, 오른쪽 「읽는 법」 칸에서 판정·근거 → 안내문 → 접수 메모를 차례로 강조")
        await crumb("<b>흐름 1</b> / 3 · 같은 도구를 PC에서 직접 부르기")
        await ev("term('명령 창 · 책이지 도구를 한 번 부르기(server/lab/consult_cli.py)'); termNarrow(1); only('term','read','bar')")
        await page.evaluate("r=>{readPanel(r);readOn([])}", [
            {"lb": "① 판정", "vv": f"<span class=\"pill\">{A1['route']}</span>", "ss": (f"소장관 {A1.get('holder')} · " if A1.get('holder') else "") + f"{P1}에서 받기"},
            {"lb": "② 근거", "vv": f"{P1}은 {here1}<br>{A1['available'][0]} 등 {len(A1['available'])}곳은 대출 가능", "ss": f"정보나루 {A1['asof']} 조회(전일 기준)"},
            {"lb": "③ 이용자 안내문", "vv": "조회일과 공식 누리집 링크를 붙여 안내"},
            {"lb": "④ 접수 메모", "vv": rtxt, "ss": "접수는 사서가 창구에서"}])
        await bar("모델 없이 도구만 불러 봅니다", "claude.ai가 부르는 것과 같은 도구(consult_request)입니다")
        await W(1000)
        await ev("termComment('이 PC는 중계에 닿지 않아 오늘 새벽 자료로 실행(원격 판도 이 책은 같은 자료로 답함)')")
        await W(700)
        await page.evaluate("t=>termType(t,22)", f'CHAEKIJI_MODE=snapshot python lab/consult_cli.py "{A1["utterance"]}" {P1}')
        await W(300)
        await page.evaluate("l=>termOut(l,90)", T1)
        await W(500)
        g5 = share("05", [0.30, 0.24, 0.22], [6.0, 5.5, 5.0])
        await ev("termFocus(['◀ 판정','◀ 근거']); readOn([0,1])")
        await bar(f"판정: {A1['route']}", f"{P1}은 {here1}, {A1['available'][0]} 등 {len(A1['available'])}곳은 대출 가능 · 정보나루 {A1['asof']} 조회(전일 기준)")
        await W(g5[0])
        await ev("termFocus(['◀ 안내문','◀ 링크']); readOn([2])")
        await bar("이용자에게 읽어 줄 안내문", "조회일과 공식 누리집의 그 책 화면 주소가 붙습니다")
        await W(g5[1])
        await ev("termFocus(['◀ 접수 메모','   도서:','   갈래:','   수령관:','   대출 가능 관:','   근거:','   규정:','   접수:']); readOn([3])")
        await bar("사서가 옮겨 적는 접수 메모", f"{rtxt} · 접수는 창구에서 사서가 합니다")
        await W(g5[2])
        await hold("05")

        # ── 6. 명령 창 2: 바로 이용 ──
        A2 = META["t2"]
        P2 = A2.get("pickup", "상동")
        scene("06", "6 명령 창 2(바로 이용)", f"명령 창(기록 재생) {A2['title']} · {P2} → 바로 이용, 읽는 법 칸")
        await ev("term('명령 창 · 다른 책으로'); termNarrow(1); only('term','read','bar')")
        await page.evaluate("r=>{readPanel(r);readOn([])}", [
            {"lb": "① 판정", "vv": f"<span class=\"pill\">{A2['route']}</span>", "ss": f"받을 도서관({P2})에 대출 가능(조회일 기준)"},
            {"lb": "② 근거", "vv": f"{P2} 등 {len(A2['available'])}곳 대출 가능", "ss": f"정보나루 {A2['asof']} 조회(전일 기준)"},
            {"lb": "③ 이용자 안내문", "vv": "상호대차 없이 바로 빌리시면 됩니다"}])
        await bar("받을 도서관 서가에 있으면", "상호대차 대신 「바로 이용」으로 안내합니다")
        await W(500)
        await page.evaluate("t=>termType(t,24)", f'CHAEKIJI_MODE=snapshot python lab/consult_cli.py "{A2["utterance"]}" {P2}')
        await W(300)
        await page.evaluate("l=>termOut(l,80)", T2)
        await W(400)
        await ev("termFocus(['◀ 판정','   수령관:']); readOn([0,1,2])")
        await W(4000)
        await hold("06")

        # ── 7. 명령 창 3: 정보나루가 끊긴 날 ──
        scene("07", "7 명령 창 3(조회 불가)", "명령 창(기록 재생) 중계를 일부러 끊고 채식주의자 → 소장 확인 불가, 읽는 법 칸")
        await ev("term('명령 창 · 정보나루에 닿지 못한 날'); termNarrow(1); only('term','read','bar')")
        await page.evaluate("r=>{readPanel(r);readOn([])}", [
            {"lb": "① 판정", "vv": "<span class=\"pill warn\">소장 확인 불가</span>", "ss": "창구에서 조회"},
            {"lb": "② 근거", "vv": "정보나루에 닿지 못함", "ss": "중계가 끊긴 상황을 일부러 만듦"},
            {"lb": "③ 이용자 안내문", "vv": "「없다」고 하지 않고 창구 조회로 넘김"}])
        await bar("자료에 닿지 못하면 「없다」고 하지 않습니다", "「창구에서 조회」로 넘깁니다(v0.3.5에서 고침)")
        await W(500)
        await ev("termComment('중계가 끊긴 상황을 일부러 만듦(닿지 않는 주소)')")
        await W(600)
        await page.evaluate("t=>termType(t,20)", f'CHAEKIJI_MODE=relay CHAEKIJI_RELAY=http://127.0.0.1:9 python lab/consult_cli.py "채식주의자 있나요?" {P1}')
        await W(300)
        await page.evaluate("l=>termOut(l,110)", T3)
        await W(400)
        await ev("termFocus(['◀ 판정','◀ 안내문'],120); readOn([0,1,2])")
        await W(4300)
        await hold("07")
        await ev("termNarrow(0)")

        # ── 8. 흐름 2: 공개 모델(인포: 숫자 칸) → 저장소의 실측 기록표 ──
        scene("08", "8 흐름 2(공개 모델)", "숫자 칸(공개 모델 2종 · 기록표 15건 · 도구 결과를 받은 11건은 판정 같음) → 저장소의 공개 모델 실측 기록표(2026. 10. 18. 깃허브 액션 실행, 글은 원문 그대로)")
        await crumb("<b>흐름 2</b> / 3 · 같은 상담을 공개 모델로")
        await page.evaluate("(a)=>{nums(...a);only('nums')}",
                            ["흐름 2 · 같은 상담을 공개 모델로", "코랩 「모두 실행」 한 번, <em>공개 모델 2종</em>",
                             [{"v": "2", "u": "종", "l": "공개 모델", "n": "엑사원 3.5 2.4B(행정안전부 AI 공통기반 지원 모델) · 라마 3.2 3B"},
                              {"v": "15", "u": "건", "l": "기록표가 남은 3차례 × 문의 5건", "n": "같은 지시문 · 같은 도구(consult_request) · 2026. 10. 18. 깃허브 액션 실행"},
                              {"v": "11", "u": "건", "l": "두 모델 모두 도구 결과를 받은 답", "n": "판정이 모두 같았음", "hot": True}],
                             "나머지 <b>4건</b>은 한쪽 모델이 도구 없이 답해 쓸 수 없는 답이었습니다. 그래서 판정은 모델이 아니라 규칙 도구가 합니다."])
        cue("같은 상담을 공개 모델로, 코랩 「모두 실행」 한 번", "엑사원 3.5 2.4B · 라마 3.2 3B · 같은 지시문 · 같은 문의 5건 · 같은 도구(consult_request)")
        await app.goto(APP_URL, wait_until="load")       # 다음 장면에 쓸 시연 웹을 미리 띄워 둔다(보이지 않는 동안)
        g8 = share("08", [0.03, 0.03, 0.04, 0.05], [0.7, 0.7, 0.9, 1.2])
        for i in range(3):
            await W(g8[i]); await ev(f"numsOn({i})")
        # [10/30] 1.2~1.4초만 보이던 자막 두 줄(1차 검수 A 28)은 빼고, 같은 말은 화면 글과 이어지는 기록표 클립 자막(8초씩)이 맡는다
        await W(g8[3]); await ev("numsNote()")
        await W(1200)
        m = clip_meta("model2")
        if m:
            await play_clip(m)
        else:
            await slot("공개 모델 실측 기록표", "clips/model2.webm이 없습니다(make_record_clip.py)")
            await W(5000)
        await acdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90, "maxWidth": 468, "maxHeight": 948, "everyNthFrame": 1})
        await hold("08", pad=0.3)

        # ── 9. 흐름 3: 시민 음성 화면(왼쪽 위에 단계 표시) ──
        scene("09", "9 흐름 3 시작", "왼쪽 단계 표시(처음 안내·판정·신청 확인·접수(시연)·누구나)와 설명 + 오른쪽 휴대폰(시연 웹 v1.12.20 실제 조작)")
        await crumb("<b>흐름 3</b> / 3 · 시민 음성 화면(2027 시범 운영 제안)")
        await ev("side('','','',''); dsteps(['처음 안내','판정','신청 확인','접수(시연)','누구나']); dstep(0); only('side','phone')")
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
                   "휴대폰 인터넷 창에서 엽니다. 처음 열면 상호대차가 무엇인지와 쓰는 법을 먼저 알려 드리고, 자주 가는 도서관을 고르게 합니다.",
                   "시연 웹 altarry-prog.github.io/chaekiji")
        await W(2600)
        KDAY = await app.evaluate("typeof 기준일 !== 'undefined' ? 기준일 : ''")      # v1.12.20 예시 단추 자료 날짜(예: 2026. 10. 30.)
        KD = re.sub(r"^\d{4}\. ", "", KDAY) or "실제 자료"
        try:
            intro = app.locator("#introGo")
            if await intro.count() and await intro.is_visible():
                mark("9 처음 안내", "처음 열면 한 번: 상호대차란 · 이렇게 써요 · 자주 가는 도서관 → 「시작하기」")
                await side("처음 안내", "처음 열면 한 번,\n상호대차부터 알려 드립니다",
                           "상호대차란 · 이렇게 써요 · 자주 가는 도서관 고르기. 「시작하기」를 누르면 음성 안내가 시작됩니다.",
                           "직원 의견(10. 30.)으로 넣음 · 10개 언어")
                await W(2600)
                await app.evaluate("(()=>{const i=document.getElementById('intro');if(i)i.scrollTo({top:i.scrollHeight,behavior:'smooth'})})()")
                await W(2000)
                await tapclick(intro); await W(1500)
            else:
                g = app.locator("#gateGo")
                if await g.count() and await g.is_visible():
                    await tapclick(g); await W(1500)
        except Exception as e:
            print("intro/gate skipped", e)
        mark("9 판정", "예시 ① 누름 → 처리 단계 → 판정 화면, 아래로 굴려 다른 도서관까지")
        await ev("dstep(1)")
        await tapclick(app.locator("text=나미야 잡화점의 기적 빌리고 싶어요").first)
        await side("판정", "상동은 대출 중이라\n다른 도서관에서 보내 드립니다",
                   f"예시 단추도 정보나루 실제 자료({KD} 새벽 자료)로 판정합니다. 직접 말하거나 입력하면 그날 새벽 자료로 찾습니다.",
                   "대출 상태는 정보나루 전일 기준")
        await W(4300)
        for y in (200, 400):
            await scroll_to(y, 1200)
        await W(700)
        await scroll_to(0, 900)
        mark("9 신청 확인", "「상호대차 신청」 → 확인 시트")
        await ev("dstep(2)")
        await tapclick(app.locator("#apply"))
        await side("신청 확인", "대출관 · 수령관 · 소요 ·\n수령 기한 · 미수령 제한",
                   "화면을 읽어 주고, 「네」 한마디나 단추 한 번으로 확인합니다.", "※ 시연이며 실제 접수로 이어지지 않습니다")
        await W(4500)
        mark("9 접수(시연)", "「네, 신청합니다」 → 접수(시연) 화면: 맨 위 받는 방법(수령 도서관·예상 도착·수령 기한·빌리는 방법), 「책이지가 대신 한 일」까지 굴림")
        await ev("dstep(3)")
        try:
            await tapclick(app.locator("#confirm")); await W(1300)
        except Exception as e:
            print("confirm skipped", e)
        await side("접수(시연)", "받는 방법을 맨 위에,\n대신 한 일까지 한 화면에",
                   "말을 글로 옮기고, 책을 확정하고, 16개관을 확인하고, 신청 규정을 확인한 뒤(한도·연체는 안내데스크에서) 접수(시연) 화면까지 이어 줍니다. 이용자는 말 한마디, 확인 한 번입니다.",
                   "※ 시연이며 실제 접수로 이어지지 않습니다")
        await W(2600)
        await scroll_to(320, 1400)
        await W(1600)
        mark("9 누구나", "처음 화면 → 큰글자 → 언어 선택(베트남어)")
        await ev("dstep(4)")
        await ev("cover(true)"); await W(600)
        await app.goto(APP_URL + "?r=2", wait_until="load"); await W(900)
        await ev("cover(false)"); await W(400)
        await side("누구나", "큰글자 · 10개 언어 ·\n전화 한 통 모드",
                   "어르신, 외국인 주민, 시각이 불편한 분도\n같은 흐름으로 쓰도록 설계했습니다(당사자 시험은 시범 운영 때).",
                   "음성 인식은 기기·브라우저가 지원하는 언어만 되고, 그 밖은 글자로 입력합니다")
        await W(1300)
        try:
            g = app.locator("#gateNo")
            if await g.count() and await g.is_visible():
                await tapclick(g); await W(700)
        except Exception as e:
            print("gateNo skipped", e)
        try:
            await tapclick(app.locator("#bigbtn")); await W(1700)
        except Exception as e:
            print("big skipped", e)
        try:
            await tapclick(app.locator("#langbtn")); await W(1200)
            vi = app.locator("text=Tiếng Việt").first
            if await vi.count():
                await tapclick(vi); await W(1300)
        except Exception as e:
            print("lang skipped", e)
        # [10/28 표지를 넣으며] 이 장면은 내레이션보다 화면이 3.5초 길었다. 끝의 기다림을 2초쯤 줄여 5분 안 여유를 둔다(내레이션은 hold가 끝까지 지킴)
        await hold("09", pad=0.3)
        await acdp.send("Page.stopScreencast")
        await ev("dsteps([])")

        # ── 10. 명령 창 4: 설치형(오른쪽에 시험 수) ──
        NT = META.get("tests") or 104
        scene("10", "10 설치형", f"명령 창(기록 재생) sh server/run.sh → 「준비 완료: 시험 {NT}건」, 오른쪽 칸에 시험 수")
        await crumb("<b>설치형</b> · 명령 한 줄로 준비·시험")
        await ev("term('명령 창 · 설치형 참조 서버 준비·시험(Windows는 server\\\\run.bat을 두 번 누르기)'); termNarrow(1); only('term','read','bar')")
        await page.evaluate("r=>{readPanel(r,'설치형 · 명령 한 줄');readOn([])}", [
            {"lb": "자동 시험(설치형)", "vv": f"<div class=\"bigv\">{NT}<small>건</small></div>", "ss": "인증키·네트워크 없이 돌아갑니다"},
            {"lb": "전체 자동 시험", "vv": "193건", "ss": "중계·원격·대조 포함"},
            {"lb": "준비", "vv": "처음 한 번만 PyYAML 설치", "ss": "Windows는 server\\run.bat을 두 번 누르기"}])
        await bar(f"설치형: 명령 한 줄로 자동 시험 {NT}건", "인증키·네트워크 없이 돌아갑니다(처음 한 번만 PyYAML 설치) · 전체 자동 시험은 193건(중계·원격·대조 포함)")
        await W(500)
        await page.evaluate("t=>termType(t,40)", "sh server/run.sh")
        await W(300)
        await page.evaluate("l=>termOut(l,60,x=>x.includes('✓')?'ok':(x.startsWith('[chaekiji-mcp]')?'c':''))", T4)
        await W(400)
        await ev("termFocus(['준비 완료'],300); readOn([0,1,2])")
        cue(f"준비 완료: 시험 {NT}건")
        await W(2500)
        await hold("10")
        await ev("termNarrow(0)")

        # ── 11. 어디까지 진짜인가(인포: 지금 / 다음 두 칸) ──
        scene("11", "11 어디까지 진짜인가", "두 칸: 지금 되는 것(사서 상담용) · 다음 단계(2027 시범 운영 제안), 아래 정직 고지")
        await crumb("<b>책이지</b> · 어디까지 진짜인가")
        NEXT = ["시민 음성 화면(지금은 시연, 실제 접수 아님)", "도서관리시스템과 연결해 접수까지",
                "다른 지자체는 도서관 코드·규정을 설정해 적용(정보나루는 전국 공통 자료)"]
        if NEXT_EXTRA:
            NEXT.append(NEXT_EXTRA)
        await page.evaluate("(a)=>{two(...a);only('two')}",
                            ["어디까지 진짜인가", "판정까지는 지금, <em>접수는 연동 뒤</em>",
                             {"h": "지금 되는 것", "sub": "사서 상담용", "items": [
                                 "사서가 창구·전화에서 쓰도록 만든 판정 도구(접수는 현행 시스템에서)",
                                 "정보나루 실제 자료로 16개관 소장·대출 확인(전일 기준)",
                                 "공개 모델 2종도 같은 도구로 같은 판정(도구 결과를 받은 11건)"]},
                             {"h": "다음 단계", "sub": "2027 시범 운영 제안", "items": NEXT},
                             "대출 상태는 정보나루 전일 기준이고, 시연 웹의 신청은 실제 접수가 아닙니다"])
        cue("판정까지는 지금, 접수는 연동 뒤")
        g11 = share("11", [0.35, 0.35], [3.0, 3.0])
        await W(700); await ev("twoOn(0)"); cue("지금 되는 것: 사서가 창구·전화에서 쓰도록 만든 판정 도구(접수는 현행 시스템에서) · 정보나루 실제 자료(전일 기준) · 공개 모델 2종도 도구 결과를 받은 11건은 같은 판정")
        await W(g11[0]); await ev("twoOn(1)"); cue("다음 단계(2027 시범): " + " · ".join(NEXT))
        await W(g11[1]); await ev("twoFoot()"); cue("대출 상태는 정보나루 전일 기준이고, 시연 웹의 신청은 실제 접수가 아닙니다")
        await hold("11")

        # ── 12. 끝(주소 · 휴대폰으로 여는 QR) ──
        scene("12", "12 끝", "끝 칸: 과제명·한 줄 표어·주소 세 줄·팀, 오른쪽에 시연 웹 QR")
        await crumb("")
        L12 = [["시연 웹", "altarry-prog.github.io/chaekiji"], ["공공 GitLab", "gitlab.aigov.go.kr/altarry/chaekiji-challenge"], ["깃허브", "github.com/altarry-prog/chaekiji"]]
        await page.evaluate("(a)=>{endc(...a);only('endc')}",
                            ["책이지: 상호대차 AI 에이전트", "말 한마디로<br>내 손안에 책이", L12, "팀 책이지 · 부천시립상동도서관",
                             "음성 해설: AI 합성(MeloTTS)" if NARR and not A.mute else "", "/tools/video/cmp/qr_demo.png", "휴대폰으로 시연 웹 열기"])
        cue("말 한마디로 내 손안에 책이", " · ".join(f"{a} {b}" for a, b in L12) + " · 팀 책이지 · 부천시립상동도서관")
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
