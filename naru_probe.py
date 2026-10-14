#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[1주차] 정보나루 첫 실호출 점검 — 키가 살아 있는지, exactMatch 값이 무엇인지, 호출이 몇 번 드는지.
실행:  read -s NARU_KEY; export NARU_KEY        (키는 화면에 보이지 않고, 파일에도 남지 않는다)
       python3 lab/naru_probe.py
쓰는 호출: 최대 5회 (하루 한도 500회 중)
키 원문은 어디에도 출력·기록하지 않는다."""
import os, sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from connectors import naru

TITLE, ISBN, LIB, LIBCODE = "나미야 잡화점의 기적", "9788972756194", "상동", "141321"

def main():
    if not os.environ.get("NARU_KEY"):
        import getpass
        os.environ["NARU_KEY"] = getpass.getpass("정보나루 인증키(화면에 안 보임): ").strip()
    k = os.environ["NARU_KEY"]
    print(f"키 길이 {len(k)}자 · 앞 2자 {k[:2]}… (원문은 출력하지 않음)")

    # 1) exactMatch 값 비교 — 매뉴얼은 true/false, 8월 실측 코드는 Y
    print(f"\n[1] srchBooks title=「{TITLE}」 — exactMatch 값별 결과")
    verdict = {}
    for v in ("true", "Y", "false"):
        try:
            resp = naru._get("srchBooks", title=TITLE, exactMatch=v, pageSize=5)
            docs = [d.get("doc", d) for d in resp.get("docs", [])]
            n = resp.get("numFound", len(docs))
            first = docs[0]["bookname"] if docs else "(없음)"
            exact = sum(1 for d in docs if "".join(d["bookname"].split()) == "".join(TITLE.split()))
            verdict[v] = (n, exact, len(docs))
            print(f"   exactMatch={v:<5} → 전체 {n}건, 받은 {len(docs)}건 중 제목 완전일치 {exact}건, 첫 결과 「{first}」")
        except Exception as e:
            print(f"   exactMatch={v:<5} → 오류: {e}")
            if "일일" in str(e) or "한도" in str(e): sys.exit(1)
    best = None
    for v in ("true", "Y"):
        if v in verdict and verdict[v][2] and verdict[v][1] == verdict[v][2]:
            best = v; break
    if best:
        print(f"   → 권장: NARU_EXACT={best}  (받은 결과가 전부 완전일치)")
        print(f"     매번 입력하지 않으려면:  export NARU_EXACT={best}")
    else:
        print("   → 어느 값도 완전일치만 주지 않음 — 결과를 prompts/ 기록에 적고, 판본 후보(candidates)로 보정하는 흐름 유지")

    # 2) bookExist — 소장·대출 가능(전일 기준)
    print(f"\n[2] bookExist {LIB}({LIBCODE}) × ISBN {ISBN}")
    r = naru._get("bookExist", libCode=LIBCODE, isbn13=ISBN).get("result", {})
    print(f"   hasBook={r.get('hasBook')} loanAvailable={r.get('loanAvailable')}  (대출 가능 여부는 조회일 전일 기준)")

    # 3) libSrchByBook — 부천(31050) 소장 도서관 수
    print(f"\n[3] libSrchByBook region=31 dtl_region=31050 × ISBN {ISBN}")
    resp = naru._get("libSrchByBook", isbn=ISBN, region="31", dtl_region="31050", pageSize=300)
    libs = [l.get("lib", l) for l in resp.get("libs", [])]
    print(f"   부천 지역 소장관 {len(libs)}곳 (작은도서관 포함) — 예: " +
          ", ".join(x.get("libName", "?") for x in libs[:5]) + (" …" if len(libs) > 5 else ""))

    s = naru.calls_summary()
    print(f"\n호출 {s['total']}회 · {s['by_api']} · 합계 {s['ms_total']}ms")
    print("이 출력에서 숫자만 prompts/ 기록에 옮겨 적으세요. 키는 적지 않습니다.")

if __name__ == "__main__":
    main()
