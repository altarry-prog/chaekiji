#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[3주차] 다른 도시 설정 파일 초안 만들기 — 정보나루 libSrch(도서관 조회)로 그 지역 공공도서관 코드표를 받아
config/<도시>.yaml 을 쓴다. 규정 숫자는 부천 값을 자리표시로 넣고 【확인】 표시를 남긴다(그 도시 누리집 규정으로 교체).
"확산 = 설정 파일 한 장" 주장을 실제 도시 코드표로 확인하는 데 쓴다.

실행 예:
  python3 lab/make_city_config.py --dtl-region 11050 --city 광진 --home 광진정보도서관
  python3 lab/make_city_config.py --dtl-region 33040 --city 청주 --exclude 작은,어린이,학교,새마을,병영
세부지역 코드는 정보나루 Open API 매뉴얼 코드표(63쪽~)에서: 광진구 11050 · 강남구 11230 · 청주시 33040 · 용인시 31190 · 부천시 31050
쓰는 호출: 1회"""
import os, sys, argparse, datetime, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from connectors import naru

def _rel(p):
    """[10/31] --out이 서버 폴더 밖이어도 안내 줄에서 멈추지 않게(시흥·광명 실측 첫 실행에서 발견)."""
    try:
        return p.resolve().relative_to(ROOT)
    except ValueError:
        return p

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dtl-region", required=True, help="정보나루 세부지역 코드(예: 11050)")
    ap.add_argument("--city", required=True, help="설정 파일 이름·city 값(예: 광진)")
    ap.add_argument("--home", default=None, help="자주 가는 도서관(기본: 목록 첫 관)")
    ap.add_argument("--include", default="도서관", help="이 낱말이 든 이름만(쉼표 구분)")
    ap.add_argument("--exclude", default="작은,어린이,학교,새마을,병영,점자,대학,교육청", help="이 낱말이 든 이름 제외(쉼표 구분)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if not os.environ.get("NARU_KEY"):
        sys.exit("NARU_KEY가 없습니다:  read -s NARU_KEY; export NARU_KEY")
    resp = naru._get("libSrch", region=a.dtl_region[:2], dtl_region=a.dtl_region, pageSize=300)
    libs = [l.get("lib", l) for l in resp.get("libs", [])]
    inc = [w for w in a.include.split(",") if w]; exc = [w for w in a.exclude.split(",") if w]
    keep = [l for l in libs if any(w in l.get("libName", "") for w in inc)
            and not any(w in l.get("libName", "") for w in exc)]
    if not keep:
        sys.exit(f"세부지역 {a.dtl_region}: 도서관 {len(libs)}곳 중 조건에 맞는 곳이 없습니다 — --include/--exclude 조정")
    def short(name):
        # [10/31] 안내문이 「{이름}도서관」으로 부르므로 「시흥시중앙도서관」 → 「중앙」처럼 시 이름 접두·「도서관」 접미를 뗀다
        #         (시흥·광명 실측에서 그대로 두면 「시흥시중앙도서관도서관」이 됨을 확인)
        n = re.sub(r"\s+", "", name)
        for pre in (a.city + "시립", a.city + "시"):
            if n.startswith(pre) and len(n) > len(pre):
                n = n[len(pre):]; break
        if n.endswith("도서관") and len(n) > 3:
            n = n[:-3]
        return n
    names = {}
    for l in keep:
        n = short(l["libName"]); base = n; k = 2
        while n in names: n = f"{base}{k}"; k += 1
        names[n] = str(l["libCode"])
    home = a.home or next(iter(names))
    if home not in names:
        cand = [n for n in names if home in n]
        if cand: home = cand[0]
        else: sys.exit(f"--home '{home}' 이 목록에 없습니다: {', '.join(names)}")
    out = Path(a.out) if a.out else ROOT/"config"/f"{a.city}.yaml"
    today = datetime.date.today().isoformat()
    y = [f"# 책이지 MCP — {a.city} 설정 초안 ({today}, lab/make_city_config.py 생성)",
         f"# 도서관 코드표: 정보나루 libSrch(dtl_region={a.dtl_region}) {len(libs)}곳 중 {len(names)}곳 채택(조건: 포함 {inc} / 제외 {exc})",
         "# 【확인】 표시 값은 부천 값을 자리표시로 넣은 것 — 이 도시 누리집 상호대차 규정으로 교체할 것",
         f"city: {a.city}", f'region_code: "{a.dtl_region}"', f"home_library: {home}", "libraries:"]
    y += [f'  {n}: "{c}"' for n, c in names.items()]
    y += ["rules:", "  ill_limit: 5                # 【확인】 상호대차 1인 한도", "  total_limit: 20             # 【확인】 통합 대출 한도",
          "  per_lib_limit: 5            # 【확인】 도서관별 한도", "  block_if_pickup_on_shelf: true   # 【확인】",
          "  block_if_overdue: true", "  excluded_types: [부록]       # 【확인】", "  exclude_new_arrival: false  # 【확인】",
          'ill_eta_days: "1"             # 【확인】 평일 기준 소요일',
          'ill_eta_text: ""              # 【확인】 안내문 문장(예: 「월~목요일 신청은 다음 날, 금·토요일 신청은 월·화요일에」) — 비우면 「○일 안에」',
          "hold_days: 3                  # 【확인】 도착 후 보관 기한(일)", "hold_includes_arrival_day: true   # 【확인】 도착일 포함 여부",
          "no_pickup_block_days: 7       # 【확인】 미수령(자동반납) 시 신청 제한 일수 — 0이면 안내 안 함",
          "reserve_converts_to_ill: true # 【확인】 예약 도서 반납 시 상호대차 전환 신청 가능 여부",
          "pass:", "  max_per_cycle: 3", "  free_routes_only: true",
          f"sso: 【확인】.go.kr", "notify_channels: [sms]"]
    out.write_text("\n".join(y) + "\n", encoding="utf-8")
    print(f"{out} — 도서관 {len(names)}곳 (지역 전체 {len(libs)}곳), home_library={home}")
    for n, c in names.items(): print(f"  {n}: {c}")
    print("다음: 이 파일의 【확인】 값을 그 도시 누리집 규정으로 바꾼 뒤\n"
          f"      python3 lab/measure.py --config {_rel(out)} --titles lab/out/titles.csv --limit 5 --tag {a.city}")

if __name__ == "__main__":
    main()
