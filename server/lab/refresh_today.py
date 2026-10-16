#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[v0.3.4] 매일 1회 갱신 — 정해 둔 도서 목록의 관내 소장·대출 상태를 정보나루에서 받아 「오늘 조회분」 파일로 쓴다.

왜: 정보나루의 대출 가능 여부는 어차피 「조회일 전일 기준」이라, 하루 한 번 받아 두면 실시간 호출과 신선도가 같다.
    인증키는 이 스크립트를 돌리는 쪽(GitHub Actions의 Secrets · 도서관 PC의 환경변수)에만 있고,
    결과 파일에는 소장·대출 상태와 날짜만 남는다. 서버(auto 모드)와 시연 웹이 이 파일을 읽으면 중계 없이도 어제 기준 데이터가 된다.

실행:  NARU_KEY=…  python lab/refresh_today.py                 (기본: 픽스처 5종 + lab/refresh_list.txt의 ISBN)
      python lab/refresh_today.py --demo                       (네트워크 없이 연습 — 8/18 픽스처를 오늘 날짜로 베낀다)
옵션: --max-calls 300  (하루 한도 500건 안에서 쓸 상한 · 넘치면 거기서 멈추고 partial 표시)
결과: fixtures/holdings-today.json  (서버용) · ../data/holdings-today.json (시연 웹용, 같은 내용)
      lab/out/refresh_status.json  (실행 기록 — 성공·실패와 까닭, 키는 가려서. 실패해도 쓴다)
      {"asof":"YYYY-MM-DD","source":"정보나루 bookExist","holdings":{isbn:{관:ok|busy|none}},"nation":{isbn:{"count":n}},"calls":n,"partial":false}
목록: lab/refresh_list.txt — 한 줄에 ISBN13 하나(# 뒤는 메모). 없으면 픽스처 5종만."""
import os, sys, json, argparse, datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ap = argparse.ArgumentParser()
ap.add_argument("--max-calls", type=int, default=300)
ap.add_argument("--demo", action="store_true", help="네트워크 없이 연습(픽스처 → 오늘 날짜)")
ap.add_argument("--list", default=str(ROOT / "lab" / "refresh_list.txt"))
ap.add_argument("--config", default=str(ROOT / "config" / "bucheon.yaml"))
ap.add_argument("--out", default=str(ROOT / "fixtures" / "holdings-today.json"))
ap.add_argument("--web-out", default=str(ROOT.parent / "data" / "holdings-today.json"))
ap.add_argument("--status-out", default=str(ROOT / "lab" / "out" / "refresh_status.json"))
a = ap.parse_args()

os.environ["CHAEKIJI_CONFIG"] = a.config
os.environ["CHAEKIJI_MODE"] = "demo" if a.demo else "live"
os.environ["CHAEKIJI_LOCAL_SOURCE"] = "naru"
os.environ.pop("CHAEKIJI_STORE", None); os.environ.pop("CHAEKIJI_AUDIT", None)
if not a.demo and not os.environ.get("NARU_KEY"):
    sys.exit("NARU_KEY가 없습니다(환경변수). 연습은 --demo")

import tools
from connectors import naru

def load_list():
    isbns = [b["isbn13"] for b in naru._cat["books"] if not b["isbn13"].startswith("9790000")]   # 시험용 가짜 ISBN 제외
    p = Path(a.list)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.split("#", 1)[0].strip().replace("-", "")
            if s.isdigit() and len(s) == 13 and s not in isbns:
                isbns.append(s)
    return isbns

KST = datetime.timezone(datetime.timedelta(hours=9))     # 깃허브 서버는 UTC — 조회일은 한국 날짜로
today = datetime.datetime.now(KST).date().isoformat()
def redact(msg):
    """실행 기록에 남기기 전에 키 원문을 가린다(오류 문구에 주소가 섞여 들어오는 경우 대비)."""
    k = os.environ.get("NARU_KEY") or ""
    msg = str(msg)
    return msg.replace(k, "***") if k else msg
status = {"asof": today, "mode": "demo" if a.demo else "live", "books": [], "calls": 0, "via": None, "result": None}
def write_status(result):
    status.update(result=result, calls=len(naru.CALLS), via=naru.base_used(),
                  generated=datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"))
    Path(a.status_out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.status_out).write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
isbns = load_list()
out = {"asof": today, "source": "정보나루 bookExist(관내) · libSrchByBook(전국) · 대출 상태는 조회일 전일 기준",
       "generated": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "holdings": {}, "nation": {}, "calls": 0, "partial": False}
naru.calls_reset()
for i, isbn in enumerate(isbns, 1):
    if not a.demo and len(naru.CALLS) + 17 > a.max_calls:          # 다음 도서가 상한을 넘길 수 있으면 여기서 멈춘다
        out["partial"] = True
        print(f"호출 상한({a.max_calls}) 근접 — {i-1}/{len(isbns)}종에서 멈춤")
        break
    try:
        h = naru.holdings_local(isbn, tools.CFG["libraries"], tools.CFG["region_code"], mode=tools.MODE)
        out["holdings"][isbn] = h
        if not any(v == "ok" for v in h.values()):
            n = naru.availability_nation(isbn, mode=tools.MODE)
            out["nation"][isbn] = {"count": n.get("found_count", 0)}
        print(f"  {i:3d}. {isbn}  소장 {sum(1 for v in h.values() if v != 'none'):2d}관 · 대출가능 {sum(1 for v in h.values() if v == 'ok'):2d}관")
        status["books"].append({"isbn": isbn, "ok": True, "owned": sum(1 for v in h.values() if v != "none"),
                                "available": sum(1 for v in h.values() if v == "ok")})
    except Exception as e:
        err = redact(f"{type(e).__name__}: {e}")
        print(f"  {i:3d}. {isbn}  실패: {err}")
        status["books"].append({"isbn": isbn, "ok": False, "error": err})
        out["partial"] = True
out["calls"] = len(naru.CALLS)
if not out["holdings"]:
    write_status("실패 — 받은 데이터 없음(키·한도·네트워크 확인)")
    sys.exit("받은 데이터가 없어 파일을 쓰지 않습니다(키·한도·네트워크 확인). 까닭은 lab/out/refresh_status.json")
write_status("일부" if out["partial"] else "성공")
for path in (a.out, a.web_out):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"저장: {a.out} · {a.web_out}  ({len(out['holdings'])}종 · 호출 {out['calls']}회 · {'일부' if out['partial'] else '전부'} · {today})")
