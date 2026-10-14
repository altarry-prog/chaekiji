# -*- coding: utf-8 -*-
"""[v0.3.1 실험실] 감사 기록 — 대행 실행의 모든 도구 호출을 한 줄씩 덧붙여 쓰는 JSONL.
각 줄은 앞 줄의 해시를 품는다(해시 사슬) → 중간 줄을 고치거나 지우면 verify()가 잡아낸다.
CHAEKIJI_AUDIT=파일경로 로 켜진다. 없으면 아무것도 쓰지 않는다.

기록하는 것: 시각, 순번, 도구 이름, 이용자 토큰의 해시(앞 12자 — 토큰 원문 아님), ISBN, 신청번호, 위임번호,
             결과(ok/denied/error), 규정 판정 요약(통과·실패 규정 이름), 실행 근거(즉시 확인/사전 위임)
기록하지 않는 것: 회원 식별자(m-…), 알림 문구, 발화 원문(길이만), 인증키
운영 전환 과제(docs/이력저장-감사기록-설계.md): 기관 감사 시스템 연계, 보존 기간, 접근 통제, 서명 키 관리."""
import os, json, hashlib, datetime

PATH = os.environ.get("CHAEKIJI_AUDIT")
_last = {"hash": None, "seq": 0}

def enabled() -> bool:
    return bool(PATH)

def _tok(t):
    return hashlib.sha256(str(t).encode("utf-8")).hexdigest()[:12] if t else None

def _init():
    """이미 있는 파일이면 마지막 줄의 해시·순번을 이어받는다."""
    if _last["hash"] is not None or not PATH or not os.path.exists(PATH): return
    last = None
    with open(PATH, encoding="utf-8") as f:
        for line in f:
            if line.strip(): last = line
    if last:
        e = json.loads(last)
        _last["hash"], _last["seq"] = e["hash"], e["seq"]

def summarize(name: str, args: dict, out, is_error: bool) -> dict:
    """도구별로 남길 만한 것만 뽑는다 — 개인정보·문구는 뺀다."""
    e = {"tool": name, "user": _tok(args.get("user")), "isbn13": args.get("isbn13"),
         "request_no": args.get("request_no"), "mandate_id": args.get("mandate_id")}
    if name == "search_item":
        e["utterance_len"] = len(args.get("utterance", ""))
    if name == "manage_mandate":
        e["op"] = args.get("op")
    if name == "_sim":
        e["event"] = args.get("event")
    if is_error:
        e["outcome"] = "error"
        e["detail"] = str(out)[:80]
        return e
    if isinstance(out, dict):
        if name in ("check_policy",) or ("checks" in out and "allowed" in out):
            e["outcome"] = "ok" if out.get("allowed") else "denied"
            e["failed_rules"] = [c["rule"] for c in out.get("checks", []) if not c["pass"]]
        elif name == "request_service":
            if out.get("accepted"):
                e["outcome"] = "ok"; e["request_no"] = out.get("receipt")
                e["authorized_by"] = out.get("authorized_by"); e["duplicate"] = bool(out.get("duplicate"))
            else:
                e["outcome"] = "denied"
                why = out.get("why")
                e["failed_rules"] = [c["rule"] for c in why if not c["pass"]] if isinstance(why, list) else [str(why)[:60]]
        elif name == "cancel_request":
            e["outcome"] = "ok" if out.get("canceled") else "denied"
        elif name == "manage_mandate":
            e["outcome"] = "ok"; e["mandate_id"] = out.get("mandate_id") or e["mandate_id"]
        elif name == "notify_user":
            e["outcome"] = "ok"; e["channel"] = out.get("channel")   # 문구는 남기지 않는다
        elif name == "track_request":
            e["outcome"] = "ok"; e["status"] = out.get("status")
        else:
            e["outcome"] = "ok"
    else:
        e["outcome"] = "ok"
    return e

def record(name: str, args: dict, out, is_error: bool):
    if not PATH: return
    _init()
    e = summarize(name, args, out, is_error)
    e = {"ts": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "seq": _last["seq"] + 1,
         **{k: v for k, v in e.items() if v not in (None, [], "")}, "prev": _last["hash"]}
    body = json.dumps(e, ensure_ascii=False, sort_keys=True)
    e["hash"] = hashlib.sha256(((_last["hash"] or "") + body).encode("utf-8")).hexdigest()
    with open(PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
    _last["hash"], _last["seq"] = e["hash"], e["seq"]

def verify(path: str):
    """사슬 검증 → (정상 여부, 줄 수, 처음 깨진 줄 번호 또는 None)"""
    prev, n = None, 0
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip(): continue
            e = json.loads(line)
            h = e.pop("hash")
            body = json.dumps(e, ensure_ascii=False, sort_keys=True)
            if e.get("prev") != prev or hashlib.sha256(((prev or "") + body).encode("utf-8")).hexdigest() != h:
                return False, n, i
            prev, n = h, n + 1
    return True, n, None

if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else PATH
    ok, n, bad = verify(p)
    print(f"{p}: {'정상' if ok else '변조 또는 손상'} — {n}줄" + (f", {bad}번째 줄에서 깨짐" if bad else ""))
    sys.exit(0 if ok else 1)
