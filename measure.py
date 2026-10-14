#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[2·3주차] 실측 — 도서 1종을 처리할 때 정보나루를 몇 번 부르고 몇 초 걸리는가.
참조 서버의 도구 함수를 그대로 부른다(search_item → check_availability → check_policy).
MCP 전송 계층만 빼고 같은 코드가 돌므로 호출 수·시간은 AI 도구에서 부를 때와 같다.

실행 예(live):
  read -s NARU_KEY; export NARU_KEY
  python3 lab/measure.py --titles lab/out/titles.csv --max-calls 300
  python3 lab/measure.py --titles lab/out/titles.csv --config config/<다른도시>.yaml   # 3주차 확산 확인
연습(네트워크 없음): python3 lab/measure.py --demo

결과:
  lab/out/measure_<날짜>.csv        도서별 호출 수·소요 시간·소장 결과
  lab/out/measure_<날짜>_요약.md    보고서에 옮길 요약표
  lab/out/기록지A_<날짜>.csv         실측 A(전일 기준 대조) 표본 — 정보나루 값은 채워져 있고 시스템 값만 손으로 적는다
다시 실행하면 이미 잰 도서는 건너뛴다(하루 한도 500회에 맞춰 며칠에 나눠 돌릴 수 있다)."""
import os, sys, csv, time, argparse, datetime, statistics
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ap = argparse.ArgumentParser()
ap.add_argument("--titles", default=str(ROOT/"lab"/"out"/"titles.csv"))
ap.add_argument("--config", default=str(ROOT/"config"/"bucheon.yaml"))
ap.add_argument("--max-calls", type=int, default=300, help="이번 실행에서 쓸 호출 상한")
ap.add_argument("--limit", type=int, default=0, help="도서 수 상한(0=전부)")
ap.add_argument("--sleep", type=float, default=0.3, help="도서 사이 쉬는 시간(초)")
ap.add_argument("--demo", action="store_true", help="픽스처로 연습(네트워크·키 불필요)")
ap.add_argument("--no-edition-fix", action="store_true", help="판본 보정(다른 ISBN 재조회) 끄기")
ap.add_argument("--sheet-a-rows", type=int, default=50, help="기록지A 표본 행 수")
ap.add_argument("--tag", default="", help="결과 파일 이름에 붙일 표시(예: gangnam)")
a = ap.parse_args()

os.environ["CHAEKIJI_CONFIG"] = a.config
os.environ["CHAEKIJI_MODE"] = "demo" if a.demo else "live"
os.environ["CHAEKIJI_LOCAL_SOURCE"] = "naru"
os.environ.pop("CHAEKIJI_STORE", None); os.environ.pop("CHAEKIJI_AUDIT", None)   # 측정은 저장·감사 없이
if not a.demo and not os.environ.get("NARU_KEY"):
    sys.exit("NARU_KEY가 없습니다:  read -s NARU_KEY; export NARU_KEY   (연습은 --demo)")

import tools
from connectors import naru

today = datetime.date.today().isoformat()
tag = f"_{a.tag}" if a.tag else ("_demo" if a.demo else "")
OUT = ROOT/"lab"/"out"; OUT.mkdir(parents=True, exist_ok=True)
out_csv = OUT/f"measure_{today}{tag}.csv"
out_md  = OUT/f"measure_{today}{tag}_요약.md"
sheet_a = OUT/f"기록지A_{today}{tag}.csv"
FIELDS = ["n", "title", "isbn_csv", "isbn_found", "edition_match", "edition_fixed", "found",
          "holding_count", "ok", "busy", "none", "home_status", "nation_found", "policy_allowed",
          "calls_search", "calls_local", "calls_policy", "calls_nation", "calls_total",
          "ms_search", "ms_local", "ms_policy", "ms_nation", "ms_total", "note"]

def load_titles():
    if a.demo:
        return [{"title": b["title"], "isbn13": b["isbn13"]} for b in naru._cat["books"][:5]]
    with open(a.titles, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def done_keys():
    if not out_csv.exists(): return set()
    with open(out_csv, encoding="utf-8-sig") as f:
        return {r["title"] for r in csv.DictReader(f)}

def phase(fn):
    n0, t0 = len(naru.CALLS), time.perf_counter()
    out = fn()
    return out, len(naru.CALLS) - n0, round((time.perf_counter() - t0) * 1000)

def measure_one(n, row):
    r = {"n": n, "title": row["title"], "isbn_csv": row.get("isbn13", ""), "note": ""}
    s, r["calls_search"], r["ms_search"] = phase(lambda: tools.search_item(row["title"]))
    r["found"] = bool(s.get("found"))
    if not r["found"]:
        r["note"] = "검색 불일치 — " + str(s.get("reason", ""))
        isbn = row.get("isbn13") or ""
        if not isbn:
            r.update(calls_local=0, ms_local=0, calls_policy=0, ms_policy=0, calls_nation=0, ms_nation=0)
            r["isbn_found"] = ""; return r
        r["note"] += " → 목록의 ISBN으로 진행"
    else:
        isbn = s["isbn13"]
    r["isbn_found"] = isbn
    r["edition_match"] = (isbn == row.get("isbn13")) if row.get("isbn13") else ""
    r["edition_fixed"] = False
    av, r["calls_local"], r["ms_local"] = phase(lambda: tools.check_availability(isbn))
    hc = av.get("holding_count") or 0
    # 판본 보정: 검색이 준 판본이 관내에 없고 다른 후보가 있으면 후보로 다시 본다(최대 2개)
    if hc == 0 and not a.no_edition_fix:
        cands = [c for c in (s.get("candidates") or []) + [row.get("isbn13") or ""] if c and c != isbn]
        for c in cands[:2]:
            av2, dc, dm = phase(lambda: tools.check_availability(c))
            r["calls_local"] += dc; r["ms_local"] += dm
            if (av2.get("holding_count") or 0) > 0:
                av, isbn, hc, r["edition_fixed"] = av2, c, av2.get("holding_count"), True
                r["isbn_found"] = c; r["note"] += f" 판본 보정({c})"
                break
    r["holding_count"] = hc
    r["ok"], r["busy"] = len(av["available_at"]), len(av["loaned_at"])
    r["none"] = len(tools.CFG["libraries"]) - r["ok"] - r["busy"]
    r["home_status"] = av["home_status"]
    r["nation_found"] = av.get("nation", {}).get("found_count", "") if "nation" in av else ""
    # 전국 폴백은 check_availability 안에서 일어났다 — 호출 수를 나눠 적는다
    r["calls_nation"] = 1 if ("nation" in av and not a.demo) else 0
    r["ms_nation"] = ""
    r["calls_local"] -= r["calls_nation"]
    v, r["calls_policy"], r["ms_policy"] = phase(
        lambda: tools.check_policy("tok_kimsj", isbn, tools.CFG["home_library"]))
    r["policy_allowed"] = v["allowed"]
    return r

def finish(r):
    r["calls_total"] = sum(r.get(k, 0) or 0 for k in ("calls_search", "calls_local", "calls_policy", "calls_nation"))
    r["ms_total"] = sum(r.get(k, 0) or 0 for k in ("ms_search", "ms_local", "ms_policy") if isinstance(r.get(k), int))
    return r

def write_sheet_a(rows):
    """실측 A 표본: 도서 × 소장관 행. 정보나루 값은 채워 두고 시스템 값은 손으로 적는다(결과만)."""
    picked = []
    for r in rows:
        if not r.get("isbn_found"): continue
        h = naru.holdings_local(r["isbn_found"], tools.CFG["libraries"], tools.CFG["region_code"],
                               mode=tools.MODE)   # 캐시에서 온다(추가 호출 없음)
        for lib, st in h.items():
            if st == "none": continue
            picked.append({"번호": len(picked) + 1, "도서명": r["title"], "ISBN13": r["isbn_found"], "분관": lib,
                           "정보나루_조회일": today, "정보나루_소장": "Y",
                           "정보나루_대출가능(전일)": "Y" if st == "ok" else "N",
                           "시스템_확인일시": "", "시스템_소장": "", "시스템_대출가능": "",
                           "소장_일치": "", "대출_일치": "", "비고": ""})
            if len(picked) >= a.sheet_a_rows: break
        if len(picked) >= a.sheet_a_rows: break
    if not picked: return 0
    with open(sheet_a, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(picked[0].keys())); w.writeheader(); w.writerows(picked)
    return len(picked)

def summary(rows):
    def col(k): return [r[k] for r in rows if isinstance(r.get(k), (int, float)) and r.get(k) != ""]
    n = len(rows)
    found = sum(1 for r in rows if r.get("found")); local_hit = sum(1 for r in rows if (r.get("ok") or 0) > 0)
    nation = sum(1 for r in rows if r.get("nation_found") not in ("", None))
    em = [r for r in rows if r.get("edition_match") != ""]; em_ok = sum(1 for r in em if r["edition_match"])
    fixed = sum(1 for r in rows if r.get("edition_fixed"))
    calls, ms = col("calls_total"), col("ms_total")
    api_ms = [c["ms"] for c in naru.CALLS]
    lines = [f"# 실측 요약 — {today}{tag}", "",
             f"- 설정: `{Path(a.config).name}` ({tools.CFG['city']}, 관내 {len(tools.CFG['libraries'])}개관) · 모드 {tools.MODE}",
             f"- 도서 {n}종 · 검색 성공 {found}/{n} · 검색 판본 = 목록 판본 {em_ok}/{len(em) or '-'} · 판본 보정 {fixed}건",
             f"- 관내 대출가능 소장 있음 {local_hit}/{n} · 전국 폴백 {nation}건",
             (f"- 도서 1종당 호출: 평균 {statistics.mean(calls):.1f}회 · 중앙값 {statistics.median(calls):.0f} · "
              f"최소 {min(calls)} · 최대 {max(calls)}  (검색 1 + 소장관 조회 1 + 소장관 수만큼 bookExist + 전국 0~1)") if calls else "- 호출 없음(demo)",
             (f"- 도서 1종당 소요: 평균 {statistics.mean(ms)/1000:.1f}초 · 최대 {max(ms)/1000:.1f}초 "
              f"(정보나루 응답 평균 {statistics.mean(api_ms):.0f}ms/호출, {len(api_ms)}회)") if api_ms else "- 소요 시간: 네트워크 없음(demo)",
             f"- 이번 실행 호출 합계 {len(naru.CALLS)}회 (하루 한도 500회 기준 {len(naru.CALLS)/5:.0f}%)", "",
             "| 도서 | 판본 | 소장관 | 대출가능 | 대출중 | 전국 | 호출 | 초 |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['title'][:24]} | {'일치' if r.get('edition_match') is True else ('보정' if r.get('edition_fixed') else ('-' if r.get('edition_match')=='' else '다름'))} "
                     f"| {r.get('holding_count','')} | {r.get('ok','')} | {r.get('busy','')} | {r.get('nation_found','')} "
                     f"| {r.get('calls_total','')} | {(r.get('ms_total') or 0)/1000:.1f} |")
    return "\n".join(lines) + "\n"

def main():
    titles = load_titles()
    done = done_keys()
    todo = [t for t in titles if t["title"] not in done]
    if a.limit: todo = todo[:a.limit]
    print(f"도서 {len(titles)}종 중 이미 잰 것 {len(done)}종 · 이번에 {len(todo)}종 · 호출 상한 {a.max_calls}회 · 모드 {tools.MODE}")
    rows = []
    new_file = not out_csv.exists()
    with open(out_csv, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file: w.writeheader()
        for i, row in enumerate(todo, len(done) + 1):
            if len(naru.CALLS) >= a.max_calls:
                print(f"호출 상한 도달({len(naru.CALLS)}회) — 남은 {len(todo)-len(rows)}종은 다음에 이어서(같은 명령)"); break
            try:
                r = finish(measure_one(i, row))
            except Exception as e:
                r = finish({"n": i, "title": row["title"], "isbn_csv": row.get("isbn13", ""), "note": f"오류: {e}"})
                print(f"  {i:>3} {row['title'][:20]:<22} 오류: {e}")
                if "일일" in str(e) or "한도" in str(e) or "인증" in str(e): rows.append(r); w.writerow(r); break
            rows.append(r); w.writerow(r); f.flush()
            print(f"  {i:>3} {row['title'][:20]:<22} 소장관 {r.get('holding_count','-'):>2} · 가능 {r.get('ok','-'):>2} "
                  f"· 호출 {r['calls_total']:>2} · {r['ms_total']/1000:>4.1f}초 {r['note']}")
            time.sleep(a.sleep)
    # 요약은 파일 전체(이전 실행 포함)로
    with open(out_csv, encoding="utf-8-sig") as f:
        allrows = []
        for r in csv.DictReader(f):
            for k in ("holding_count", "ok", "busy", "none", "calls_search", "calls_local", "calls_policy",
                      "calls_nation", "calls_total", "ms_search", "ms_local", "ms_policy", "ms_total"):
                if r.get(k, "") != "": r[k] = int(float(r[k]))
            for k in ("found", "edition_fixed"): r[k] = (r.get(k) == "True")
            r["edition_match"] = True if r.get("edition_match") == "True" else (False if r.get("edition_match") == "False" else "")
            allrows.append(r)
    out_md.write_text(summary(allrows), encoding="utf-8")
    k = write_sheet_a(rows) if rows else 0
    print(f"\n결과: {out_csv.name} · 요약: {out_md.name}" + (f" · 기록지A {k}행: {sheet_a.name}" if k else ""))
    print(out_md.read_text(encoding="utf-8").split("\n\n")[0])

if __name__ == "__main__":
    main()
