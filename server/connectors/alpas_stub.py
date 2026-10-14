# -*- coding: utf-8 -*-
"""알파스 커넥터 — 실행 계층 (모의 구현).
이 파일의 함수 목록이 곧 벤더에게 요청할 연동 명세다:
[벤더 구현 ①~⑦] 일곱 함수를 실제 알파스 API/DB 호출로 바꾸면 커넥터가 완성되고,
같은 시스템을 쓰는 전국 도서관이 그 커넥터를 재사용한다.

v0.3 — 신청은 접수로 끝나지 않는다. 실무의 생애주기를 계약에 넣었다:
  requested(접수) → confirmed(자료 확보) → in_transit(이송 중)
  → arrived(도착·수령 대기, 보관기한) → loaned(대출 완료)
  예외: failed(서가 부재·대출 경합) / canceled(이용자·미수령·실패)
모의 데이터는 fixtures/에 있으며 상태 변화는 메모리에만 기록된다."""
import json, datetime
from pathlib import Path

FIX = Path(__file__).resolve().parent.parent / "fixtures"
_hold = json.load(open(FIX/"holdings.json", encoding="utf-8"))["holdings"]
_members = json.load(open(FIX/"members.json", encoding="utf-8"))["members"]
_requests, _outbox = {}, []          # 운영: 알파스 DB 트랜잭션 / 알림 게이트웨이

STATUS_LABEL = {"requested": "접수", "confirmed": "자료 확보", "in_transit": "이송 중",
                "arrived": "도착·수령 대기", "loaned": "대출 완료",
                "failed": "실패", "canceled": "취소"}

def _now(): return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

def _release(r):
    """실패·취소 시 한도와 진행중 목록을 되돌린다 — 자동화일수록 되돌림이 계약이어야 한다."""
    m = _members[r["member"]]
    m["ill_count"] = max(0, m["ill_count"] - 1)
    if r["isbn13"] in m.get("active_isbns", []):
        m["active_isbns"].remove(r["isbn13"])

def member_status(member_id: str) -> dict:            # [벤더 구현 ①] 회원 현황(연체·정지·진행중 포함)
    m = _members.get(member_id)
    if not m: raise KeyError("회원 없음")
    return m

def holdings_realtime(isbn13: str) -> dict:           # [벤더 구현 ②] 관내 실시간 재고
    h = _hold.get(isbn13)
    if h is None: return {}
    return dict(h)                                    # ok=서가에 있음, busy=대출중, none=미소장

def on_shelf(lib: str, isbn13: str) -> bool:          # [벤더 구현 ③] 특정관 서가 비치 여부
    return _hold.get(isbn13, {}).get(lib) == "ok"

def create_ill(member_id, isbn13, from_lib, pickup,   # [벤더 구현 ④] 상호대차 신청 생성
               client_ref=None):                      #   v0.3: 동일 client_ref 재수신 시 기존 신청 반환(이중 방지)
    if client_ref:
        for r in _requests.values():
            if (r["member"] == member_id and r.get("client_ref") == client_ref
                    and r["status"] not in ("canceled", "failed")):
                return {"no": r["no"], "duplicate": True}
    no = f"ILL-{datetime.date.today():%Y%m%d}-{len(_requests)+1:04d}"
    _requests[no] = {"no": no, "member": member_id, "isbn13": isbn13,
                     "from": from_lib, "pickup": pickup, "client_ref": client_ref,
                     "status": "requested",
                     "history": [{"status": "requested", "at": _now()}]}
    m = _members[member_id]
    m["ill_count"] += 1                               # 한도 즉시 반영
    m.setdefault("active_isbns", []).append(isbn13)
    return {"no": no, "duplicate": False}

def find_by_ref(member_id, client_ref):
    """[벤더 구현 ④의 일부] client_ref로 기존 신청 조회 — 재시도 멱등성의 근거."""
    if not client_ref: return None
    for r in _requests.values():
        if (r["member"] == member_id and r.get("client_ref") == client_ref
                and r["status"] not in ("canceled", "failed")):
            return r["no"]
    return None

def send_notice(member_id, channel, message):         # [벤더 구현 ⑤] 알림 발송
    _outbox.append({"member": member_id, "channel": channel, "message": message})
    return {"queued": True, "channel": channel}

def ill_status(no: str) -> dict:                      # [벤더 구현 ⑥] 신청 상태 조회 (v0.3)
    r = _requests.get(no)
    if not r: raise KeyError("해당 신청 없음")
    return dict(r, status_label=STATUS_LABEL[r["status"]])

def cancel_ill(no: str, reason: str, by="user"):      # [벤더 구현 ⑦] 신청 취소 (v0.3)
    r = _requests.get(no)
    if not r: raise KeyError("해당 신청 없음")
    if r["status"] in ("loaned", "canceled"):
        return {"canceled": False, "why": f"현재 상태({STATUS_LABEL[r['status']]})에서는 취소 불가"}
    _release(r)
    r["status"], r["cancel_reason"], r["canceled_by"] = "canceled", reason, by
    r["history"].append({"status": "canceled", "at": _now(), "reason": reason})
    return {"canceled": True, "restored_limit": True}

def simulate(no: str, event: str, hold_days: int = 3):
    """데모·시험 전용 — 운영에는 존재하지 않는다(상태 변경의 주체는 알파스).
    confirm/transit/arrive/expire(미수령)/fail_shelf(서가부재·경합)"""
    r = _requests[no]
    if event == "confirm":
        r["status"] = "confirmed"
    elif event == "transit":
        r["status"] = "in_transit"
    elif event == "arrive":
        r["status"] = "arrived"
        r["pickup_due"] = str(datetime.date.today() + datetime.timedelta(days=hold_days))
    elif event == "expire":
        _release(r)
        r["status"] = "canceled"
        r["cancel_reason"] = f"보관기한({hold_days}일) 경과 미수령"
        r["canceled_by"] = "system"
    elif event == "fail_shelf":
        _release(r)
        r["status"] = "failed"
        r["fail_reason"] = "서가 부재(전산 소장·실물 없음) 또는 확인~이송 사이 대출 경합"
    else:
        raise ValueError("event: confirm/transit/arrive/expire/fail_shelf")
    r["history"].append({"status": r["status"], "at": _now()})
    return ill_status(no)
