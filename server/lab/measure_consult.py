#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""원격 상담 비서(/mcp) 처리 시간 실측 — 이용자 문의 15건을 실제 주소로 보내 걸린 시간과 판정을 기록한다.

무엇을 재나: 상담 묶음 도구(consult_request) 한 번이 답을 돌려줄 때까지의 시간(벽시계, 네트워크 포함).
  사람이 문의를 듣고 도서관리시스템에서 확인하는 시간은 재지 않는다(그건 사람의 시험으로만 잴 수 있다).
어디서 재나: 깃허브 액션(measure-consult.yml) — 미국 쪽 서버. 한국에서 부르면 더 빠를 것으로 추정.
기록: lab/out/consult_timing_YYYY-MM-DD.json(원자료) · .md(요약). 키·개인정보 없음(문의는 책 제목뿐).
정보나루 호출: 매일 갱신 자료에 있는 책은 0회, 없는 책은 1회(서지) + 1 + 소장관 수 — 하루 한도(500건)를 생각해 15건으로 묶는다.
실행: python3 lab/measure_consult.py [--url https://…/mcp] [--out lab/out]"""
import argparse, datetime, json, statistics, time, urllib.error, urllib.request
from pathlib import Path

KST = datetime.timezone(datetime.timedelta(hours=9))
UA = "chaekiji-measure/1.0 (+https://github.com/altarry-prog/chaekiji)"
# (문의 — 모델이 넘기듯 제목 위주, 받을 도서관). 앞 5건은 매일 갱신 목록의 시연 도서, 뒤 10건은 목록 밖의 책.
CASES = [
    ("나미야 잡화점의 기적", "상동"), ("소년이 온다", "꿈빛"), ("불편한 편의점", "원미"),
    ("설민석의 한국사 대모험", "상동"), ("지구 끝의 온실", "송내"),
    ("채식주의자", "상동"), ("작별하지 않는다", "역곡"), ("아몬드", "상동"), ("파친코", "심곡"),
    ("세이노의 가르침", "원미"), ("하얼빈", "상동"), ("데미안", "꿈여울"), ("어린 왕자", "상동"),
    ("82년생 김지영", "도당"), ("돈의 속성", "북부"),
]


def rpc(url, body, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
                                 headers={"User-Agent": UA, "Content-Type": "application/json",
                                          "Accept": "application/json, text/event-stream"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return (json.loads(raw) if raw else None), round((time.perf_counter() - t0) * 1000)


def source_of(basis):
    if not basis: return "—"
    if "매일 갱신" in basis: return "오늘 새벽 자료"
    if "픽스처" in basis or "예시" in basis: return "8/18 실측값(복귀)"
    if "중계" in basis: return "그 자리 조회"
    return basis[:20]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://chaekiji-relay.altarry2.workers.dev/mcp")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "out"))
    a = ap.parse_args()
    now = datetime.datetime.now(KST)
    _, init_ms = rpc(a.url, {"jsonrpc": "2.0", "id": 0, "method": "initialize",
                             "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "measure", "version": "1"}}})
    rows = []
    for i, (q, pickup) in enumerate(CASES, 1):
        try:
            b, ms = rpc(a.url, {"jsonrpc": "2.0", "id": i, "method": "tools/call",
                                "params": {"name": "consult_request", "arguments": {"utterance": q, "pickup": pickup}}})
            res = b["result"]; txt = res["content"][0]["text"]
            if res.get("isError"):
                rows.append({"no": i, "ask": q, "pickup": pickup, "ms": ms, "ok": False, "error": txt[:160]}); continue
            o = json.loads(txt); av = o.get("availability") or {}
            rows.append({"no": i, "ask": q, "pickup": pickup, "ms": ms, "ok": True, "found": o.get("found"),
                         "title": (o.get("book") or {}).get("title"), "isbn13": (o.get("book") or {}).get("isbn13"),
                         "route": o.get("route"), "route_label": o.get("route_label"), "asof": av.get("asof"),
                         "source": source_of(av.get("basis")), "available": len(av.get("available_at") or []),
                         "loaned": len(av.get("loaned_at") or []), "pending_rules": len((o.get("policy") or {}).get("pending") or []),
                         "notice_chars": len(o.get("notice") or ""), "memo_lines": len((o.get("desk_memo") or "").splitlines())})
        except Exception as e:                            # 실패도 그대로 남긴다
            rows.append({"no": i, "ask": q, "pickup": pickup, "ms": None, "ok": False, "error": f"{type(e).__name__}: {str(e)[:120]}"})
        time.sleep(1.0)                                   # 상대 서버(정보나루) 부담을 줄이려 1초씩 쉰다
    ok = [r for r in rows if r["ok"]]
    ms = [r["ms"] for r in ok]
    by = {}
    for r in ok: by.setdefault(r["source"], []).append(r["ms"])
    summary = {"time": now.strftime("%Y-%m-%d %H:%M KST"), "where": "깃허브 액션(미국 쪽 서버) → Cloudflare(원격 상담 비서) → 정보나루",
               "url": a.url, "cases": len(rows), "ok": len(ok), "init_ms": init_ms,
               "median_ms": round(statistics.median(ms)) if ms else None, "mean_ms": round(statistics.mean(ms)) if ms else None,
               "max_ms": max(ms) if ms else None, "min_ms": min(ms) if ms else None,
               "by_source": {k: {"n": len(v), "median_ms": round(statistics.median(v))} for k, v in by.items()},
               "routes": {k: sum(1 for r in ok if r.get("route_label") == k) for k in sorted({r.get("route_label") for r in ok if r.get("route_label")})}}
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    day = now.strftime("%Y-%m-%d")
    (out / f"consult_timing_{day}.json").write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    sec = lambda v: "—" if v is None else f"{v / 1000:.1f}초"
    L = [f"# 원격 상담 비서 처리 시간 실측 — {summary['time']}", "",
         f"- 무엇을: 이용자 문의 {len(rows)}건을 상담 묶음 도구(`consult_request`)에 한 건씩 보내 답이 올 때까지의 시간(네트워크 포함)",
         f"- 어디서: {summary['where']} · 한국에서 부르면 더 빠를 것으로 추정",
         "- 재지 않은 것: 사람이 문의를 듣고 도서관리시스템에서 확인하는 시간 — 사람의 시험으로만 잴 수 있다",
         "- 대출 상태는 정보나루 조회일 전일 기준 · 이 측정의 어떤 상담도 접수로 이어지지 않았다", "",
         "## 한눈에", "",
         f"- 성공 {len(ok)}/{len(rows)}건 · 가운데값 **{sec(summary['median_ms'])}** · 평균 {sec(summary['mean_ms'])} · 가장 오래 {sec(summary['max_ms'])}"]
    for k, v in summary["by_source"].items():
        L.append(f"- {k}: {v['n']}건 · 가운데값 {sec(v['median_ms'])}")
    L.append("- 판정 갈래: " + " · ".join(f"{k} {n}건" for k, n in summary["routes"].items()))
    L += ["", "## 문의별", "", "| 번호 | 문의 | 판정 | 자료 | 시간 |", "|---|---|---|---|---|"]
    for r in rows:
        if r["ok"]:
            t = r.get("title") or "(못 찾음)"
            L.append(f"| {r['no']} | {r['ask']} → {t} | {r.get('route_label') or '—'} | {r.get('source')} | {sec(r['ms'])} |")
        else:
            L.append(f"| {r['no']} | {r['ask']} | 실패 | — | {sec(r['ms'])} |")
    fails = [r for r in rows if not r["ok"]]
    if fails:
        L += ["", "실패 기록: " + "; ".join(f"{r['no']}번 {r.get('error', '')}" for r in fails)]
    L += ["", "원자료: `consult_timing_" + day + ".json` · 측정 스크립트: `lab/measure_consult.py` · 사람이 고치지 않은 기록"]
    (out / f"consult_timing_{day}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
