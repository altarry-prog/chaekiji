#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[v0.3.4] 중계(relay) 모드 시험 — 네트워크·인증키 없이, 이 PC 안에서 모의 중계를 띄워 돈다.
검증하는 것:
  ① auto 모드: 중계가 살아 있으면 relay, 죽어 있으면 demo로 스스로 고른다
  ② relay 모드의 상담 묶음: 소장·대출 상태가 중계(오늘 날짜)에서 오고, 안내문에 그 날짜가 찍힌다
  ③ 픽스처에 없는 책은 중계의 서지 검색으로 찾는다(요청 말투를 걷어낸 제목으로)
  ④ 중계가 도중에 죽으면 그 호출만 픽스처로 떨어지고 근거 문구에 남는다 — 픽스처에도 없는 책은 「미소장」이 아니라 「소장 확인 불가」(v0.3.5)
  ⑤ 응답 어디에도 인증키 문자열이 없다
  ⑥ 매일 갱신 스냅샷(lab/refresh_today.py 결과): 신선하면 auto가 snapshot을 고르고, 오래되면 무시하며, relay 모드에서도 스냅샷에 있는 책은 중계를 부르지 않는다
실행: python3 tests/run_relay.py"""
import subprocess, json, sys, os, threading, http.server, socketserver, datetime, urllib.parse, time, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
KST = datetime.timezone(datetime.timedelta(hours=9))   # 서버·갱신 스크립트와 같은 한국 날짜
TODAY = datetime.datetime.now(KST).date().isoformat()
FAKE_KEY = "FAKE-KEY-NEVER-LEAKS"
LIBS = ["141321","141065","141248","141583","141315","141652","141056","141559",
        "141651","141043","141603","141660","141584","141535","141115","141151"]

class MockRelay(http.server.BaseHTTPRequestHandler):
    """모의 중계 — 나미야(9788972756194)는 상동만 대출 가능, 채식주의자(9788936433598)는 꿈빛·원미 대출 가능."""
    def log_message(self, *a): pass
    def _send(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        u = urllib.parse.urlparse(self.path); qs = urllib.parse.parse_qs(u.query)
        if u.path == "/health": return self._send({"ok": True, "keyed": True})
        if u.path == "/holdings":
            isbn = qs.get("isbn", [""])[0]
            libs = {c: "none" for c in LIBS}
            if isbn == "9788972756194": libs["141321"] = "ok"
            if isbn == "9788936433598": libs["141065"] = "ok"; libs["141535"] = "ok"; libs["141321"] = "busy"
            if isbn == "9788954616515": return self._send({"error": "upstream", "detail": ["http:TypeError"]}, 502)   # 그 책 조회만 실패
            return self._send({"isbn": isbn, "asof": TODAY, "libs": libs, "calls": 3, "cached": False})
        if u.path == "/search":
            q = qs.get("q", [""])[0]; isbn = qs.get("isbn", [""])[0]
            docs = []
            if "채식주의자" in q or isbn == "9788936433598":
                docs = [{"isbn13": "9788936433598", "title": "채식주의자", "author": "한강 지음", "publisher": "창비", "year": "2007"}]
            if q == "흐르는 강물처럼": return self._send({"error": "upstream", "detail": ["http:TypeError"]}, 502)   # 서지 검색부터 실패
            if q == "희랍어 시간":
                docs = [{"isbn13": "9788954616515", "title": "희랍어 시간", "author": "한강", "publisher": "문학동네", "year": "2011"}]
            return self._send({"query": q or isbn, "docs": docs, "asof": TODAY})
        if u.path == "/nation":
            return self._send({"isbn": qs.get("isbn", [""])[0], "found_count": 12, "asof": TODAY})
        self._send({"error": "not-found"}, 404)

def serve(port):
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", port), MockRelay)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd

class Client:
    def __init__(self, **env):
        e = dict(os.environ, CHAEKIJI_CONFIG=str(ROOT/"config"/"bucheon.yaml"), **env)
        e.pop("CHAEKIJI_STORE", None); e.pop("CHAEKIJI_AUDIT", None)
        if "CHAEKIJI_SNAPSHOT" not in env:                                      # 기본은 스냅샷 없음 — 밖의 환경변수가 새어 들지 않게
            e["CHAEKIJI_SNAPSHOT"] = "/nonexistent/holdings-today.json"
        if "CHAEKIJI_LOCAL_SOURCE" not in env:
            e.pop("CHAEKIJI_LOCAL_SOURCE", None)
        self.p = subprocess.Popen([sys.executable, str(ROOT/"server.py")], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=e)
        self.n = 0
        self.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "relay-kit", "version": "0"}})
    def rpc(self, method, params=None):
        self.n += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}, ensure_ascii=False) + "\n")
        self.p.stdin.flush()
        return json.loads(self.p.stdout.readline())["result"]
    def call(self, name, **args):
        r = self.rpc("tools/call", {"name": name, "arguments": args})
        return json.loads(r["content"][0]["text"]) if not r.get("isError") else {"_error": r["content"][0]["text"]}
    def banner(self):
        self.p.stdin.close(); self.p.wait(timeout=5)
        return self.p.stderr.read()

PASS = 0
def ok(cond, label):
    global PASS
    assert cond, f"실패: {label}"
    PASS += 1; print(f"  ✓ {label}")

PORT = 8797
httpd = serve(PORT)
time.sleep(0.3)
RELAY = f"http://127.0.0.1:{PORT}"

print("── auto 모드 · 중계 살아 있음 ──")
c = Client(CHAEKIJI_MODE="auto", CHAEKIJI_RELAY=RELAY)
r = c.call("consult_request", utterance="나미야 잡화점의 기적 빌리고 싶어요", pickup="상동")
ok(r["mode"] == "relay", "① auto → relay 선택(중계 health 응답)")
ok(r["route"] == "visit" and r["availability"]["asof"] == TODAY,
   f"② 상담 묶음 — 소장·대출 상태가 중계(오늘 {TODAY})에서 옴 → 갈래 「{r['route_label']}」")
ok(TODAY.split("-")[0] in r["notice"] and "중계" in r["availability"]["basis"], "   안내문에 오늘 날짜 · 근거에 「중계」 표시")
r2 = c.call("consult_request", utterance="채식주의자 있나요?", pickup="상동")
ok(r2["found"] and r2["book"]["isbn13"] == "9788936433598" and r2["route"] == "ill" and r2["from_lib"] in ("꿈빛", "원미"),
   f"③ 픽스처에 없는 책 — 중계 서지 검색으로 찾음(『{r2['book']['title']}』) → {r2['route_label']} · 소장관 {r2['from_lib']}")
r3 = c.call("search_item", utterance="데미안이라는 책 있을까요")
ok(r3["found"] is False and r3.get("query") == "데미안", "   요청 말투를 걷어낸 검색어로 중계에 묻는다(「데미안」) · 없으면 못 찾음으로 정직하게")
r3b = c.call("search_item", utterance="채식주의자 상호대차 되나요?")
ok(r3b["found"] and r3b.get("query") == "채식주의자" and r3b["isbn13"] == "9788936433598",
   "   [10/18] 문장째 넘어온 「채식주의자 상호대차 되나요?」 → 검색어 「채식주의자」(「되나요」까지 걷어냄)")
r3c = c.call("consult_request", utterance="채식주의자 원미도서관으로 가져다줄 수 있어요?", pickup="원미도서관")
ok(r3c["found"] and r3c["book"]["isbn13"] == "9788936433598" and r3c["pickup"] == "원미" and r3c["route"] == "visit",
   "   [10/18] 수령관 「원미도서관」도 설정 이름 「원미」로 · 검색어에서 「원미도서관으로」를 뺌 → 바로 이용")
r3d = c.call("consult_request", utterance="채식주의자 있나요?", pickup="부천시립 꿈빛도서관")
ok(r3d["pickup"] == "꿈빛" and r3d["route"] == "visit", "   [10/18] 「부천시립 꿈빛도서관」 → 「꿈빛」")
r10 = c.call("consult_request", utterance="희랍어 시간 있나요?", pickup="상동")
ok(r10["found"] and r10["route"] == "check" and "확인하지 못했습니다" in r10["notice"] and "소장되어 있지 않습니다" not in r10["notice"]
   and r10["availability"]["nation"] is None and any("비치" in x for x in r10["policy"]["pending"]) and "확인 불가" in r10["desk_memo"],
   "④′ 그 책 조회만 실패 + 픽스처에도 없는 책 — 「미소장 → 책바다」가 아니라 「소장 확인 불가 → 창구 조회」(비치 규정도 창구 확인)")
from urllib.parse import quote as _q
ok(r10["official_link"] == "https://alpasq.bcl.go.kr/search/keyword/" + _q(r10["book"]["title"], safe="")
   and (r["official_link"] or "").endswith("/" + r["book"]["isbn13"]),
   "④‴ [10/18] 누리집 링크 — 소장을 확인한 책은 ISBN(그 판본 화면), 소장 확인 불가인 책은 제목 검색(그 판본이 없을 수도 있어)")
r11 = c.call("consult_request", utterance="흐르는 강물처럼", pickup="상동")
ok(r11["found"] is False and r11["route"] == "check" and "연결되지 않아" in r11["notice"] and r11["desk_memo"].startswith("[조회 불가]"),
   "④″ 서지 검색부터 실패 — 「저자·출판사를 알려 달라」고 되묻지 않고 「조회 불가 → 창구 조회」")
ok("상호대차 제외 자료 아님" in r2["policy"]["pending"] and "상호대차 제외 자료 아님" not in r["policy"]["pending"],
   "   자료 유형·신착을 모르는 책(정보나루 서지)은 제외 자료 규정도 창구 확인 — 픽스처 도서는 그대로 판정")
allj = json.dumps([r, r2, r3, r10, r11], ensure_ascii=False)
ok(FAKE_KEY not in allj and "authKey" not in allj, "⑤ 응답에 인증키 흔적 없음")
banner = c.banner()
ok("relay 모드" in banner and "관내 출처 naru" in banner, "   기동 배너 — relay 모드 · 관내 출처 naru")

print("── 중계가 죽은 뒤 ──")
httpd.shutdown(); httpd.server_close()
c2 = Client(CHAEKIJI_MODE="relay", CHAEKIJI_RELAY=RELAY, CHAEKIJI_LOCAL_SOURCE="naru")
r4 = c2.call("consult_request", utterance="나미야 잡화점의 기적", pickup="상동")
ok(r4["found"] and "픽스처로 복귀" in r4["availability"]["basis"] and r4["availability"]["asof"] == "2026-08-18",
   "④ relay 모드인데 중계 응답 없음 — 픽스처(2026-08-18)로 복귀, 근거에 표시")
c2.banner()
c3 = Client(CHAEKIJI_MODE="auto", CHAEKIJI_RELAY=RELAY)
r5 = c3.call("consult_request", utterance="나미야 잡화점의 기적", pickup="상동")
ok(r5["mode"] == "demo", "① auto → 중계 죽어 있으면 demo 선택")
c3.banner()
print("── 매일 갱신 스냅샷(refresh_today.py 결과) ──")
tmp = Path(tempfile.mkdtemp())
r0 = subprocess.run([sys.executable, str(ROOT/"lab"/"refresh_today.py"), "--demo", "--out", str(tmp/"snap.json"), "--status-out", str(tmp/"status.json"),
                     "--web-out", str(tmp/"web.json")], capture_output=True, text=True, encoding="utf-8", timeout=60)
snap = json.load(open(tmp/"snap.json", encoding="utf-8"))
ok(r0.returncode == 0 and snap["asof"] == TODAY and len(snap["holdings"]) == 5 and "9790000000012" not in snap["holdings"] and (tmp/"web.json").exists(),
   "⑥ refresh_today.py --demo — 오늘 날짜 스냅샷 2벌(서버용·웹용), 픽스처 5종")
snap["holdings"]["9788972756194"]["상동"] = "ok"                      # 어제 반납됐다고 치자
json.dump(snap, open(tmp/"snap.json", "w", encoding="utf-8"), ensure_ascii=False)
c4 = Client(CHAEKIJI_MODE="auto", CHAEKIJI_RELAY=RELAY, CHAEKIJI_SNAPSHOT=str(tmp/"snap.json"))
r6 = c4.call("consult_request", utterance="나미야 잡화점의 기적", pickup="상동")
ok(r6["mode"] == "snapshot" and r6["route"] == "visit" and "매일 갱신" in r6["availability"]["basis"] and r6["availability"]["asof"] == TODAY,
   "   중계 없음 + 신선한 스냅샷 → auto가 snapshot 선택 · 어제 반납분이 「바로 이용」으로 반영")
c4.banner()
snap["asof"] = (datetime.datetime.now(KST).date() - datetime.timedelta(days=30)).isoformat()   # [10/19] 10일 → 30일(심사 기간 고정 자료 규칙과 겹치지 않게 — 판정 기준은 그대로)
json.dump(snap, open(tmp/"snap.json", "w", encoding="utf-8"), ensure_ascii=False)
c5 = Client(CHAEKIJI_MODE="auto", CHAEKIJI_RELAY=RELAY, CHAEKIJI_SNAPSHOT=str(tmp/"snap.json"))
r7 = c5.call("consult_request", utterance="나미야 잡화점의 기적", pickup="상동")
ok(r7["mode"] == "demo" and r7["availability"]["asof"] == "2026-08-18", "   30일 지난 스냅샷은 무시 → demo(8/18 픽스처)")
c5.banner()
# [10/19] 심사 기간 고정 자료 — 동결(11/8 18시) 뒤 새벽 갱신이 멈춰도 11/8 자료로 결선(11/25)까지 답한다. 날짜를 넣어 순수 함수로 확인(실제 시계와 무관)
sys.path.insert(0, str(ROOT))
from connectors import naru as _naru
D = datetime.date
ok(_naru.snapshot_ok(D(2026, 11, 8), D(2026, 11, 13)) and _naru.snapshot_ok(D(2026, 11, 8), D(2026, 11, 17)) and _naru.snapshot_ok(D(2026, 11, 8), D(2026, 11, 25))
   and _naru.snapshot_ok(D(2026, 11, 8), D(2026, 11, 26)) and not _naru.snapshot_ok(D(2026, 11, 8), D(2026, 11, 27))
   and not _naru.snapshot_ok(D(2026, 11, 7), D(2026, 11, 13)) and not _naru.snapshot_ok(D(2026, 11, 9), D(2026, 11, 8)),
   "   ⑥′ 심사 기간 고정 자료 — 11/8 자료는 11/13·11/17·11/25·11/26에 신선, 11/27엔 아님 · 11/7 자료는 아님 · 미래 날짜 자료는 아님")
ok(_naru.snapshot_ok(D(2026, 10, 19), D(2026, 10, 19)) and _naru.snapshot_ok(D(2026, 10, 17), D(2026, 10, 19)) and not _naru.snapshot_ok(D(2026, 10, 16), D(2026, 10, 19)),
   "   ⑥″ 평소 규칙은 그대로 — 2일 이내만 신선(10/17 자료는 10/19에 신선, 10/16 자료는 아님)")
httpd2 = serve(PORT + 1); time.sleep(0.3)
snap["asof"] = TODAY
json.dump(snap, open(tmp/"snap.json", "w", encoding="utf-8"), ensure_ascii=False)
c6 = Client(CHAEKIJI_MODE="auto", CHAEKIJI_RELAY=f"http://127.0.0.1:{PORT+1}", CHAEKIJI_SNAPSHOT=str(tmp/"snap.json"))
r8 = c6.call("consult_request", utterance="나미야 잡화점의 기적", pickup="상동")
r9 = c6.call("consult_request", utterance="채식주의자", pickup="상동")
ok(r8["mode"] == "relay" and "매일 갱신" in r8["availability"]["basis"] and "상동" in r8["availability"]["available_at"] and r8["route"] == "visit",
   "   relay 모드라도 스냅샷에 있는 책은 중계를 안 부름(한도 절약) — 스냅샷 값으로 판정")
ok(r9["found"] and "중계" in r9["availability"]["basis"] and r9["route"] == "ill", "   스냅샷에 없는 책은 중계로 — 『채식주의자』 관내 상호대차")
c6.banner(); httpd2.shutdown(); httpd2.server_close()
print(f"\n중계 시험 {PASS}건 통과 — 키 없이 오늘 데이터, 중계가 멈춰도 멈추지 않는다.")
