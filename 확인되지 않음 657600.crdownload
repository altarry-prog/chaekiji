#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책이지 정보나루 중계 — 파이썬 표준 라이브러리 판 (도서관 PC·실험실 VM에서 바로 실행, 의존성 0).
worker.js와 같은 경로·같은 응답 모양. 인증키는 환경변수 NARU_KEY로만 받는다.

실행:  set NARU_KEY=...   (윈도우)  /  export NARU_KEY=...  (리눅스)
       python relay.py            → http://127.0.0.1:8787
점검:  curl http://127.0.0.1:8787/health
경로:  /holdings?isbn=  /search?q=|isbn=  /nation?isbn=  /health   (worker.js와 같다)
"""
import os, sys, json, time, re, urllib.request, urllib.parse, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ALLOW_ORIGINS = {"https://altarry-prog.github.io", "http://localhost:8080", "http://127.0.0.1:8080"}
LIBS = ["141321","141065","141248","141583","141315","141652","141056","141559",
        "141651","141043","141603","141660","141584","141535","141115","141151"]
REGION, DTL_REGION = "31", "31050"
RATE_LIMIT, CACHE_SEC, PORT = 60, 600, int(os.environ.get("PORT", "8787"))
_hits, _cache = {}, {}

def naru(api, key, **p):
    p.update(authKey=key, format="json")
    with urllib.request.urlopen("https://data4library.kr/api/%s?%s" % (api, urllib.parse.urlencode(p)), timeout=20) as r:
        d = json.load(r)
    return d.get("response", d)

def search(q, isbn, key):
    params = {"isbn13": isbn, "pageSize": 1} if isbn else {"title": q, "exactMatch": "false", "pageSize": 5}
    r = naru("srchBooks", key, **params)
    docs = []
    for x in r.get("docs", []):
        d = x.get("doc", x)
        if d.get("isbn13"):
            docs.append({"isbn13": str(d["isbn13"]), "title": d.get("bookname"), "author": d.get("authors"),
                         "publisher": d.get("publisher"), "year": d.get("publication_year")})
    return {"query": isbn or q, "docs": docs, "asof": str(datetime.date.today()), "basis": "정보나루 srchBooks"}

def nation(isbn, key):
    r = naru("libSrchByBook", key, isbn=isbn, region=REGION, pageSize=200)
    return {"isbn": isbn, "found_count": len(r.get("libs", [])), "asof": str(datetime.date.today()),
            "basis": "정보나루 libSrchByBook(경기 광역 예시) · 전일 기준"}

def holdings(isbn, key):
    r1 = naru("libSrchByBook", key, isbn=isbn, region=REGION, dtl_region=DTL_REGION, pageSize=300)
    have = []
    for l in r1.get("libs", []):
        lib = l.get("lib", l); c = str(lib.get("libCode", ""))
        if c in LIBS: have.append(c)
    libs = {c: "none" for c in LIBS}
    for c in have:
        r = naru("bookExist", key, libCode=c, isbn13=isbn).get("result", {})
        if r.get("hasBook") == "Y": libs[c] = "ok" if r.get("loanAvailable") == "Y" else "busy"
    return {"isbn": isbn, "asof": str(datetime.date.today()),
            "basis": "정보나루 bookExist · 대출 상태는 조회일 전일 기준", "libs": libs, "calls": 1 + len(have)}

class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):   # 로그에 쿼리(ISBN)만 남고 키는 애초에 URL에 없다
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % a))
    def _send(self, obj, status=200):
        origin = self.headers.get("Origin", "")
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Cache-Control", "no-store")
        if origin in ALLOW_ORIGINS: self.send_header("Access-Control-Allow-Origin", origin); self.send_header("Vary", "Origin")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_OPTIONS(self):
        self.send_response(204); origin = self.headers.get("Origin", "")
        if origin in ALLOW_ORIGINS: self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET"); self.end_headers()
    def do_GET(self):
        key = os.environ.get("NARU_KEY")
        if not key: return self._send({"error": "relay-not-configured"}, 503)
        origin = self.headers.get("Origin", "")
        if origin and origin not in ALLOW_ORIGINS: return self._send({"error": "origin"}, 403)
        u = urllib.parse.urlparse(self.path)
        if u.path == "/health": return self._send({"ok": True, "keyed": True, "region": DTL_REGION})
        if u.path not in ("/holdings", "/search", "/nation"): return self._send({"error": "not-found"}, 404)
        ip = self.client_address[0]; now = time.time()
        arr = [t for t in _hits.get(ip, []) if now - t < 600]
        if len(arr) >= RATE_LIMIT: return self._send({"error": "rate-limit"}, 429)
        arr.append(now); _hits[ip] = arr
        qs = urllib.parse.parse_qs(u.query)
        isbn = re.sub(r"\D", "", qs.get("isbn", [""])[0]); q = qs.get("q", [""])[0].strip()[:80]
        if u.path == "/search":
            if not isbn and len(q) < 2: return self._send({"error": "query"}, 400)
            key_ = f"s:{isbn}" if isbn else f"q:{q}"
        else:
            if not re.fullmatch(r"97[89]\d{10}", isbn): return self._send({"error": "isbn"}, 400)
            key_ = f"{u.path}:{isbn}"
        hit = _cache.get(key_)
        if hit and now - hit[0] < CACHE_SEC: return self._send(dict(hit[1], cached=True))
        try:
            v = holdings(isbn, key) if u.path == "/holdings" else search(q, isbn, key) if u.path == "/search" else nation(isbn, key)
            _cache[key_] = (now, v); self._send(dict(v, cached=False))
        except Exception:
            self._send({"error": "upstream"}, 502)

if __name__ == "__main__":
    if not os.environ.get("NARU_KEY"):
        sys.exit("NARU_KEY 환경변수(정보나루 인증키)가 없어 기동하지 않습니다 — 코드·파일에 키를 쓰지 마세요.")
    print(f"책이지 중계 가동: http://127.0.0.1:{PORT}  (/health · /holdings?isbn=…)")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
