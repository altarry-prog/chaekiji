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
                                  text=True, encoding="utf-8", env=env)
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
ok(len(tl["tools"]) == 11, "tools/list — 핵심 8종 + 확장 2종 + 상담 묶음 1종 노출 (v0.3.4)")
pl = c.rpc("prompts/list")
ok(len(pl["prompts"]) == 1 and pl["prompts"][0]["name"] == "consult", "prompts/list — 사서 모드 지시문 「consult」 노출 (v0.3.4)")
pg = c.rpc("prompts/get", {"name": "consult", "arguments": {"pickup": "꿈빛", "lang": "vi"}})
ptxt = pg["messages"][0]["content"]["text"]
ok("「꿈빛」" in ptxt and "「vi」" in ptxt and "개인정보" in ptxt and "접수는 사서가" in ptxt,
   "prompts/get — 수령관·언어가 채워지고 개인정보 금지·접수는 사서가 명시")

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
print("── v0.3.4 · 상담 묶음(consult_request) — 창구·전화에서 지금 쓰는 판정 ──")
k1 = c.call("consult_request", utterance="나미야 잡화점의 기적 빌리고 싶어요", pickup="상동")
ok(k1["found"] and k1["route"] == "ill" and k1["from_lib"] in k1["availability"]["available_at"] and k1["from_lib"] != "상동",
   f"㉔ 말 한마디 → 찾기·소장·규정 한 번에 — 갈래 「{k1['route_label']}」 · 소장관 {k1['from_lib']}")
ok(len(k1["policy"]["pending"]) == 5 and k1["policy"]["allowed_so_far"] and "창구에서 확인" in k1["notice"],
   "    회원 토큰 없음 — 비치·제외자료만 확정, 한도 3종·연체·중복은 창구 확인으로 보류")
ok("전일 기준" in k1["notice"] and "2026. 8. 18." in k1["notice"] and "접수하지 않음" in k1["desk_memo"],
   "    안내문에 조회일·전일 기준 명시 · 접수 메모에 「이 도구는 접수하지 않음」")
ok((k1.get("official_link") or "").startswith("https://alpasq.bcl.go.kr/search/keyword/%EB%82%98%EB%AF%B8%EC%95%BC")
   and k1["official_link"] in k1["notice"] and "접수는 이용자가 직접" in k1["notice"],
   "    안내문 끝에 공식 누리집 링크(설정 official_search_url, 제목을 주소에 넣음) — 그 책 화면까지, 접수는 이용자가 직접")
k2 = c.call("consult_request", utterance="한강 소년이 온다 찾아주세요", pickup="상동")
ok(k2["route"] == "visit" and "바로 대출" in k2["notice"] and "다만" not in k2["notice"],
   "㉕ 수령관 서가에 있는 책 — 「바로 이용」, 상호대차 아님(비치 규정을 되풀이하지 않음)")
k3 = c.call("consult_request", utterance="지구 끝의 온실", pickup="상동")
ok(k3["route"] == "sea" and k3["availability"]["nation"]["found_count"] == 6 and "책바다" in k3["notice"]
   and k3["official_link"] is None and "누리집" not in k3["notice"],
   "㉖ 관내 전무 — 「책바다 안내」 + 전국 소장 수(전일 기준) · 누리집 링크 없음(관내에 없는 책)")
k4 = c.call("consult_request", utterance="나미야 잡화점의 기적", pickup="상동", user="tok_kimsj")
ok(k4["policy"]["pending"] == [] and k4["policy"]["allowed_so_far"] and k4["next_tool"]["tool"] == "request_service",
   "㉗ 회원 토큰 있음 — 규정 7종 전부 판정, 다음 도구(request_service) 제안(이용자 확인 뒤에만)")
k5 = c.call("consult_request", utterance="나미야 잡화점의 기적", pickup="상동", user="tok_parkys")
ok(not k5["policy"]["allowed_so_far"] and "연체" in k5["notice"], "㉘ 연체 회원 — 안내문에 「연체」 조건이 먼저 확인할 것으로 붙음")
k6 = c.call("consult_request", utterance="아무도 모르는 책", pickup="상동")
ok(k6["found"] is False and k6["route"] == "unknown" and "알려 주시겠어요" in k6["notice"],
   "㉙ 못 찾은 책 — 지어내지 않고 되묻기 안내")
k7 = c.call("consult_request", utterance="불편한 편의점", pickup="역곡", lang="vi")
ok(k7["translate_to"] == "vi" and k7["route"] == "ill", "㉚ 이용자 언어 vi — translate_to로 호스트 모델이 옮기게 넘김")
k8 = c.call("consult_request", utterance="불편한 편의점", pickup="없는관")
ok("_error" in k8 and "설정에 없는" in k8["_error"], "㉛ 설정에 없는 수령관 — 오류로 거부")
c.close()

print("── 설정 교체 검증 · 가상시(ill_limit 5→2) ──")
c2 = Client("example-city.yaml")
c2.rpc("initialize", {"protocolVersion":"2024-11-05","capabilities":{},
                      "clientInfo":{"name":"kit","version":"0"}})
v3 = c2.call("check_policy", user="tok_kimsj", isbn13="9788972756194", pickup="중앙")
failed = [x for x in v3["checks"] if not x["pass"]]
ok(not v3["allowed"] and any("2권" in x["rule"] for x in failed),
   f"같은 코드·같은 회원 — 규정 YAML만 바꿔 차단됨: {failed[0]['rule']} ({failed[0]['detail']})")
k9 = c2.call("consult_request", utterance="나미야 잡화점의 기적", pickup="중앙")
ok(k9["found"] and k9["pickup"] == "중앙" and "가상시(예시)시립도서관" in k9["notice"],
   "상담 묶음도 설정 교체만으로 다른 도시(가상시) 수령관·도시 이름으로 동작")
ok(k9["official_link"] is None and "누리집" not in k9["notice"],
   "official_search_url을 비운 도시 — 안내문에 링크 없음(설정으로만 켜고 끔)")
c2.close()

print(f"\n전체 {PASS}건 통과 — 표준 도구 계층과 설정 분리 구조가 실증되었습니다.")
