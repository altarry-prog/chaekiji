# -*- coding: utf-8 -*-
"""정보나루 커넥터 — 조회 계층.
demo 모드: 2026. 8. 18. 실측 픽스처로 응답 (네트워크 없음).
live 모드: 실제 Open API 호출 (NARU_KEY 환경변수 필요 — 코드·설정파일에 키를 쓰지 않는다).
어느 모드든 응답 모양은 같다 — 이것이 커넥터의 요점.

v0.3.1 (실험실 판, 2026. 9.)
- holdings_local(): 관내 소장·대출 상태를 정보나루로 조회 (libSrchByBook 1회 + 소장관별 bookExist)
  → 알파스 모의 커넥터와 같은 모양({관이름: ok|busy|none})으로 돌려준다.
- CALLS: 실제 HTTP 호출을 한 건씩 계측(어떤 API, 몇 ms). lab/measure.py가 읽는다.
- NARU_EXACT 환경변수: srchBooks의 exactMatch 값(기본 true). lab/naru_probe.py가 맞는 값을 알려준다.
- bibinfo(): live 모드에서 픽스처에 없는 ISBN은 srchBooks(isbn13)로 서지를 받는다.
※ 대출 가능 여부는 API 사양상 「조회일 기준 전날」 상태다(Open API 매뉴얼 v20260210, 35쪽)."""
import json, os, time, datetime, urllib.parse, urllib.request
from pathlib import Path

FIX = Path(__file__).resolve().parent.parent / "fixtures"
_cat = json.load(open(FIX/"catalog.json", encoding="utf-8"))
_hold = json.load(open(FIX/"holdings.json", encoding="utf-8"))

BASE = "https://data4library.kr/api/"
EXACT = os.environ.get("NARU_EXACT", "true")          # 매뉴얼: true/false. 8월 실측 코드는 Y — probe로 확인
CALLS = []                                            # 호출 계측 [{"api","ms","at"}] — live 호출만 기록
LAST_META = {}                                        # 마지막 holdings_local의 부가 정보(소장관 수·호출 수)
_HOLD_CACHE = {}                                      # {(isbn, region): (time, dict)} — 같은 ISBN 재조회 절약
_BIB_CACHE = {}                                       # {isbn: 서지} — 검색 결과를 서지 조회에 재사용(호출 절약)
CACHE_SEC = 600

def _norm(s): return "".join(s.split()).lower()

# ── 계측 ──────────────────────────────────────────────────────────
def calls_reset(): CALLS.clear()
def calls_summary():
    by = {}
    for c in CALLS: by[c["api"]] = by.get(c["api"], 0) + 1
    return {"total": len(CALLS), "by_api": by, "ms_total": sum(c["ms"] for c in CALLS)}

# ── 공개 함수 (demo/live 같은 모양) ────────────────────────────────
def search(utterance: str, mode="demo"):
    if mode == "live":
        return _live_search(utterance)
    q = _norm(utterance)
    best = None
    for b in _cat["books"]:
        score = max((len(_norm(k)) for k in b["keys"] if _norm(k) in q), default=0)
        if score and (best is None or score > best[0]):
            best = (score, b)
    if not best:
        return {"found": False, "reason": "픽스처에 없는 도서(모의 모드 한계) — live 모드에서는 전국 서지 검색"}
    b = best[1]
    return {"found": True, "isbn13": b["isbn13"], "title": b["title"], "author": b["author"],
            "publisher": b["publisher"], "year": b["year"], "candidates": [b["isbn13"]],
            "confidence": 0.97, "evidence": "정보나루 srchBooks(모의 픽스처 · 실측 서지)"}

def bibinfo(isbn13: str, mode="demo"):
    """서지 1건 — 제외 규정 판정용(자료 유형·신착 여부).
    demo: 픽스처 / live: 픽스처에 있으면 그것, 없으면 srchBooks(isbn13) 1회.
    ※ 정보나루는 자료 유형(비도서 등)·신착 여부를 주지 않는다 → 그 판정은 도서관리시스템 연동의 몫."""
    for b in _cat["books"]:
        if b["isbn13"] == isbn13:
            return b
    if mode != "live":
        return {}
    if isbn13 in _BIB_CACHE:                          # 방금 검색으로 받은 서지면 다시 부르지 않는다
        return _BIB_CACHE[isbn13]
    resp = _get("srchBooks", isbn13=isbn13, pageSize=1)
    docs = resp.get("docs", [])
    if not docs: return {}
    d = docs[0].get("doc", docs[0])
    _BIB_CACHE[isbn13] = _bib_from_doc(d)
    return _BIB_CACHE[isbn13]

def _bib_from_doc(d):
    return {"isbn13": d.get("isbn13"), "title": d.get("bookname"), "author": d.get("authors"),
            "publisher": d.get("publisher"), "year": d.get("publication_year"),
            "type": "일반", "new_arrival": False,
            "basis": "정보나루 srchBooks(live) — 자료유형·신착은 미제공(판정 보류)"}

def availability_nation(isbn13: str, mode="demo"):
    yday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    if mode == "live":
        return _live_nation(isbn13)
    n = _hold.get("nation", {}).get(isbn13)
    return {"basis": f"전일({yday}) 기준 · 정보나루", "found_count": (n or {}).get("count", 0),
            "note": (n or {}).get("note", "전국 조회(모의)")}

def holdings_local(isbn13: str, libraries: dict, region_code: str, mode="demo") -> dict:
    """[v0.3.1] 관내 소장·대출 상태 {관이름: ok|busy|none}.
    demo: 8/18 실측 픽스처 / live: libSrchByBook(세부지역) 1회 → 소장관마다 bookExist 1회.
    호출 수 = 1 + 소장관 수 (설계 문서의 「17회 → 소장관 수 + 1회」가 이 함수다).
    같은 ISBN을 10분 안에 다시 물으면 캐시로 답한다(check_availability → check_policy 연속 호출 절약)."""
    global LAST_META
    if mode != "live":
        h = _hold.get("holdings", {}).get(isbn13, {})
        out = {name: h.get(name, "none") for name in libraries}
        LAST_META = {"basis": "관내: 정보나루 bookExist(2026. 8. 18. 실측 픽스처 · 전일 기준)",
                     "holding_count": sum(1 for v in out.values() if v != "none"), "calls": 0, "cached": False}
        return out
    key = (isbn13, region_code)
    hit = _HOLD_CACHE.get(key)
    if hit and time.time() - hit[0] < CACHE_SEC:
        LAST_META = dict(hit[2], cached=True)
        return dict(hit[1])
    n0 = len(CALLS)
    region = region_code[:2]
    resp = _get("libSrchByBook", isbn=isbn13, region=region, dtl_region=region_code, pageSize=300)
    code2name = {str(v): k for k, v in libraries.items()}
    holding = []
    for l in resp.get("libs", []):
        lib = l.get("lib", l)
        code = str(lib.get("libCode", ""))
        if code in code2name:
            holding.append(code2name[code])
    out = {name: "none" for name in libraries}
    for name in holding:
        r = _get("bookExist", libCode=libraries[name], isbn13=isbn13).get("result", {})
        if r.get("hasBook") == "Y":
            out[name] = "ok" if r.get("loanAvailable") == "Y" else "busy"
    LAST_META = {"basis": "관내: 정보나루 bookExist(live · 전일 기준)",
                 "holding_count": len(holding), "calls": len(CALLS) - n0, "cached": False,
                 "region_libs_found": len(resp.get("libs", []))}
    _HOLD_CACHE[key] = (time.time(), dict(out), dict(LAST_META))
    return out

# ── live 모드 ─────────────────────────────────────────────────────
def _key():
    k = os.environ.get("NARU_KEY")
    if not k: raise RuntimeError("live 모드에는 NARU_KEY 환경변수(정보나루 인증키)가 필요합니다 — read -s NARU_KEY; export NARU_KEY")
    return k

def _get(api, **params):
    """정보나루 Open API 1회 호출. 키는 URL에만 실리고 어디에도 기록되지 않는다."""
    params["authKey"] = _key()
    params["format"] = "json"
    url = BASE + api + "?" + urllib.parse.urlencode(params)
    t0 = time.perf_counter()
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.load(r)
    CALLS.append({"api": api, "ms": round((time.perf_counter() - t0) * 1000),
                  "at": datetime.datetime.now().strftime("%H:%M:%S")})
    resp = data.get("response", data)
    if isinstance(resp, dict) and resp.get("error"):
        raise RuntimeError(f"정보나루 응답 오류({api}): {resp['error']}")
    return resp

def _live_search(utterance):
    resp = _get("srchBooks", title=utterance, exactMatch=EXACT, pageSize=5)
    docs = resp.get("docs", [])
    if not docs: return {"found": False, "reason": "일치 결과 없음", "candidates": []}
    ds = [d.get("doc", d) for d in docs]
    for x in ds:
        if x.get("isbn13"): _BIB_CACHE[x["isbn13"]] = _bib_from_doc(x)
    d = ds[0]
    return {"found": True, "isbn13": d["isbn13"], "title": d["bookname"], "author": d["authors"],
            "publisher": d["publisher"], "year": d["publication_year"],
            "candidates": [x["isbn13"] for x in ds if x.get("isbn13")],   # 판본 ISBN 후보(대출순)
            "confidence": 0.9, "evidence": f"정보나루 srchBooks(title · exactMatch={EXACT}, live)"}

def _live_nation(isbn13):
    resp = _get("libSrchByBook", isbn=isbn13, region="31", pageSize=200)
    libs = resp.get("libs", [])
    return {"basis": "전일 기준 · 정보나루(live)", "found_count": len(libs), "note": "경기 광역 예시"}
