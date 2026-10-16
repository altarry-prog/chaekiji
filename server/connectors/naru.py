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
※ 대출 가능 여부는 API 사양상 「조회일 기준 전날」 상태다(Open API 매뉴얼 v20260210, 35쪽).

v0.3.4 (상담 비서 판, 2026. 10.)
- relay 모드: 키가 없는 쪽(심사위원·다른 기관)이 우리 중계(relay/)에 물어 오늘 데이터를 받는다.
  중계가 응답하지 않으면 그 호출만 픽스처로 떨어지고 근거 문구에 그 사실을 적는다.
- LAST_META.asof: 어느 모드든 「몇 월 며칠 조회분」인지 날짜를 함께 돌려준다(안내문의 전일 기준 표시용).
- snapshot: lab/refresh_today.py가 매일 써 두는 fixtures/holdings-today.json(어제 기준 조회분)을 읽는다.
  auto 모드는 중계 → 신선한 스냅샷(2일 이내) → 8/18 픽스처 순으로 고른다. relay 모드도 스냅샷에 있는 책은 중계를 부르지 않는다(한도 절약)."""
import json, os, time, datetime, socket, urllib.error, urllib.parse, urllib.request
from pathlib import Path

FIX = Path(__file__).resolve().parent.parent / "fixtures"
_cat = json.load(open(FIX/"catalog.json", encoding="utf-8"))
_hold = json.load(open(FIX/"holdings.json", encoding="utf-8"))

# 매뉴얼(v20260210)의 호출 주소는 http://data4library.kr/api/ 다. https를 먼저 시도하고, 연결이 안 되면 http로 넘어가
# 처음 통한 주소를 기억한다(키가 실리는 주소라 https를 앞에 둔다). NARU_BASE 환경변수로 하나만 지정할 수도 있다.
BASES = [os.environ["NARU_BASE"]] if os.environ.get("NARU_BASE") else ["https://data4library.kr/api/", "http://data4library.kr/api/"]
BASE = BASES[0]
_BASE_OK = None                                       # 처음 통한 주소(https/http)
KST = datetime.timezone(datetime.timedelta(hours=9))   # 조회일은 한국 날짜로(깃허브 서버는 UTC)
EXACT = os.environ.get("NARU_EXACT", "true")          # 매뉴얼: true/false. 8월 실측 코드는 Y — probe로 확인
CALLS = []                                            # 호출 계측 [{"api","ms","at"}] — live 호출만 기록
LAST_META = {}                                        # 마지막 holdings_local의 부가 정보(소장관 수·호출 수)
_HOLD_CACHE = {}                                      # {(isbn, region): (time, dict)} — 같은 ISBN 재조회 절약
_BIB_CACHE = {}                                       # {isbn: 서지} — 검색 결과를 서지 조회에 재사용(호출 절약)
CACHE_SEC = 600
FIX_ASOF = "2026-08-18"                               # 픽스처 실측일
SNAPSHOT_PATH = Path(os.environ.get("CHAEKIJI_SNAPSHOT") or (FIX / "holdings-today.json"))
SNAPSHOT_MAX_DAYS = 2
try:
    _snap = json.load(open(SNAPSHOT_PATH, encoding="utf-8")) if SNAPSHOT_PATH.exists() else None
except Exception:
    _snap = None

def snapshot_fresh() -> bool:
    """오늘 조회분 파일이 있고 2일 안쪽이면 참(대출 상태는 어차피 전일 기준이라 하루 지난 것까지 쓴다)."""
    if not _snap or not _snap.get("holdings"): return False
    try:
        d = datetime.date.fromisoformat(_snap["asof"])
    except Exception:
        return False
    return 0 <= (datetime.datetime.now(KST).date() - d).days <= SNAPSHOT_MAX_DAYS

def _snapshot_holdings(isbn13, libraries):
    if not snapshot_fresh(): return None
    h = _snap["holdings"].get(isbn13)
    if h is None: return None
    return {name: h.get(name, "none") for name in libraries}
RELAY = ""                                            # 중계 주소 — tools.py가 환경변수·설정에서 넣어 준다
RELAY_TIMEOUT = 8

def _norm(s): return "".join(s.split()).lower()

_REQ_PHRASES = ["빌리고 싶어요", "빌리고 싶은데요", "빌리고 싶습니다", "빌릴 수 있어요", "빌릴 수 있나요", "빌릴 수 있을까요",
                "빌릴수있어요", "빌릴수있나요", "찾아 주세요", "찾아주세요", "찾아줘", "찾아 줘", "있나요", "있어요", "있을까요",
                "있습니까", "보고 싶어요", "읽고 싶어요", "대출 되나요", "대출되나요", "대출할 수 있나요", "신청해 주세요",
                "신청해주세요", "신청할게요", "부탁해요", "부탁드려요", "부탁합니다", "주세요", "가져다 줄 수 있어요",
                "가져다줄 수 있어요", "상호대차", "그 왜", "그거", "라는 책", "이라는 책", "하는 책", "인가 하는"]
def clean_title(utterance: str) -> str:
    """발화에서 요청 말투를 걷어 제목 비슷한 것만 남긴다(정보나루 제목 검색용). 모델이 제목만 넘기면 그대로 통과."""
    t = " " + " ".join(str(utterance).split()) + " "
    for ph in sorted(_REQ_PHRASES, key=len, reverse=True):
        t = t.replace(" " + ph + " ", " ").replace(ph, " ") if ph in t else t
    t = t.replace("?", " ").replace(".", " ").replace("!", " ")
    t = " ".join(t.split())
    if t.endswith(" 책"): t = t[:-2].rstrip()                   # 낱말 「책」은 떼고, 「그림책」처럼 붙은 것은 둔다
    for suf in ("이라고", "라고", "이란", "란", "은", "는", "을", "를", "이", "가"):
        if len(t) > 3 and t.endswith(suf) and not t.endswith(" " + suf):
            t = t[: -len(suf)].rstrip(); break
    return t or str(utterance)
def _today(): return datetime.datetime.now(KST).date().isoformat()

# ── 중계(relay/) 호출 — 키 없이 오늘 데이터 ─────────────────────────
def relay_ok(timeout=3):
    """중계가 살아 있고 키를 갖고 있는지만 본다(키 값은 오가지 않는다)."""
    if not RELAY: return False
    try:
        with urllib.request.urlopen(RELAY.rstrip("/") + "/health", timeout=timeout) as r:
            return json.load(r).get("ok") is True
    except Exception:
        return False

def _relay(path, **params):
    url = RELAY.rstrip("/") + path + ("?" + urllib.parse.urlencode(params) if params else "")
    t0 = time.perf_counter()
    with urllib.request.urlopen(url, timeout=RELAY_TIMEOUT) as r:
        data = json.load(r)
    CALLS.append({"api": "relay" + path, "ms": round((time.perf_counter() - t0) * 1000),
                  "at": datetime.datetime.now().strftime("%H:%M:%S")})
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"중계 응답 오류({path}): {data['error']}")
    return data

def _relay_search(utterance=None, isbn13=None):
    r = _relay("/search", **({"isbn": isbn13} if isbn13 else {"q": utterance}))
    docs = r.get("docs", [])
    for x in docs:
        if x.get("isbn13"): _BIB_CACHE[x["isbn13"]] = {**x, "type": "일반", "new_arrival": False,
                                                       "basis": "정보나루 srchBooks(중계) — 자료유형·신착은 미제공(판정 보류)"}
    return docs

# ── 계측 ──────────────────────────────────────────────────────────
def calls_reset(): CALLS.clear()

def base_used():
    """지금까지 통한 정보나루 주소 종류(https/http) — 없으면 None."""
    return None if not _BASE_OK else ("https" if _BASE_OK.startswith("https") else "http")
def calls_summary():
    by = {}
    for c in CALLS: by[c["api"]] = by.get(c["api"], 0) + 1
    return {"total": len(CALLS), "by_api": by, "ms_total": sum(c["ms"] for c in CALLS)}

# ── 공개 함수 (demo/live 같은 모양) ────────────────────────────────
def search(utterance: str, mode="demo"):
    if mode == "live":
        return _live_search(utterance)
    if mode == "relay":
        fx = search(utterance, mode="demo")           # 실측 서지 5종은 픽스처가 먼저(시연 도서는 늘 같은 답)
        if fx.get("found"):
            fx["evidence"] = "정보나루 srchBooks(실측 서지 픽스처) · 소장·대출 상태는 중계로 오늘 조회"
            return fx
        title = clean_title(utterance)
        try:
            docs = _relay_search(utterance=title)
            if docs:
                d = docs[0]
                return {"found": True, "isbn13": d["isbn13"], "title": d.get("title"), "author": d.get("author"),
                        "publisher": d.get("publisher"), "year": d.get("year"),
                        "candidates": [x["isbn13"] for x in docs if x.get("isbn13")], "query": title,
                        "confidence": 0.85, "evidence": "정보나루 srchBooks(중계 · 전국 서지 · 제목 부분일치)"}
            return {"found": False, "reason": f"정보나루 서지 검색 결과 없음(검색어 「{title}」) — 제목·저자를 더 알려 주세요",
                    "candidates": [], "query": title}
        except Exception:
            return {"found": False, "reason": f"중계 응답 없음 — 픽스처 5종에도 없는 도서(검색어 「{title}」)", "candidates": []}
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
    if isbn13 in _BIB_CACHE:                          # 방금 검색으로 받은 서지면 다시 부르지 않는다
        return _BIB_CACHE[isbn13]
    if mode == "relay":
        try:
            _relay_search(isbn13=isbn13)
        except Exception:
            pass
        return _BIB_CACHE.get(isbn13, {})
    if mode != "live":
        return {}
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
    yday = (datetime.datetime.now(KST).date() - datetime.timedelta(days=1)).isoformat()
    if mode == "live":
        return _live_nation(isbn13)
    if mode == "snapshot" or (mode == "relay" and snapshot_fresh() and isbn13 in (_snap.get("nation") or {})):
        n = (_snap.get("nation") or {}).get(isbn13) if snapshot_fresh() else None
        if n is not None:
            return {"basis": f"전일 기준 · 정보나루(매일 갱신 · {_snap['asof']} 조회)", "found_count": n.get("count", 0),
                    "note": "경기 광역 예시", "asof": _snap["asof"]}
        if mode == "snapshot":
            return availability_nation(isbn13, mode="demo")
    if mode == "relay":
        try:
            r = _relay("/nation", isbn=isbn13)
            return {"basis": f"전일 기준 · 정보나루(중계 · {r.get('asof', _today())} 조회)",
                    "found_count": r.get("found_count", 0), "note": "경기 광역 예시", "asof": r.get("asof")}
        except Exception:
            out = availability_nation(isbn13, mode="demo"); out["note"] += " · 중계 응답 없음 → 픽스처로 복귀"
            return out
    n = _hold.get("nation", {}).get(isbn13)
    return {"basis": f"전일({yday}) 기준 · 정보나루", "found_count": (n or {}).get("count", 0),
            "note": (n or {}).get("note", "전국 조회(모의)")}

def holdings_local(isbn13: str, libraries: dict, region_code: str, mode="demo") -> dict:
    """[v0.3.1] 관내 소장·대출 상태 {관이름: ok|busy|none}.
    demo: 8/18 실측 픽스처 / live: libSrchByBook(세부지역) 1회 → 소장관마다 bookExist 1회.
    호출 수 = 1 + 소장관 수 (설계 문서의 「17회 → 소장관 수 + 1회」가 이 함수다).
    같은 ISBN을 10분 안에 다시 물으면 캐시로 답한다(check_availability → check_policy 연속 호출 절약)."""
    global LAST_META
    if mode in ("relay", "snapshot"):
        sh = _snapshot_holdings(isbn13, libraries)        # 오늘 조회분에 있으면 그걸로(중계 호출·한도 절약)
        if sh is not None:
            LAST_META = {"basis": f"관내: 정보나루 bookExist(매일 갱신 · {_snap['asof']} 조회 · 전일 기준)", "asof": _snap["asof"],
                         "holding_count": sum(1 for v in sh.values() if v != "none"), "calls": 0, "cached": True}
            return sh
        if mode == "snapshot":
            out = holdings_local(isbn13, libraries, region_code, mode="demo")
            LAST_META["basis"] += " · 오늘 조회분에 없는 도서"
            return out
    if mode == "relay":
        key = ("relay", isbn13, region_code)
        hit = _HOLD_CACHE.get(key)
        if hit and time.time() - hit[0] < CACHE_SEC:
            LAST_META = dict(hit[2], cached=True)
            return dict(hit[1])
        try:
            r = _relay("/holdings", isbn=isbn13)
            libs = r.get("libs", {})
            out = {name: libs.get(str(code), "none") for name, code in libraries.items()}
            asof = r.get("asof") or _today()
            LAST_META = {"basis": f"관내: 정보나루 bookExist(중계 · {asof} 조회 · 전일 기준)", "asof": asof,
                         "holding_count": sum(1 for v in out.values() if v != "none"),
                         "calls": r.get("calls"), "cached": bool(r.get("cached"))}
            _HOLD_CACHE[key] = (time.time(), dict(out), dict(LAST_META))
            return out
        except Exception:
            out = holdings_local(isbn13, libraries, region_code, mode="demo")
            LAST_META["basis"] += " · 중계 응답 없음 → 픽스처로 복귀"
            return out
    if mode != "live":
        h = _hold.get("holdings", {}).get(isbn13, {})
        out = {name: h.get(name, "none") for name in libraries}
        LAST_META = {"basis": "관내: 정보나루 bookExist(2026. 8. 18. 실측 픽스처 · 전일 기준)", "asof": FIX_ASOF,
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
    LAST_META = {"basis": f"관내: 정보나루 bookExist(live · {_today()} 조회 · 전일 기준)", "asof": _today(),
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
    """정보나루 Open API 1회 호출. 키는 URL에만 실리고 어디에도 기록되지 않는다.
    https가 연결되지 않으면 http(매뉴얼 주소)로 한 번 더 — 처음 통한 주소를 기억해 다음부터는 그것만 쓴다."""
    global _BASE_OK
    params["authKey"] = _key()
    params["format"] = "json"
    q = urllib.parse.urlencode(params)
    bases = [_BASE_OK] if _BASE_OK else BASES
    last = None
    for i, base in enumerate(bases):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(base + api + "?" + q, timeout=20 if i == len(bases) - 1 else 8) as r:
                data = json.load(r)
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            last = e
            continue
        _BASE_OK = base
        break
    else:
        why = getattr(last, "reason", None) or getattr(last, "code", None) or last
        raise RuntimeError(f"정보나루 연결 실패({api}): {type(last).__name__}: {why}")
    CALLS.append({"api": api, "ms": round((time.perf_counter() - t0) * 1000),
                  "at": datetime.datetime.now(KST).strftime("%H:%M:%S"),
                  "via": "https" if _BASE_OK.startswith("https") else "http"})
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
