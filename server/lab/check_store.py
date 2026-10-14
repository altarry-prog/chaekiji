#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[3주차] 실험실 점검 시험 — 영속 저장·감사 기록·관내 출처 전환. 네트워크·인증키 불필요(demo 모드).
적합성 시험 33건(tests/run_scenarios.py)과 별도로 센다 — 원고의 「33건」 숫자를 건드리지 않기 위해.
실행: python3 lab/check_store.py
검증하는 것:
  ① 서버를 껐다 켜도 신청·위임·한도 현황이 남는다(CHAEKIJI_STORE)
  ② 취소·해지가 저장되고 복원된다
  ③ 감사 기록이 해시 사슬로 이어지고, 한 줄을 고치면 검증이 실패한다(CHAEKIJI_AUDIT)
  ④ 감사 기록에 회원 식별자·토큰 원문·알림 문구가 없다
  ⑤ 관내 출처를 정보나루(CHAEKIJI_LOCAL_SOURCE=naru)로 바꿔도 같은 판정이 나온다"""
import subprocess, json, sys, os, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import audit

class Client:
    def __init__(self, **env):
        e = dict(os.environ, CHAEKIJI_CONFIG=str(ROOT/"config"/"bucheon.yaml"), CHAEKIJI_MODE="demo", **env)
        self.p = subprocess.Popen([sys.executable, str(ROOT/"server.py")], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=e)
        self.n = 0
        self.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "lab", "version": "0"}})
    def rpc(self, method, params=None):
        self.n += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}, ensure_ascii=False) + "\n")
        self.p.stdin.flush()
        return json.loads(self.p.stdout.readline())["result"]
    def call(self, name, **args):
        r = self.rpc("tools/call", {"name": name, "arguments": args})
        body = r["content"][0]["text"]
        return json.loads(body) if not r.get("isError") else {"_error": body}
    def close(self):
        self.p.stdin.close(); self.p.wait(timeout=5)
        return self.p.stderr.read()

PASS = 0
def ok(cond, label):
    global PASS
    assert cond, f"실패: {label}"
    PASS += 1; print(f"  ✓ {label}")

tmp = tempfile.mkdtemp(prefix="chaekiji-lab-")
db, log = os.path.join(tmp, "state.sqlite3"), os.path.join(tmp, "audit.jsonl")
env = dict(CHAEKIJI_STORE=db, CHAEKIJI_AUDIT=log)

print("── ① 영속 저장 — 서버 재시작 후 복원 ──")
c = Client(**env)
md = c.call("manage_mandate", user="tok_kimsj", op="create", pickup="상동")
r1 = c.call("request_service", user="tok_kimsj", isbn13="9791161571188", from_lib="꿈빛", pickup="상동", mandate_id=md["mandate_id"])
r2 = c.call("request_service", user="tok_kimsj", isbn13="9788972756194", from_lib="한울빛", pickup="상동", confirmed_by_user=True)
ok(r1["accepted"] and r2["accepted"], f"위임 실행 {r1['receipt']} · 즉시 확인 {r2['receipt']} 접수")
banner = c.close()
ok("저장 계층 켜짐" in banner and "감사 기록 켜짐" in banner, "서버 시작 문구에 저장·감사 켜짐 표시")

c = Client(**env)                                     # 서버를 새로 켠다 — 메모리는 비어 있어야 정상
t = c.call("track_request", user="tok_kimsj", request_no=r1["receipt"])
ok(t.get("status") == "requested", f"재시작 후 track_request {r1['receipt']} → 「{t.get('status_label')}」 (복원)")
st = c.call("manage_mandate", user="tok_kimsj", op="status")
ok(st.get("active") and st.get("used_this_cycle") == 1 and st.get("mandate_id") == md["mandate_id"],
   f"재시작 후 위임 {md['mandate_id']} 활성 · 이번 주기 사용 1권 (복원)")
v = c.call("check_policy", user="tok_kimsj", isbn13="9788936434120", pickup="동화")
ok(v["checks"][1]["detail"].startswith("현재 4/5"), "재시작 후 한도 현황 4/5권 유지 (회원 모의값 복원)")

print("── ② 취소·해지의 저장 ──")
x = c.call("cancel_request", user="tok_kimsj", request_no=r2["receipt"])
rv = c.call("manage_mandate", user="tok_kimsj", op="revoke")
ok(x.get("canceled") and rv.get("revoked"), "취소·해지 실행")
c.close()
c = Client(**env)
t2 = c.call("track_request", user="tok_kimsj", request_no=r2["receipt"])
st2 = c.call("manage_mandate", user="tok_kimsj", op="status")
ok(t2.get("status") == "canceled" and not st2.get("active") and st2.get("revoked_at"),
   f"재시작 후에도 취소 상태·해지 일시({st2.get('revoked_at')}) 유지")
n = c.call("notify_user", user="tok_kimsj", event="test", message="비밀문구-이것은-기록되면-안-됨")
ok(n.get("queued"), "알림 큐 적재(문구는 감사 기록에 남지 않아야 함)")
c.close()

print("── ③④ 감사 기록 — 해시 사슬·최소 기록 ──")
good, nlines, bad = audit.verify(log)
ok(good and nlines >= 10, f"감사 기록 {nlines}줄 사슬 정상")
text = open(log, encoding="utf-8").read()
ok("m-1004" not in text and "tok_kimsj" not in text and "비밀문구" not in text,
   "회원 식별자·토큰 원문·알림 문구 없음(토큰은 해시 12자만)")
entries = [json.loads(l) for l in text.splitlines() if l.strip()]
ok(any(e.get("tool") == "request_service" and e.get("authorized_by", "").startswith("사전 위임") for e in entries),
   "위임 실행의 근거(사전 위임 mnd-…)가 기록됨")
lines = text.splitlines()
lines[3] = lines[3].replace('"outcome": "ok"', '"outcome": "denied"')   # 4번째 줄 변조
open(log, "w", encoding="utf-8").write("\n".join(lines) + "\n")
good2, _, bad2 = audit.verify(log)
ok(not good2 and bad2 == 4, f"한 줄을 고치면 검증 실패 — {bad2}번째 줄에서 사슬 끊김 감지")

print("── ⑤ 관내 출처 전환(정보나루 픽스처) — 같은 판정 ──")
c = Client(CHAEKIJI_LOCAL_SOURCE="naru")
av = c.call("check_availability", isbn13="9788972756194")
ok(av["home_status"] == "busy" and len(av["available_at"]) == 8 and "정보나루" in av["basis"] and av.get("holding_count") == 13,
   f"check_availability(naru) — 상동 대출중 · 8곳 가능 · 소장관 13 · 근거 「{av['basis']}」")
v2 = c.call("check_policy", user="tok_kimsj", isbn13="9788936434120", pickup="상동")
ok(not v2["allowed"] and any("비치" in x["rule"] for x in v2["checks"] if not x["pass"]),
   "check_policy(naru) — 수령관 비치 규정이 같은 출처로 판정")
c.close()

print(f"\n실험실 점검 {PASS}건 통과 — 저장 계층·감사 기록·관내 출처 전환이 동작합니다. (임시 파일: {tmp})")
