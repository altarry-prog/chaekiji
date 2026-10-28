#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""명령 창 장면의 출력(t1~t4.txt)을 다시 받고, 화면 글에 쓸 값(t_meta.json)을 남긴다. 저장소 루트에서:

  python3 tools/video/capture.py

- 매일 새벽 자료(data/holdings-today.json)는 날마다 바뀐다. 그래서 찍는 날의 자료를 보고
  t1에는 「상동은 대출 중이고 다른 분관에 있는 책」(관내 상호대차), t2에는 「상동 서가에 있는 책」(바로 이용)을
  시연 도서 가운데서 고른다. 영상 첫 장면(claude.ai, 10. 20.)의 나미야 잡화점의 기적은 날짜가 달라 결과가 다를 수 있어 고르지 않는다.
- 내레이션은 책 이름·관 수를 말하지 않고, 화면 글(record.py)이 t_meta.json의 값을 그대로 쓴다.
- t3은 중계를 일부러 끊은 날(닿지 않는 주소), t4는 sh server/run.sh(설치형 시험)."""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SERVER = os.path.join(ROOT, "server")
PY = sys.executable
PICKUP = os.environ.get("CHAEKIJI_VIDEO_PICKUP", "역곡")   # 영상 예시의 받을 곳(담당자 승인으로 바꿈, 예: 역곡)
SKIP = {"9788972756194",          # 나미야: 첫 장면(10. 20.)과 날짜가 달라 결과가 엇갈릴 수 있음
        "9791191824001"}          # 지구 끝의 온실: 시연 웹에서 「관내에 없음, 책바다(예시)」 장면이라 헷갈리지 않게
PICKUP2 = os.environ.get("CHAEKIJI_VIDEO_PICKUP2", "상동")   # 명령 창 2(바로 이용)의 받을 곳

snap = json.load(open(os.path.join(ROOT, "data", "holdings-today.json"), encoding="utf-8"))
cat = {b["isbn13"]: b for b in json.load(open(os.path.join(SERVER, "fixtures", "catalog.json"), encoding="utf-8"))["books"]}
order = ["9788936434120", "9791161571188", "9791195794799", "9791191824001", "9788972756194"]   # 시연 도서 5종
H = snap["holdings"]


def pick(want, pickup=None):
    pickup = pickup or PICKUP
    for isbn in order:
        if isbn in SKIP or isbn not in H or isbn not in cat:
            continue
        st = H[isbn]
        here = st.get(pickup)
        others = [k for k, v in st.items() if k != pickup and v == "ok"]
        if want == "ill" and here in ("busy", "none") and others:
            return isbn
        if want == "visit" and here == "ok":
            return isbn
    return None


def run(env_extra, args, out):
    env = dict(os.environ, **env_extra)
    for k in ("CHAEKIJI_SNAPSHOT", "CHAEKIJI_LOCAL_SOURCE"):
        env.pop(k, None)
    r = subprocess.run([PY, "lab/consult_cli.py"] + args, cwd=SERVER, env=env, capture_output=True, text=True)
    open(os.path.join(HERE, out), "w", encoding="utf-8").write(r.stdout)
    return r.stdout


def meta(text, title, utter, pickup=None):
    # 판정 줄: 「관내 상호대차(소장관 꿈빛)」·「바로 이용(수령관 서가에 있음)」(10. 27.부터 긴줄표 대신 괄호)
    route = re.search(r"^◀ 판정: ([^(\n—]+)", text, re.M)
    holder = re.search(r"^◀ 판정: [^\n]*소장관 ([^)\s]+)", text, re.M)
    avail = re.search(r"대출 가능 관: ([^/\n]+)", text)
    libs = [x.strip() for x in avail.group(1).split(",")] if avail else []
    asof = re.search(r"(\d{4})-(\d{2})-(\d{2}) 조회", text)
    return {"title": title, "utterance": utter, "pickup": pickup or PICKUP, "route": route.group(1).strip() if route else "",
            "holder": holder.group(1) if holder else "",
            "available": libs, "asof": f"{int(asof.group(1))}. {int(asof.group(2))}. {int(asof.group(3))}." if asof else ""}


i1, i2 = pick("ill"), pick("visit", PICKUP2)
if not i1 or not i2:
    sys.exit(f"오늘 자료({snap.get('asof')})로는 {PICKUP} 기준 두 장면을 고를 수 없습니다(ill={i1} visit={i2})")
u1 = f"{cat[i1]['title']} 빌리고 싶어요"
u2 = cat[i2]["title"]
t1 = run({"CHAEKIJI_MODE": "snapshot"}, [u1, PICKUP], "t1.txt")
t2 = run({"CHAEKIJI_MODE": "snapshot"}, [u2, PICKUP2], "t2.txt")
run({"CHAEKIJI_MODE": "relay", "CHAEKIJI_RELAY": "http://127.0.0.1:9"}, ["채식주의자 있나요?", PICKUP], "t3.txt")
r = subprocess.run(["sh", "server/run.sh"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)   # 화면처럼 섞어서
open(os.path.join(HERE, "t4.txt"), "w", encoding="utf-8").write(r.stdout)
m4 = re.search(r"준비 완료[:\s—]*시험 (\d+)건", r.stdout)
M = {"asof": snap.get("asof"), "t1": meta(t1, cat[i1]["title"], u1), "t2": meta(t2, cat[i2]["title"], u2, PICKUP2),
     "tests": int(m4.group(1)) if m4 else None}
json.dump(M, open(os.path.join(HERE, "t_meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(M, ensure_ascii=False, indent=1))
