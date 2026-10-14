# -*- coding: utf-8 -*-
"""표준 도구 10종(핵심 8종 + 확장 2종) — MCP 서버가 노출하는 전부.
에이전트는 이 함수들의 이름과 인자만 알며,
그 뒤의 정보나루·알파스·규정·금고는 커넥터가 처리한다.
v0.3: 신청 이후의 생애주기(추적·취소)와 규정 3종(연체·제외자료·중복)이 계약에 들어왔다.
v0.3.1(실험실): 관내 조회원 선택(CHAEKIJI_LOCAL_SOURCE=alpas|naru) · 영속 저장(CHAEKIJI_STORE) · 감사 기록(server.py)."""
import os, datetime, yaml
from pathlib import Path
import vault, policy, store
from connectors import naru, alpas_stub as alpas
import json as _json

# 위임장(mandate) 저장소 — 운영: DB. 책이지 패스 등록(동의 1회)이 만드는 실행 권한의 실체.
_MANDATES = {}
_MSEQ = [0]

ROOT = Path(__file__).resolve().parent
CFG = yaml.safe_load(open(os.environ.get("CHAEKIJI_CONFIG", ROOT/"config"/"bucheon.yaml"), encoding="utf-8"))
MODE = os.environ.get("CHAEKIJI_MODE", "demo")
# 관내 소장·대출의 출처 — alpas: 도서관리시스템 실시간(모의) / naru: 정보나루 bookExist(전일 기준, live면 실호출)
LOCAL_SOURCE = os.environ.get("CHAEKIJI_LOCAL_SOURCE", "alpas")

# [v0.3.1] 서버를 켤 때 저장된 이력이 있으면 복원한다(CHAEKIJI_STORE가 있을 때만).
_saved = store.load()
if _saved:
    _MANDATES.update(_saved["mandates"]); _MSEQ[0] = _saved["mseq"]
    alpas._requests.update(_saved["requests"])
    for _mid, _m in _saved["members"].items():
        if _mid in alpas._members: alpas._members[_mid].update(_m)

def _persist():
    store.save(_MANDATES, _MSEQ, alpas._requests, alpas._members)

def _local_holdings(isbn13: str):
    """관내 {관이름: ok|busy|none}과 근거 문구. 출처는 LOCAL_SOURCE로 고른다."""
    if LOCAL_SOURCE == "naru":
        rt = naru.holdings_local(isbn13, CFG["libraries"], CFG["region_code"], mode=MODE)
        return rt, naru.LAST_META.get("basis", "관내: 정보나루(전일 기준)")
    return alpas.holdings_realtime(isbn13), "관내: 도서관리시스템 실시간(모의)"

def search_item(utterance: str, lang: str = "ko"):
    return naru.search(utterance, mode=MODE)

def check_availability(isbn13: str, realtime: bool = True):
    home = CFG["home_library"]
    rt, basis = _local_holdings(isbn13)
    ok  = sorted([l for l, s in rt.items() if s == "ok"])
    busy = sorted([l for l, s in rt.items() if s == "busy"])
    res = {"city": CFG["city"], "home_library": home, "home_status": rt.get(home, "none"),
           "available_at": ok, "loaned_at": busy, "basis": basis}
    if LOCAL_SOURCE == "naru":
        res["holding_count"] = naru.LAST_META.get("holding_count")
        res["naru_calls"] = naru.LAST_META.get("calls")
    if not ok:                                        # 관내 전무 → 전국(정보나루, 전일 기준)
        res["nation"] = naru.availability_nation(isbn13, mode=MODE)
    return res

def check_policy(user: str, isbn13: str, pickup: str):
    member = alpas.member_status(vault.resolve(user))     # 토큰은 금고 안에서만 풀린다
    if LOCAL_SOURCE == "naru":                            # 수령관 비치 여부도 같은 출처(캐시로 재호출 없음)
        on_shelf = _local_holdings(isbn13)[0].get(pickup) == "ok"
    else:
        on_shelf = alpas.on_shelf(pickup, isbn13)
    return policy.check(CFG["rules"], member, on_shelf, pickup,
                        item=naru.bibinfo(isbn13, mode=MODE), isbn13=isbn13)

def request_service(user: str, isbn13: str, from_lib: str, pickup: str,
                    confirmed_by_user: bool = False, mandate_id: str = None,
                    route: str = "ill", client_ref: str = None):
    """실행 권한은 둘 중 하나 — 그 자리의 확인(confirmed_by_user) 또는 사전 위임(mandate_id).
    client_ref가 있으면 같은 요청의 재수신(네트워크 재시도)을 먼저 가려낸다 — 이미 접수된 일은 다시 만들지 않는다."""
    if client_ref:
        prev = alpas.find_by_ref(vault.resolve(user), client_ref)
        if prev:
            return {"accepted": True, "receipt": prev, "duplicate": True,
                    "why": "동일 client_ref 재수신 — 새 신청을 만들지 않고 기존 접수를 반환(이중 신청 방지)"}
    if mandate_id:
        m = _MANDATES.get(mandate_id)
        if not m or not m["active"]:
            raise PermissionError("유효한 위임(책이지 패스)이 없습니다")
        if m["user"] != user:
            raise PermissionError("위임의 이용자가 다릅니다")
        if m["scope"]["free_routes_only"] and route != "ill":
            return {"accepted": False, "skipped": True,
                    "why": "실비 경로는 위임 범위 밖 — 자동 실행하지 않고 수동 확인으로 넘깁니다"}
        if m["used_this_cycle"] >= m["scope"]["max_per_cycle"]:
            return {"accepted": False, "skipped": True,
                    "why": f"이번 주기 한도({m['scope']['max_per_cycle']}권) 소진"}
    elif not confirmed_by_user:
        raise PermissionError("이용자 확인(confirmed_by_user) 없이는 실행하지 않습니다")
    verdict = check_policy(user, isbn13, pickup)          # 어느 경로든 실행 직전 재판정
    if not verdict["allowed"]:
        return {"accepted": False, "why": verdict["checks"]}
    res = alpas.create_ill(vault.resolve(user), isbn13, from_lib, pickup, client_ref=client_ref)
    receipt = res["no"]
    if res.get("duplicate"):                              # 같은 요청 재수신(재시도) → 기존 접수 반환
        return {"accepted": True, "receipt": receipt, "duplicate": True,
                "why": "동일 client_ref 재수신 — 새 신청을 만들지 않고 기존 접수를 반환(이중 신청 방지)"}
    if mandate_id:
        _MANDATES[mandate_id]["used_this_cycle"] += 1
        _MANDATES[mandate_id]["ledger"].append(receipt)
    _persist()                                            # [v0.3.1] 접수 즉시 영속화
    return {"accepted": True, "receipt": receipt,
            "eta_days": CFG["ill_eta_days"], "executed_via": "알파스 커넥터(모의)",
            "authorized_by": ("사전 위임 " + mandate_id) if mandate_id else "이용자 즉시 확인"}

def suggest_items(user: str = None, count: int = 3):
    """[확장 v0.2] 이달의 추천 — 운영: AI 책큐/정보나루 recommandList 커넥터."""
    rec = _json.load(open(ROOT/"fixtures"/"recommend.json", encoding="utf-8"))["monthly"]
    return {"items": rec[:count], "basis": "월간 추천(모의 픽스처)"}

def manage_mandate(user: str, op: str, pickup: str = None):
    """[확장 v0.2] 사전 위임장(책이지 패스) 관리 — 한 번 등록하면 범위 안 신청은 확인 없이 접수하게 하는 동의 장치.
    create: 범위가 명시된 위임 생성(이 1회가 유일한 사람 확인)
    status/revoke: 조회·즉시 해지."""
    vault.resolve(user)                                   # 토큰 검증
    if op == "create":
        _MSEQ[0] += 1
        mid = f"mnd-{_MSEQ[0]:04d}"
        _MANDATES[mid] = {"user": user, "active": True, "used_this_cycle": 0,
                          "ledger": [],
                          "agreed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                          "notice_version": "동의 고지문 v1(2026-08)",   # 감사 대비: 무엇에 동의했는지 버전으로 남긴다
                          "scope": {"max_per_cycle": CFG["pass"]["max_per_cycle"],
                                     "free_routes_only": CFG["pass"]["free_routes_only"],
                                     "pickup": pickup or CFG["home_library"],
                                     "cancel": "언제든 해지 · 실행 결과는 매회 통지"}}
        _persist()                                        # [v0.3.1] 동의 기록 영속화
        return {"mandate_id": mid, **_MANDATES[mid]}
    mine = [k for k, v in _MANDATES.items() if v["user"] == user]
    user_mid = next((k for k in mine if _MANDATES[k]["active"]), mine[-1] if mine else None)
    m = _MANDATES.get(user_mid)
    if op == "status":
        return {"mandate_id": user_mid, **m} if m else {"active": False}
    if op == "revoke":
        if m and m["active"]:
            m["active"] = False
            m["revoked_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            _persist()                                    # [v0.3.1] 해지 즉시 영속화
        return {"revoked": bool(m), "revoked_at": m.get("revoked_at") if m else None}
    raise ValueError("op은 create/status/revoke")

_GUIDE = {
    "requested": "접수됨 — 소장관이 자료를 확보하면 이송이 시작됩니다",
    "confirmed": "자료 확보 — 다음 이송 편에 실립니다",
    "in_transit": "이송 중 — 도착하면 알림이 갑니다",
    "arrived": "도착 — 보관기한 내 미수령 시 자동 취소됩니다",
    "loaned": "대출 완료",
    "failed": "실패 — 다른 소장관 재신청 또는 대체자료(find_alternative) 확인을 권장",
    "canceled": "취소됨 — 한도는 복원되었습니다",
}

def track_request(user: str, request_no: str):
    """[v0.3] 신청 추적 — 접수 이후의 생애주기. 본인 신청만 조회할 수 있다."""
    mid = vault.resolve(user)
    r = alpas.ill_status(request_no)
    if r["member"] != mid:
        raise PermissionError("본인 신청만 조회할 수 있습니다")
    out = {"no": r["no"], "status": r["status"], "status_label": r["status_label"],
           "history": r["history"], "guidance": _GUIDE[r["status"]]}
    for k in ("pickup_due", "fail_reason", "cancel_reason", "canceled_by"):
        if k in r: out[k] = r[k]
    if r["status"] == "arrived":
        out["hold_days"] = CFG.get("hold_days", 3)
    return out

def cancel_request(user: str, request_no: str):
    """[v0.3] 신청 취소 — 본인 신청만. 취소 즉시 한도·중복목록이 복원된다."""
    mid = vault.resolve(user)
    r = alpas.ill_status(request_no)
    if r["member"] != mid:
        raise PermissionError("본인 신청만 취소할 수 있습니다")
    out = alpas.cancel_ill(request_no, "이용자 취소", by="user")
    _persist()                                            # [v0.3.1]
    return {"no": request_no, **out}

def _sim(request_no: str, event: str):
    """데모·적합성시험 전용 상태 전이 훅 — tools/list에 노출되지 않으며 운영에는 없다.
    (운영에서 상태를 바꾸는 주체는 알파스뿐이다)"""
    out = alpas.simulate(request_no, event, CFG.get("hold_days", 3))
    _persist()                                            # [v0.3.1] 상태 전이도 저장(운영: 알파스 DB가 원본)
    return out

def find_alternative(isbn13: str, user: str = None):
    import json
    alt = json.load(open(ROOT/"fixtures"/"alternatives.json", encoding="utf-8"))["alternatives"]
    a = alt.get(isbn13, {"audiobook": False, "braille": False})
    return {**a, "basis": "국가서지 대체자료종합목록(모의)",
            "chaeknarae_eligible": bool(a.get("audiobook") or a.get("braille"))}

def notify_user(user: str, event: str, message: str):
    member_id = vault.resolve(user)
    pref = alpas.member_status(member_id).get("notify_pref", "sms")
    ch = pref if pref in CFG["notify_channels"] else CFG["notify_channels"][0]
    return alpas.send_notice(member_id, ch, message)
