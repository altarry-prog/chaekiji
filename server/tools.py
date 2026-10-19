# -*- coding: utf-8 -*-
"""표준 도구 10종(핵심 8종 + 확장 2종) — MCP 서버가 노출하는 전부.
에이전트는 이 함수들의 이름과 인자만 알며,
그 뒤의 정보나루·알파스·규정·금고는 커넥터가 처리한다.
v0.3: 신청 이후의 생애주기(추적·취소)와 규정 3종(연체·제외자료·중복)이 계약에 들어왔다.
v0.3.1(실험실): 관내 조회원 선택(CHAEKIJI_LOCAL_SOURCE=alpas|naru) · 영속 저장(CHAEKIJI_STORE) · 감사 기록(server.py).
v0.3.4(상담 비서): consult_request 묶음 도구(찾기→소장·대출→규정→안내문·접수 메모) · CHAEKIJI_MODE=relay|auto(키 없이 오늘 데이터)."""
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
MODE = os.environ.get("CHAEKIJI_MODE", "demo")        # demo | relay | live | auto
# [v0.3.4] 중계 주소 — 환경변수 CHAEKIJI_RELAY > 설정 relay_url. 키 값은 어디에도 없다(중계 서버만 가짐).
naru.RELAY = os.environ.get("CHAEKIJI_RELAY") or str(CFG.get("relay_url") or "")
naru.PLACES = list(CFG["libraries"])            # [10/18] 검색어에서 수령관 말(「원미도서관으로」·「상동에서」)을 뺄 때 쓰는 도서관 이름
naru.POINTS = list(CFG.get("pickup_points") or [])   # [10/19] 작은도서관 받을 곳 이름도(「상동역 칙칙폭폭에서」)
if MODE == "auto":                                    # 심사위원 기본값: 중계(오늘) → 매일 갱신 스냅샷(어제) → 8/18 픽스처
    MODE = "relay" if naru.relay_ok() else ("snapshot" if naru.snapshot_fresh() else "demo")
# 관내 소장·대출의 출처 — alpas: 도서관리시스템 실시간 연동 모의(값은 8/18 픽스처) / naru: 정보나루 bookExist(전일 기준, live·relay·snapshot이면 실조회분)
LOCAL_SOURCE = os.environ.get("CHAEKIJI_LOCAL_SOURCE", "naru" if MODE in ("relay", "live", "snapshot") else "alpas")

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
    if isbn13 in naru._hold.get("_examples", []):        # 실측이 아닌 예시 장면용 값
        return alpas.holdings_realtime(isbn13), "관내: 예시 데이터(관내에 없는 책의 흐름을 보이는 장면 — 이 책의 실제 소장과 다를 수 있음)"
    # demo: 도서관리시스템 실시간 연동을 흉내 낸 모의 커넥터 — 값은 픽스처(정보나루 실측)이므로 안내문의 조회일과 같은 출처를 밝힌다
    y, m, d = naru.FIX_ASOF.split("-")
    return alpas.holdings_realtime(isbn13), f"관내: 도서관리시스템 실시간 연동 모의(값은 {y}. {int(m)}. {int(d)}. 정보나루 실측)"

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
        if naru.LAST_META.get("unavailable"):         # [v0.3.5] 관내 상태를 모르면 전국으로 넘기지 않는다 — 「관내에 없음」이 확인된 게 아니다
            res["status_unknown"] = True
            return res
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

# ── [v0.3.4] 상담 묶음 — 창구·전화에서 사서가 지금 쓰는 판정 도구 ─────────────────────
_ROUTE_LABEL = {"visit": "바로 이용(수령관 서가에 있음)", "ill": "관내 상호대차", "reserve": "예약 권장(관내 소장분 전부 대출 중)",
                "sea": "책바다(전국 상호대차) 안내", "unknown": "도서 미확정", "check": "소장 확인 불가(창구에서 조회)"}
_MEMBER_RULE_KEYS = ("권", "연체", "중복")              # 회원 정보가 있어야 판정되는 규정(한도 3종·연체·중복)

def _ill_terms(pickup: str, eta, hold, point: bool = False) -> str:
    """[10/18] 관내 상호대차 안내의 「도착·보관·미수령」 문장 — 값과 문장은 설정에서(ill_eta_text·hold_includes_arrival_day·no_pickup_block_days).
    설정에 없으면 예전 문장(「○일 안에 받으실 수 있고」·「도착 후 ○일 안에」) 그대로.
    작은도서관 받을 곳(point)은 도착일·보관 기한을 모르므로 창구 확인으로 안내한다."""
    block = CFG.get("no_pickup_block_days")
    if point:
        return (f"관내 상호대차로 신청하시면 {pickup}도서관에서 받으실 수 있고 비용은 없습니다. "
                f"작은도서관으로 받으시면 도착일과 보관 기한은 창구에서 확인해 드립니다."
                + (f" 기한이 지나면 자동 반납되고 {block}일 동안 상호대차를 신청할 수 없습니다." if block else ""))
    eta_text = CFG.get("ill_eta_text")
    if eta_text:
        out = f"관내 상호대차로 신청하시면 {eta_text} {pickup}도서관에 도착하며 비용은 없습니다. "
    else:
        out = f"관내 상호대차로 신청하시면 {eta}일 안에 {pickup}도서관에서 받으실 수 있고 비용은 없습니다. "
    out += (f"도착한 날을 포함해 {hold}일 안에 찾아가 주세요." if CFG.get("hold_includes_arrival_day")
            else f"도착 후 {hold}일 안에 찾아가 주세요.")
    if block:
        out += f" 기한이 지나면 자동 반납되고 {block}일 동안 상호대차를 신청할 수 없습니다."
    return out

def _eun(word: str) -> str:
    """받침에 따라 은/는 — 안내문이 사람 말처럼 읽히게."""
    if not word: return "은(는)"
    ch = word[-1]
    if "가" <= ch <= "힣":
        return "은" if (ord(ch) - 0xAC00) % 28 else "는"
    return "은(는)"

def _lib_status(avail: dict, lib: str) -> str:
    if lib in avail["available_at"]: return "ok"
    if lib in avail["loaned_at"]: return "busy"
    return "none"

def _guest_policy(isbn13: str, pickup: str):
    """회원 토큰 없이 판정할 수 있는 규정만 판정하고, 회원 규정은 「창구 확인」으로 보류한다."""
    guest = {"ill_count": 0, "total_loans": 0, "loans_at": {}, "overdue_count": 0, "suspended": False, "active_isbns": []}
    if LOCAL_SOURCE == "naru":
        on_shelf = _local_holdings(isbn13)[0].get(pickup) == "ok"
    else:
        on_shelf = alpas.on_shelf(pickup, isbn13)
    v = policy.check(CFG["rules"], guest, on_shelf, pickup, item=naru.bibinfo(isbn13, mode=MODE), isbn13=isbn13)
    pending = []
    for c in v["checks"]:
        if any(k in c["rule"] for k in _MEMBER_RULE_KEYS):
            c["pass"] = None; c["detail"] = "회원 확인 필요 — 창구에서 도서관리시스템으로 확인"
            pending.append(c["rule"])
    decided = [c for c in v["checks"] if c["pass"] is not None]
    return {"allowed_so_far": all(c["pass"] for c in decided), "checks": v["checks"], "pending": pending,
            "basis": "회원 토큰 없이 판정 — 비치·제외자료 규정만 확정, 한도·연체·중복은 창구 확인"}

def _unverified_item(item) -> bool:
    """[v0.3.5] 정보나루 서지만으로는 자료 유형(비도서 등)·신착 여부를 알 수 없다 — 픽스처에 없는 책의 서지."""
    return (not item) or "미제공" in str(item.get("basis", ""))

def _official_link(title: str, isbn13: str, by_title: bool = False):
    """[v0.3.4] 공식 누리집(자료검색) 링크 — 설정 official_search_url의 {title}/{isbn13}을 채운다.
    「그 책 화면까지」만 — 접수는 이용자가 누리집에 로그인해 직접 한다(이 도구는 접수하지 않는다).
    [10/18] 부천은 ISBN으로 그 판본 화면까지(담당자 확인). 소장을 확인하지 못한 책(by_title)은 그 판본이 없을 수도 있어
    official_search_url_title(제목 검색)이 있으면 그것으로."""
    tmpl = str((by_title and CFG.get("official_search_url_title")) or CFG.get("official_search_url") or "").strip()
    if not tmpl:
        return None
    from urllib.parse import quote
    return tmpl.replace("{title}", quote(title, safe="")).replace("{isbn13}", quote(isbn13, safe=""))

def _pickup_name(p):
    """[10/18] 「꿈빛도서관」·「부천시립 꿈빛도서관」·「꿈빛 도서관」도 설정의 짧은 이름(「꿈빛」)으로. 모르면 그대로 둔다(뒤에서 설정에 없는 도서관 오류)."""
    s = "".join(str(p).split())
    for pre in (CFG["city"] + "시립", CFG["city"] + "시"):
        if s.startswith(pre) and len(s) > len(pre):
            s = s[len(pre):]; break
    if s in CFG["libraries"]: return s
    for suf in ("도서관", "관"):
        if s.endswith(suf) and s[: -len(suf)] in CFG["libraries"]: return s[: -len(suf)]
    pts = {"".join(x.split()): x for x in (CFG.get("pickup_points") or [])}   # [10/18] 작은도서관 받을 곳 — 띄어쓰기·「(작은)도서관」 무시
    for cand in (s, s[:-5] if s.endswith("작은도서관") else "", s[:-3] if s.endswith("도서관") else ""):
        if cand and cand in pts: return pts[cand]
    return str(p)

def consult_request(utterance: str, pickup: str = None, lang: str = "ko", user: str = None):
    """[v0.3.4] 상담 묶음 — 이용자의 말 한마디로 ① 도서 특정 ② 관내 소장·대출 상태 ③ 상호대차 가능 여부·갈래 판정
    ④ 이용자 안내문 ⑤ 접수 메모까지 한 번에. 회원 토큰(user)이 있으면 규정 7종을 전부 판정하고, 없으면 회원 규정은 창구 확인으로 보류.
    접수는 하지 않는다(접수는 request_service 또는 창구에서 사서가)."""
    pickup = _pickup_name(pickup or CFG["home_library"])
    points = list(CFG.get("pickup_points") or [])
    is_point = pickup in points and pickup not in CFG["libraries"]   # [10/18] 작은도서관 받을 곳 — 정보나루 자료가 없어 서가·도착일·보관은 창구 확인
    if pickup not in CFG["libraries"] and not is_point:
        raise ValueError(f"수령관 「{pickup}」은(는) 설정에 없는 도서관입니다: {', '.join(list(CFG['libraries']) + points)}")
    eta, hold = CFG.get("ill_eta_days", "2~3"), CFG.get("hold_days", 3)
    found = search_item(utterance, lang)
    base = {"utterance": utterance, "pickup": pickup, "lang": lang, "mode": MODE,
            "disclaimer": "대출 가능 여부는 정보나루 조회일 전일 기준이며, 최종 확인과 접수는 창구에서 합니다."}
    if not found.get("found") and found.get("unavailable"):   # [v0.3.5] 정보나루에 닿지 못해 찾지 못함 — 되묻지 말고 창구 조회
        return {**base, "found": False, "route": "check", "route_label": _ROUTE_LABEL["check"],
                "book": None, "reason": found.get("reason"), "candidates": [],
                "notice": "지금 정보나루에 연결되지 않아 책을 찾지 못했습니다. 창구에서 도서관리시스템으로 찾아 드리겠습니다.",
                "desk_memo": f"[조회 불가] 문의 「{utterance}」 — 정보나루 연결 안 됨, 창구에서 도서관리시스템으로 조회"}
    if not found.get("found"):
        out = {**base, "found": False, "route": "unknown", "route_label": _ROUTE_LABEL["unknown"],
               "book": None, "reason": found.get("reason"), "candidates": found.get("candidates", []),
               "notice": "말씀하신 책을 아직 찾지 못했습니다. 저자나 출판사, 대략의 내용을 조금 더 알려 주시겠어요?",
               "desk_memo": f"[미확정] 문의 「{utterance}」 — 서지 재확인 필요"}
        if found.get("candidate_books"):              # [10/19] 검색은 됐지만 문의와 맞는 책을 못 고름 — 후보를 보여 주고 되묻는다
            out["candidate_books"] = found["candidate_books"]
            out["desk_memo"] += "\n검색 후보: " + " / ".join(
                f"{b.get('title') or ''}({b.get('author') or ''}, {b.get('publisher') or ''} {b.get('year') or ''})" for b in found["candidate_books"])
        return out
    isbn = found["isbn13"]; title = found.get("title") or isbn
    avail = check_availability(isbn)
    unknown = bool(avail.get("status_unknown"))       # [v0.3.5] 정보나루 조회 실패 + 픽스처에도 없는 책
    at_pickup = "unknown" if unknown else ("point" if is_point else _lib_status(avail, pickup))
    others_ok = [l for l in avail["available_at"] if l != pickup]
    nation = avail.get("nation")
    if unknown:
        route, from_lib = "check", None
    elif at_pickup == "ok":
        route, from_lib = "visit", pickup
    elif others_ok:
        route, from_lib = "ill", others_ok[0]
    elif avail["loaned_at"] or at_pickup == "busy":
        route, from_lib = "reserve", None
    else:
        route, from_lib = "sea", None
    if user:
        pol = check_policy(user, isbn, pickup); pol = {"allowed_so_far": pol["allowed"], "checks": pol["checks"], "pending": [],
                                                        "basis": "회원 토큰으로 규정 7종 전부 판정"}
    else:
        pol = _guest_policy(isbn, pickup)
    if unknown:                                       # 수령관 비치 여부도 모르므로 비치 규정까지 창구 확인으로 돌린다
        for c in pol["checks"]:
            if "비치" in c["rule"] and c["pass"] is not None:
                c["pass"] = None; c["detail"] = "소장·대출 상태 확인 불가 — 창구에서 도서관리시스템으로 확인"
                pol["pending"].append(c["rule"])
        pol["allowed_so_far"] = all(c["pass"] for c in pol["checks"] if c["pass"] is not None)
    if is_point:                                      # [10/18] 작은도서관 서가 비치 여부는 정보나루에 없다 — 「통과」로 두지 않는다
        for c in pol["checks"]:
            if "비치" in c["rule"] and c["pass"] is not None:
                c["pass"] = None; c["detail"] = "작은도서관 서가 비치 여부는 정보나루에 없어 창구에서 확인"
                pol["pending"].append(c["rule"])
        pol["allowed_so_far"] = all(c["pass"] for c in pol["checks"] if c["pass"] is not None)
    if _unverified_item(naru.bibinfo(isbn, mode=MODE)):   # 자료 유형·신착을 모르면 제외 자료 규정도 창구 확인(「통과」로 두지 않는다)
        for c in pol["checks"]:
            if c["rule"] == "상호대차 제외 자료 아님" and c["pass"] is not None:
                c["pass"] = None; c["detail"] = "자료 유형·신착 여부는 정보나루에 없어 창구에서 확인"
                pol["pending"].append(c["rule"])
        pol["allowed_so_far"] = all(c["pass"] for c in pol["checks"] if c["pass"] is not None)
    asof = naru.LAST_META.get("asof") or naru.FIX_ASOF
    y, m, d = asof.split("-"); asof_k = f"{y}. {int(m)}. {int(d)}."
    n_ok = len(avail["available_at"]); n_busy = len(avail["loaned_at"])
    disp = f"{naru._main_title(title)} {naru.vol_label(found['vol'])}" if found.get("vol") else str(title).strip()   # [10/19] 권차가 있으면 「흔한남매 1권」처럼 · 서명 끝 빈칸은 뗀다
    t_ = f"『{disp}』{_eun(disp)}"
    if route == "visit":
        notice = (f"{t_} 지금 {pickup}도서관 서가에 있어 바로 대출하실 수 있습니다. "
                  f"받으실 도서관에 있는 자료는 상호대차 신청 대상이 아니니 방문해 주세요.")
    elif route == "ill" and is_point:                # [10/18] 작은도서관에서 받기 — 그곳 소장 여부는 말하지 않는다(모름)
        notice = (f"{t_} {from_lib}도서관 등 {CFG['city']}시립도서관 {n_ok}곳에 대출 가능 상태입니다. "
                  + _ill_terms(pickup, eta, hold, point=True))
    elif route == "ill":
        where = "대출 중이" if at_pickup == "busy" else "없"
        notice = (f"{t_} {pickup}도서관에는 {where}지만 {from_lib}도서관 등 {CFG['city']}시립도서관 {n_ok}곳에 대출 가능 상태입니다. "
                  + _ill_terms(pickup, eta, hold))
    elif route == "reserve":
        notice = (f"{t_} {CFG['city']}시립도서관 {n_busy}곳이 소장하고 있지만 지금은 모두 대출 중입니다. "
                  + ("먼저 예약해 두시면, 책이 반납될 때 상호대차로 바꿔 신청할 수 있습니다" if CFG.get("reserve_converts_to_ill")
                     else "상호대차 대신 예약을 권해 드립니다")
                  + "(책바다는 관내에 없는 자료가 대상입니다).")
    elif route == "check":
        notice = (f"{t_} 지금 {CFG['city']}시립도서관의 소장·대출 상태를 확인하지 못했습니다(정보나루 조회가 되지 않았습니다). "
                  f"창구에서 도서관리시스템으로 확인해 드리겠습니다.")
    else:
        cnt = (nation or {}).get("found_count")
        notice = (f"{t_} {CFG['city']}시립도서관 {len(CFG['libraries'])}곳에 소장되어 있지 않습니다. 전국 상호대차(책바다)로 신청하실 수 있으며 "
                  f"왕복 택배비가 듭니다." + (f" 정보나루 기준 다른 지역 {cnt}곳 소장입니다." if cnt else ""))
    example = isbn in naru._hold.get("_examples", []) and (LOCAL_SOURCE != "naru" or naru.LAST_META.get("example"))
    if route == "check":                              # 조회한 자료가 없으므로 날짜를 찍지 않는다
        pass
    elif example:                                     # 실측이 아닌 예시 장면 — 날짜 대신 그렇게 밝힌다
        notice += " (예시 데이터 — 이 책의 실제 소장·대출과 다를 수 있습니다)"
    else:
        notice += f" (대출 상태는 정보나루 {asof_k} 조회, 전일 기준)"
    if pol["pending"]:
        notice += " 회원 한도·연체 여부는 창구에서 확인해 드립니다."
    others = found.get("same_title_others") or []    # [10/19] 같은 제목·다른 저자의 책이 함께 검색됨 — 고른 책을 밝히고 확인을 청한다
    if others:
        notice += (" 같은 제목의 다른 책도 있습니다(" + " / ".join(f"{b.get('author') or ''} · {b.get('publisher') or ''} {b.get('year') or ''}"
                                                          for b in others) + ") — 찾으시는 책의 저자가 다르면 알려 주세요.")
    alt = []                                          # [10/19] 판본 보정 — 고른 판이 관내에 없을 때 같은 작품의 다른 판 하나가 관내에 있으면 알린다. 갈래는 그대로
    if route == "sea":                               # 하나만 본다 — 원격 판(Cloudflare 무료)은 요청당 외부 호출 50회 한도라 관내 조회(16회)를 두 번 더 하면 넘을 수 있다
        for b in (found.get("same_work_editions") or [])[:1]:
            rt2, _ = _local_holdings(b["isbn13"])
            if LOCAL_SOURCE == "naru" and (naru.LAST_META.get("unavailable") or (naru.LAST_META.get("asof") or naru.FIX_ASOF) != asof):
                continue                              # 조회가 안 됐거나 조회일이 다르면 섞지 않는다
            ok2 = sorted(l for l, s in rt2.items() if s == "ok"); busy2 = sorted(l for l, s in rt2.items() if s == "busy")
            if ok2 or busy2:
                alt.append({**b, "available_at": ok2, "loaned_at": busy2, "official_link": _official_link(b.get("title") or b["isbn13"], b["isbn13"])})
    if alt:
        def _alt_where(b):
            ed = " ".join(x for x in (b.get("publisher") or "", f"{b['year']}년" if b.get("year") else "") if x) or f"ISBN {b['isbn13']}"
            if pickup in b["available_at"]: return f"{ed} 판은 {pickup}도서관 서가에 있습니다"
            if b["available_at"]: return f"{ed} 판은 {b['available_at'][0]}도서관 등 {len(b['available_at'])}곳에 대출 가능합니다"
            return f"{ed} 판은 {len(b['loaned_at'])}곳이 소장하고 있지만 모두 대출 중입니다"
        lk = alt[0]["official_link"]
        notice += (" 같은 책의 다른 판은 관내에 있습니다: " + "; ".join(_alt_where(b) for b in alt)
                   + ". 판이 달라도 괜찮으시면 그 판으로 이용하실 수 있습니다" + (f"(그 판의 공식 누리집 화면: {lk})." if lk else "."))
    bad = [c for c in pol["checks"] if c["pass"] is False and not (route == "visit" and "비치" in c["rule"])]
    if bad:                                           # 바로 이용 갈래에서 비치 규정은 곧 그 갈래의 이유이므로 되풀이하지 않는다
        notice += " 다만 " + "; ".join(f"{c['rule']}({c['detail']})" for c in bad) + " — 이 조건을 먼저 확인해야 합니다."
    link = _official_link(title, isbn, by_title=(route == "check")) if route in ("visit", "ill", "reserve", "check") else None   # 관내에 없는 책(책바다)은 누리집에 없다
    if link:
        tail = {"visit": "이 책 보기", "ill": "이 책 보기·신청(로그인 뒤 「상호대차 신청」 — 접수는 이용자가 직접)",
                "reserve": "이 책 보기·예약(로그인 뒤 「예약」)", "check": "이 책의 소장·대출 상태 보기"}[route]
        notice += f" 공식 누리집에서 {tail}: {link}"
    memo_lines = [f"도서: {str(title).strip()}" + (f" [{naru.vol_label(found['vol'])}]" if found.get("vol") else "") + f" ({found.get('author') or ''}) ISBN {isbn}" + (f" · 같은 제목 다른 책 {len(others)}건 — 저자 확인" if others else ""),
                  f"갈래: {_ROUTE_LABEL[route]}" + (f" · 소장관 {from_lib}" if from_lib else ""),
                  (f"수령관: {pickup}도서관 (작은도서관 — 서가 비치·도착일·보관 기한은 창구 확인)" if is_point else
                   f"수령관: {pickup} (현재 {'서가 비치' if at_pickup == 'ok' else '대출 중' if at_pickup == 'busy' else '확인 불가' if unknown else '미소장'})"),
                  ("대출 가능 관: 확인 불가 / 대출 중: 확인 불가" if unknown else
                   f"대출 가능 관: {', '.join(avail['available_at']) or '없음'} / 대출 중: {', '.join(avail['loaned_at']) or '없음'}"),
                  f"근거: {avail['basis']}",
                  f"규정: {sum(1 for c in pol['checks'] if c['pass'] is True)}건 통과 · {sum(1 for c in pol['checks'] if c['pass'] is False)}건 불가 · {len(pol['pending'])}건 창구 확인",
                  "접수: 창구에서 도서관리시스템 입력(이 도구는 접수하지 않음)"]
    for b in alt:                                     # [10/19] 판본 보정 — 다른 판의 관내 소장(접수 전 판 확인)
        memo_lines.insert(-1, f"다른 판 관내: {b.get('publisher') or ''} {b.get('year') or ''} ISBN {b['isbn13']} — "
                              f"대출 가능 {', '.join(b['available_at']) or '없음'} / 대출 중 {', '.join(b['loaned_at']) or '없음'}")
    next_tool = None
    if route == "ill" and user:
        next_tool = {"tool": "request_service", "arguments": {"user": user, "isbn13": isbn, "from_lib": from_lib, "pickup": pickup,
                                                              "confirmed_by_user": True}, "note": "이용자 확인 뒤에만"}
    return {**base, "found": True, "route": route, "route_label": _ROUTE_LABEL[route], "from_lib": from_lib,
            "book": {"isbn13": isbn, "title": title, "author": found.get("author"), "publisher": found.get("publisher"),
                     "year": found.get("year"), "evidence": found.get("evidence"), **({"vol": found["vol"]} if found.get("vol") else {})},
            "availability": {"at_pickup": at_pickup, "available_at": avail["available_at"], "loaned_at": avail["loaned_at"],
                             "nation": nation, "basis": avail["basis"], "asof": asof},
            "policy": pol, "notice": notice, "official_link": link,
            "translate_to": None if lang == "ko" else lang,
            "desk_memo": "\n".join(memo_lines), "next_tool": next_tool, **({"same_title_others": others} if others else {}),
            **({"other_editions": alt} if alt else {})}

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
