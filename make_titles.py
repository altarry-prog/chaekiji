#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[2주차] 측정용 도서 목록 만들기 — 정보나루 인기대출도서(loanItemSrch)에서 실제 서지를 받아 CSV로 저장.
지어낸 도서가 아니라 최근 6개월 실제 대출 상위 도서라서, 관내 소장이 있는 책(관내 판정 경로)과
다른 지역 상위 도서(관내 없음 → 전국 폴백 경로)를 섞을 수 있다.

실행 예:
  python3 lab/make_titles.py --n 24 --dtl-region 31050                 # 부천 상위 24권
  python3 lab/make_titles.py --n 24 --dtl-region 31050 --extra-region 39 --extra-n 8   # + 제주 상위 8권
쓰는 호출: 1회(+ extra 1회)
결과: lab/out/titles.csv (열: source, rank, title, author, publisher, year, isbn13, loan_count)"""
import os, sys, csv, argparse, datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from connectors import naru

def fetch(n, months, region=None, dtl_region=None):
    start = (datetime.date.today() - datetime.timedelta(days=30 * months)).isoformat()
    params = {"startDt": start, "pageSize": n}
    if dtl_region: params["dtl_region"] = dtl_region
    elif region: params["region"] = region
    resp = naru._get("loanItemSrch", **params)
    docs = [d.get("doc", d) for d in resp.get("docs", [])]
    return [{"rank": d.get("ranking"), "title": d.get("bookname"), "author": d.get("authors"),
             "publisher": d.get("publisher"), "year": d.get("publication_year"),
             "isbn13": d.get("isbn13"), "loan_count": d.get("loan_count")} for d in docs if d.get("isbn13")]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=24, help="주 지역 상위 권수")
    ap.add_argument("--months", type=int, default=6, help="대출 집계 기간(개월)")
    ap.add_argument("--dtl-region", default="31050", help="세부지역 코드(부천 31050)")
    ap.add_argument("--extra-region", default=None, help="추가 지역 코드(예: 제주 39) — 관내 미소장 사례용")
    ap.add_argument("--extra-n", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT/"lab"/"out"/"titles.csv"))
    a = ap.parse_args()
    if not os.environ.get("NARU_KEY"):
        sys.exit("NARU_KEY가 없습니다:  read -s NARU_KEY; export NARU_KEY")
    rows = [dict(source=f"dtl_region {a.dtl_region}", **r) for r in fetch(a.n, a.months, dtl_region=a.dtl_region)]
    if a.extra_region and a.extra_n:
        seen = {r["isbn13"] for r in rows}
        rows += [dict(source=f"region {a.extra_region}", **r)
                 for r in fetch(a.extra_n, a.months, region=a.extra_region) if r["isbn13"] not in seen]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["source", "rank", "title", "author", "publisher", "year", "isbn13", "loan_count"])
        w.writeheader(); w.writerows(rows)
    s = naru.calls_summary()
    print(f"{len(rows)}권 → {a.out}  (호출 {s['total']}회)")
    for r in rows[:5]: print(f"  {r['rank']:>3} {r['title']} / {r['author']} / {r['isbn13']}")
    if len(rows) > 5: print("  …")

if __name__ == "__main__":
    main()
