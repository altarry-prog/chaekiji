#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 몫 다시 재기(11. 5.)용 「한 번 받아 두고 다시 쓰는」 중계 — 정보나루 하루 한도를 지키면서 시연 도서 밖 책으로 잰다.

무엇을 하나: 책이지 중계(relay/worker.js)와 같은 주소(/health · /search · /holdings · /nation)로 답하는 작은 서버.
  요청이 오면 먼저 받아 둔 자료(캐시 파일)에서 찾고, 없을 때만 진짜 중계에 한 번 물어 그 답을 캐시에 적는다.
  그래서 모델 3종 × 3회가 같은 책을 물어도 정보나루는 처음 한 번만 불리고, 모든 회차가 같은 자료로 판정된다
  (도구의 판정이 자료 차이로 흔들리지 않게 해서, 모델이 맡는 몫만 따로 보이게 한다).
한도: AI_LIVE_MAX(정보나루 호출 수, 기본 60)를 넘으면 진짜 중계를 부르지 않고 502로 답한다. 서버는 이것을 「조회 불가」로 처리하고,
  기록에는 그 건이 예산 때문에 확인 불가였다고 남는다(채점에서 따로 센다).
실행: python3 replay_relay.py --cache 캐시.json --port 8765 [--log 요청기록.ndjson]
  환경변수 AI_REAL_RELAY(기본 https://chaekiji-relay.altarry2.workers.dev) · AI_LIVE_MAX
인증키는 쓰지 않는다(키는 진짜 중계에만 있다). 개인정보 없음(책 제목·ISBN만 오간다)."""
import argparse, json, os, threading, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REAL = os.environ.get("AI_REAL_RELAY", "https://chaekiji-relay.altarry2.workers.dev").rstrip("/")
LIVE_MAX = int(os.environ.get("AI_LIVE_MAX", "60"))
UA = "chaekiji-ai-metrics/1 (replay relay; github actions)"
LOCK = threading.Lock()
STATE = {"live_calls": 0, "hits": 0, "misses": 0, "over": 0}


def key_of(path, q):
    return path + "?" + urllib.parse.urlencode(sorted((k, v) for k, v in q.items() if k in ("q", "isbn")))


class H(BaseHTTPRequestHandler):
    cache, cache_path, log_path = {}, None, None

    def log_message(self, *a):
        pass

    def send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def note(self, row):
        if self.log_path:
            with LOCK, open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({**row, "t": time.strftime("%H:%M:%S")}, ensure_ascii=False) + "\n")

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if u.path == "/health":
            return self.send(200, {"ok": True, "keyed": True, "replay": True})
        if u.path == "/stats":                              # 실측 도구가 끝에 읽어 기록에 남긴다(정보나루를 몇 번 불렀나)
            with LOCK:
                return self.send(200, {**STATE, "live_max": LIVE_MAX, "cached_keys": len(self.cache)})
        if u.path not in ("/search", "/holdings", "/nation"):
            return self.send(404, {"error": "not-found"})
        k = key_of(u.path, q)
        with LOCK:
            hit = self.cache.get(k)
        if hit is not None:
            with LOCK:
                STATE["hits"] += 1
            self.note({"key": k, "from": "cache", "status": hit["status"]})
            return self.send(hit["status"], hit["body"])
        cost = 16 if u.path == "/holdings" else 1           # 중계 /holdings는 시립도서관 16곳 bookExist
        with LOCK:
            if STATE["live_calls"] + cost > LIVE_MAX:
                STATE["over"] += 1
                over = True
            else:
                STATE["live_calls"] += cost
                over = False
        if over:
            self.note({"key": k, "from": "budget", "status": 502})
            return self.send(502, {"error": "upstream", "detail": ["replay:budget"]})
        with LOCK:
            STATE["misses"] += 1
        url = REAL + u.path + "?" + urllib.parse.urlencode(q)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                status, body = r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            status = e.code
            try:
                body = json.loads(e.read().decode("utf-8"))
            except Exception:
                body = {"error": "upstream", "detail": [f"http:{e.code}"]}
        except Exception as e:                              # 연결 실패는 캐시에 적지 않는다(다음에 다시 물을 수 있게)
            self.note({"key": k, "from": "live", "status": 502, "err": type(e).__name__})
            return self.send(502, {"error": "upstream", "detail": [f"replay:{type(e).__name__}"]})
        if status == 200:                                   # 성공한 답만 적어 둔다
            with LOCK:
                self.cache[k] = {"status": status, "body": body, "at": time.strftime("%Y-%m-%d %H:%M")}
                tmp = self.cache_path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self.cache, ensure_ascii=False, indent=0), encoding="utf-8")
                tmp.replace(self.cache_path)
        self.note({"key": k, "from": "live", "status": status, "calls": body.get("calls") if isinstance(body, dict) else None})
        return self.send(status, body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--log", default="")
    a = ap.parse_args()
    H.cache_path = Path(a.cache)
    H.cache = json.loads(H.cache_path.read_text(encoding="utf-8")) if H.cache_path.exists() else {}
    H.log_path = a.log or None
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"replay relay :{a.port} · 캐시 {len(H.cache)}건 · 정보나루 예산 {LIVE_MAX}회 · 진짜 중계 {REAL}", flush=True)
    try:
        srv.serve_forever()
    finally:
        print(json.dumps(STATE, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
