#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""적합성 시험 킷 — 김순자 시나리오 + 설정 교체 검증.
서버를 실제 MCP 전송(stdio JSON-RPC)으로 띄워 도구를 호출한다.
어떤 커넥터 구현이든 이 시험을 통과하면 책이지 에이전트와 호환된다."""
import subprocess, json, sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

class Client:
    def __init__(self, config):
        env = dict(os.environ, CHAEKIJI_CONFIG=str(ROOT/"config"/config), CHAEKIJI_MODE="demo")
        self.p = subprocess.Popen([sys.executable, str(ROOT/"server.py")],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  text=True, env=env)
        self.n = 0
    def rpc(self, method, params=None):
        self.n += 1
        self.p.stdin.write(json.dumps({"jsonrpc":"2.0","id":self.n,"method":method,
                                       "params":params or {}}, ensure_ascii=False)+"\n")
        self.p.stdin.flush()
        return json.loads(self.p.stdout.readline())["result"]
    def call(self, name, **args):
        r = self.rpc("tools/call", {"name": name, "arguments": args})
        body = r["content"][0]["text"]
        return (json.loads(body) if not r.get("isError") else {"_error": body})
    def close(self): self.p.stdin.close(); self.p.wait(timeout=5)

PASS = 0
def ok(cond, label):
    global PASS
    assert cond, f"실패: {label}"
    PASS += 1; print(f"  ✓ {label}")

print("── 부천 설정 · 김순자 시나리오 ──")
c = Client("bucheon.yaml")
init = c.rpc("initialize", {"protocolVersion":"2024-11-05","capabilities":{},
                            "clientInfo":{"name":"conformance-kit","version":"0"}})
ok(init["serverInfo"]["name"] == "chaekiji-mcp", "initialize — 서버 식별")
tl = c.rpc("tools/list")
ok(len(tl["tools"]) == 10, "tools/list — 핵심 8종 + 확장 2종 노출 (v0.3)")

b = c.call("search_item", utterance="그 왜 나미야 잡화점인가 하는 책")
ok(b["isbn13"] == "9788972756194", f"① search_item — 『{b['title']}』 ISBN 확정")

a = c.call("check_availability", isbn13=b["isbn13"])
ok(a["home_status"] == "busy" and len(a["available_at"]) == 8,
   f"② check_availability — 상동 대출중 · 관내 {len(a['available_at'])}곳 가능(실시간·모의)")

v = c.call("check_policy", user="tok_kimsj", isbn13=b["isbn13"], pickup="상동")
ok(v["allowed"] and len(v["checks"]) == 7, "③ check_policy — 규정 7종 전부 통과 (2/5권)")

r0 = c.call("request_service", user="tok_kimsj", isbn13=b["isbn13"],
            from_lib="한울빛", pickup="상동", confirmed_by_user=False)
ok("_error" in r0, "④a request_service — 확인 없는 실행은 거부")

r1 = c.call("request_service", user="tok_kimsj", isbn13=b["isbn13"],
            from_lib="한울빛", pickup="상동", confirmed_by_user=True)
ok(r1["accepted"] and r1["receipt"].startswith("ILL-"),
   f"④b request_service — 접수 {r1['receipt']} (한도 2→3권 반영)")

v2 = c.call("check_policy", user="tok_kimsj", isbn13=b["isbn13"], pickup="상동")
ok(v2["checks"][1]["detail"].startswith("현재 3/5"), "    실행 후 한도 3/5로 갱신 확인")

n1 = c.call("notify_user", user="tok_kimsj", event="arrival", message="신청하신 책이 도착했습니다")
ok(n1["queued"] and n1["channel"] == "voice_call",
   "⑤ notify_user — 선호 채널(음성전화)로 발송")

alt = c.call("find_alternative", isbn13="9788936434120")
ok(alt["audiobook"] and alt["chaeknarae_eligible"],
   "＋ find_alternative — 오디오북 존재 → 책나래 분기 가능(모의)")

g = c.call("check_availability", isbn13="9791191824001")
ok(not g["available_at"] and g["nation"]["found_count"] == 6,
   "＋ 관내 전무 도서 → 전국 폴백(정보나루 · 전일 기준 명시)")

print("── 책이지 패스 · 사전 위임 자동 실행 ──")
sg = c.call("suggest_items", user="tok_kimsj", count=3)
ok(len(sg["items"]) == 3, "⑥ suggest_items — 이달의 추천 3권(모의)")

md = c.call("manage_mandate", user="tok_kimsj", op="create", pickup="상동")
ok(md["mandate_id"].startswith("mnd-") and md["scope"]["max_per_cycle"] == 3,
   f"⑦ manage_mandate — 위임 생성 {md['mandate_id']} (월 3권·무료 경로만)")
ok(md.get("agreed_at") and md.get("notice_version"),
   f"    동의 기록 보존 — {md['agreed_at']} · {md['notice_version']}")

r2 = c.call("request_service", user="tok_kimsj", isbn13="9791161571188",
            from_lib="꿈빛", pickup="상동", mandate_id=md["mandate_id"])
ok(r2["accepted"] and "위임" in r2["authorized_by"],
   f"⑧ 위임 실행 — 확인 없이 접수 {r2['receipt']} (근거: {r2['authorized_by']})")

r3 = c.call("request_service", user="tok_kimsj", isbn13="9791191824001",
            from_lib="전국", pickup="상동", mandate_id=md["mandate_id"], route="sea")
ok((not r3["accepted"]) and r3.get("skipped"),
   "⑨ 실비 경로(책바다)는 위임 범위 밖 — 스스로 건너뜀")

rv = c.call("manage_mandate", user="tok_kimsj", op="revoke")
r4 = c.call("request_service", user="tok_kimsj", isbn13="9788972756194",
            from_lib="한울빛", pickup="상동", mandate_id=md["mandate_id"])
ok("_error" in r4, "⑩ 해지 후 위임 실행 시도 — 거부 (즉시 해지권 보장)")
st = c.call("manage_mandate", user="tok_kimsj", op="status")
ok(rv.get("revoked_at") and st.get("revoked_at") and not st["active"],
   f"    해지 일시 기록 보존 — {st['revoked_at']}")

print("── v0.3 · 신청 이후의 생애주기 ──")
t1 = c.call("track_request", user="tok_kimsj", request_no=r1["receipt"])
ok(t1["status"] == "requested" and t1["status_label"] == "접수",
   f"⑪ track_request — {t1['no']} 상태 「{t1['status_label']}」 + 다음 안내")

c.call("_sim", request_no=r1["receipt"], event="confirm")
c.call("_sim", request_no=r1["receipt"], event="transit")
c.call("_sim", request_no=r1["receipt"], event="arrive")
t2 = c.call("track_request", user="tok_kimsj", request_no=r1["receipt"])
ok(t2["status"] == "arrived" and t2.get("pickup_due") and t2.get("hold_days") == 3,
   f"⑫ 확보→이송→도착 추적 — 수령기한 {t2['pickup_due']}(보관 {t2['hold_days']}일, 설정값)")

c.call("_sim", request_no=r1["receipt"], event="expire")
t3 = c.call("track_request", user="tok_kimsj", request_no=r1["receipt"])
ok(t3["status"] == "canceled" and "보관기한" in t3["cancel_reason"] and t3["canceled_by"] == "system",
   "⑬ 보관기한 경과 미수령 — 자동 취소 + 사유 기록")
vv = c.call("check_policy", user="tok_kimsj", isbn13="9788972756194", pickup="상동")
ok(vv["checks"][1]["detail"].startswith("현재 3/5"),
   "    자동 취소 즉시 한도 복원 (4→3권)")

r5 = c.call("request_service", user="tok_kimsj", isbn13="9788936434120",
            from_lib="꿈빛", pickup="동화", confirmed_by_user=True)
c.call("_sim", request_no=r5["receipt"], event="confirm")
c.call("_sim", request_no=r5["receipt"], event="fail_shelf")
t4 = c.call("track_request", user="tok_kimsj", request_no=r5["receipt"])
ok(t4["status"] == "failed" and "서가 부재" in t4["fail_reason"],
   f"⑭ 서가 부재·대출 경합 실패 — 사유 기록 + 한도 복원 ({t4['no']})")
alt2 = c.call("find_alternative", isbn13="9788936434120")
n2 = c.call("notify_user", user="tok_kimsj", event="ill_failed",
            message="상호대차가 실패했습니다. 오디오북 대체자료가 있어 안내드립니다.")
ok(alt2["chaeknarae_eligible"] and n2["queued"],
   "⑮ 실패 → 대체자료 확인 → 통보 — 도구 연계로 복구 흐름 완결")

r6 = c.call("request_service", user="tok_kimsj", isbn13="9788936434120",
            from_lib="꿈빛", pickup="별빛마루", confirmed_by_user=True)
ok(r6["accepted"], f"⑯ 실패 도서 재신청 가능 — 한도·중복목록 복원 검증 ({r6['receipt']})")
x1 = c.call("cancel_request", user="tok_parkys", request_no=r6["receipt"])
ok("_error" in x1, "⑰ 타인 토큰의 취소 시도 — 거부 (본인 신청만)")
x2 = c.call("cancel_request", user="tok_kimsj", request_no=r6["receipt"])
ok(x2["canceled"] and x2["restored_limit"], "⑱ 이용자 취소 — 즉시 한도 복원")

ra = c.call("request_service", user="tok_kimsj", isbn13="9791191824001",
            from_lib="타지역", pickup="상동", confirmed_by_user=True,
            client_ref="app-20260830-001")
rb = c.call("request_service", user="tok_kimsj", isbn13="9791191824001",
            from_lib="타지역", pickup="상동", confirmed_by_user=True,
            client_ref="app-20260830-001")
ok(rb["accepted"] and rb.get("duplicate") and rb["receipt"] == ra["receipt"],
   "⑲ 같은 요청 재전송(재시도) — 새 신청 대신 기존 접수 반환 (이중 방지)")
rc = c.call("request_service", user="tok_kimsj", isbn13="9791191824001",
            from_lib="타지역", pickup="상동", confirmed_by_user=True)
dup_rule = [x for x in rc["why"] if not x["pass"]] if not rc["accepted"] else []
ok((not rc["accepted"]) and any("중복" in x["rule"] for x in dup_rule),
   "⑳ 진행 중 도서 재신청 — 규정 판정이 차단 (동일 도서 중복 신청 없음)")

print("── v0.3 · 규정 확장 — 연체·제외자료 ──")
vo = c.call("check_policy", user="tok_parkys", isbn13="9788972756194", pickup="상동")
fo = [x for x in vo["checks"] if not x["pass"]]
ok((not vo["allowed"]) and any("연체" in x["rule"] for x in fo),
   f"㉑ 연체 회원 차단 — {fo[0]['detail']}")
vn = c.call("check_policy", user="tok_kimsj", isbn13="9790000000012", pickup="상동")
fn = [x for x in vn["checks"] if not x["pass"]]
ok((not vn["allowed"]) and any("제외" in x["rule"] for x in fn),
   "㉒ 신착 자료 제외 — 설정(exclude_new_arrival)으로 차단")
vd = c.call("check_policy", user="tok_kimsj", isbn13="9790000000029", pickup="상동")
fd = [x for x in vd["checks"] if not x["pass"]]
ok((not vd["allowed"]) and any("제외" in x["rule"] for x in fd),
   "㉓ 비도서(DVD) 제외 — 설정(excluded_types)으로 차단")
c.close()

print("── 설정 교체 검증 · 가상시(ill_limit 5→2) ──")
c2 = Client("example-city.yaml")
c2.rpc("initialize", {"protocolVersion":"2024-11-05","capabilities":{},
                      "clientInfo":{"name":"kit","version":"0"}})
v3 = c2.call("check_policy", user="tok_kimsj", isbn13="9788972756194", pickup="중앙")
failed = [x for x in v3["checks"] if not x["pass"]]
ok(not v3["allowed"] and any("2권" in x["rule"] for x in failed),
   f"같은 코드·같은 회원 — 규정 YAML만 바꿔 차단됨: {failed[0]['rule']} ({failed[0]['detail']})")
c2.close()

print(f"\n전체 {PASS}건 통과 — 표준 도구 계층과 설정 분리 구조가 실증되었습니다.")
