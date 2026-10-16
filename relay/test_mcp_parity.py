#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""원격 상담 비서(relay/mcp.js)와 파이썬 참조 서버(server/, relay 모드)가 같은 입력에 같은 답을 내는지 맞춰 본다.

두 판에 같은 시나리오(relay/test_mcp_scenarios.json)를 준다.
  파이썬 판: server/server.py를 relay 모드로 띄우고, 이 스크립트가 띄운 모의 중계에 묻게 한다.
  원격 판:   node relay/test_mcp_parity.mjs — worker.js의 /mcp에 같은 사례를 보내고, 모의 정보나루가 답한다.
  매일 갱신 자료(스냅샷)도 같은 내용을 두 판에 준다(파이썬: 파일, 원격: 시연 웹 주소를 모의).
판정·안내문·접수 메모·근거 문구·공식 누리집 링크까지 글자 하나 다르지 않아야 통과. 네트워크·키 불필요.
실행: python3 relay/test_mcp_parity.py"""
import datetime, json, os, subprocess, sys, tempfile, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SC = json.load(open(ROOT / "relay" / "test_mcp_scenarios.json", encoding="utf-8"))
KST = datetime.timezone(datetime.timedelta(hours=9))
TODAY = datetime.datetime.now(KST).date().isoformat()
SNAP = dict(SC["snapshot"], asof=TODAY)
CODES = ["141321", "141065", "141248", "141583", "141315", "141652", "141056", "141559",
         "141651", "141043", "141603", "141660", "141584", "141535", "141115", "141151"]
BOOKS = [b for docs in SC["books"].values() for b in docs]


class Relay(BaseHTTPRequestHandler):
    """worker.js와 같은 모양으로 답하는 모의 중계 — 값은 시나리오에서."""
    def log_message(self, *a): pass

    def send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = dict(urllib.parse.parse_qsl(u.query))
        isbn = q.get("isbn", "")
        if u.path == "/health": return self.send(200, {"ok": True, "keyed": True})
        if isbn and isbn in SC.get("fail", []): return self.send(502, {"error": "upstream", "detail": ["http:TypeError"]})
        if u.path == "/search":
            docs = SC["books"].get(q.get("q", ""), []) if not isbn else [b for b in BOOKS if b["isbn13"] == isbn][:1]
            return self.send(200, {"query": isbn or q.get("q"), "docs": docs, "asof": TODAY, "basis": "정보나루 srchBooks", "cached": False})
        if u.path == "/holdings":
            held = SC["libs"].get(isbn, {})
            return self.send(200, {"isbn": isbn, "asof": TODAY, "basis": "정보나루 bookExist · 대출 상태는 조회일 전일 기준",
                                   "libs": {c: held.get(c, "none") for c in CODES}, "calls": 1 + len(held), "cached": False})
        if u.path == "/nation":
            return self.send(200, {"isbn": isbn, "found_count": SC.get("nation", {}).get(isbn, 0), "asof": TODAY, "cached": False})
        return self.send(404, {"error": "not-found"})


def python_side(relay_url, snap_path):
    env = dict(os.environ, CHAEKIJI_MODE="relay", CHAEKIJI_RELAY=relay_url, CHAEKIJI_SNAPSHOT=str(snap_path),
               CHAEKIJI_CONFIG=str(ROOT / "server" / "config" / "bucheon.yaml"), PYTHONUTF8="1")
    for k in ("CHAEKIJI_STORE", "CHAEKIJI_AUDIT", "CHAEKIJI_LOCAL_SOURCE", "NARU_KEY"):
        env.pop(k, None)
    lines = [json.dumps({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})]
    for i, c in enumerate(SC["cases"], 1):
        lines.append(json.dumps({"jsonrpc": "2.0", "id": i, "method": "tools/call",
                                 "params": {"name": c["tool"], "arguments": c["args"]}}, ensure_ascii=False))
    p = subprocess.run([sys.executable, str(ROOT / "server" / "server.py")], input="\n".join(lines) + "\n",
                       capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(ROOT / "server"), timeout=120)
    replies = {json.loads(l)["id"]: json.loads(l) for l in p.stdout.splitlines() if l.strip()}
    out = []
    for i, c in enumerate(SC["cases"], 1):
        res = replies[i]["result"]; text = res["content"][0]["text"]
        out.append({"tool": c["tool"], "args": c["args"], "isError": res["isError"], "result": text if res["isError"] else json.loads(text)})
    return out


def diff(a, b, path=""):
    if type(a) != type(b): return [f"{path}: 형 다름 {type(a).__name__} ≠ {type(b).__name__} ({a!r} / {b!r})"]
    if isinstance(a, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b: out.append(f"{path}.{k}: 한쪽에만 있음 ({a.get(k, '∅')!r} / {b.get(k, '∅')!r})")
            else: out += diff(a[k], b[k], f"{path}.{k}")
        return out
    if isinstance(a, list):
        if len(a) != len(b): return [f"{path}: 길이 다름 {len(a)} ≠ {len(b)} ({a!r} / {b!r})"]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in diff(x, y, f"{path}[{i}]")]
    return [] if a == b else [f"{path}: {a!r} ≠ {b!r}"]


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Relay)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory() as td:
        snap = Path(td) / "snap.json"; snap.write_text(json.dumps(SNAP, ensure_ascii=False), encoding="utf-8")
        scp = Path(td) / "sc.json"; scp.write_text(json.dumps(SC, ensure_ascii=False), encoding="utf-8")
        py = python_side(f"http://127.0.0.1:{srv.server_port}", snap)
        js_run = subprocess.run(["node", str(ROOT / "relay" / "test_mcp_parity.mjs"), str(scp), str(snap)],
                                capture_output=True, text=True, encoding="utf-8", timeout=120)
        if js_run.returncode != 0:
            sys.exit("원격 판 실행 실패:\n" + js_run.stderr[-2000:])
        js = json.loads(js_run.stdout)
    srv.shutdown()
    bad = 0
    for c, p, j in zip(SC["cases"], py, js):
        d = diff(p, j)
        label = f"{c['tool']} 「{c['args'].get('utterance') or c['args'].get('isbn13')}」 — {c['why']}"
        if d:
            bad += 1; print("  ✗ " + label); [print("      " + x) for x in d[:8]]
        else:
            r = p["result"]; tail = r if p["isError"] else (r.get("route") or ("찾음" if r.get("found") else r.get("home_status")))
            print(f"  ✓ {label} → {str(tail)[:40]}")
    if bad:
        sys.exit(f"\n파이썬 판과 다른 답 {bad}건")
    print(f"\n파이썬 판 대조 {len(py)}건 — 판정·안내문·접수 메모·근거·링크가 모두 같음")


if __name__ == "__main__":
    main()
