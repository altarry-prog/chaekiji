#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""전국 공공도서관 상호대차 실적(국가도서관통계시스템 공개 API, 키 없음)을 연도별로 합산한다.

담당자 11. 3. 10:35 「25년 실적을 넣었는데 전국 도서관 상호대차 수치는 안 나와?」. 신청서의 전국 값은 2024년(기사 인용, 원자료 대조 전)이라
원자료(통계시스템 API)로 2024·2025년을 직접 합산해 대조한다. 작업 공간에서는 mcst.go.kr이 막혀 깃허브 액션에서 돈다.
API: https://mcst.go.kr/libsta/nlstatapi/api/v1/stat?year=…&libGubun=…&page=…&size=100 (매뉴얼: 프로젝트 문서 「통계시스템 API_매뉴얼」)
출력: server/lab/out/libstat_ill_<연도>.json(상호대차가 들어간 항목의 합계·도서관 수·0건 도서관 수, 부천 도서관 값) · libstat_ill.md(요약)
정보나루를 부르지 않는다. 개인정보 없음."""
import json, sys, time, urllib.parse, urllib.request, pathlib, collections, datetime

BASE = "https://mcst.go.kr/libsta/nlstatapi/api/v1"
GUBUN = {"공공": "LIBTYPE000002001", "어린이": "LIBTYPE000002002", "장애인": "LIBTYPE000002004"}
OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "server/lab/out")
YEARS = [int(y) for y in (sys.argv[2].split(",") if len(sys.argv) > 2 else ["2024", "2025"])]
UA = {"User-Agent": "chaekiji-libstat/1 (github actions)", "Accept": "application/json"}


def get(path, **q):
    url = f"{BASE}/{path}?" + urllib.parse.urlencode(q)
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            err = e; time.sleep(3 * (i + 1))
    raise SystemExit(f"API 실패: {url} · {type(err).__name__}: {err}")


def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None


def walk(o, path=()):
    """list 항목 안의 모든 (경로, 값)을 꺼낸다(응답 모양이 정해져 있지 않아도 상호대차 키를 찾을 수 있게)."""
    if isinstance(o, dict):
        for k, v in o.items():
            yield from walk(v, path + (str(k),))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, path + (str(i),))
    else:
        yield path, o


OUT.mkdir(parents=True, exist_ok=True)
summary = {"made": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M"), "years": {}}
for year in YEARS:
    ymap = {}
    for gname, gcode in GUBUN.items():
        try:
            ymap[gname] = get("stat/mapinfo", libGubun=gcode, year=str(year))
        except SystemExit as e:
            ymap[gname] = {"error": str(e)}
    keys_ill = sorted({"/".join(p) for g in ymap.values() for p, v in walk(g) if "상호대차" in "/".join(p) or "상호대차" in str(v)})
    per = {}
    for gname, gcode in GUBUN.items():
        first = get("stat", year=str(year), libGubun=gcode, page="1", size="100")
        cnt = int(first.get("count") or 0)
        pages = max(1, -(-cnt // 100))
        recs = list(first.get("list") or [])
        for p in range(2, pages + 1):
            recs += list(get("stat", year=str(year), libGubun=gcode, page=str(p), size="100").get("list") or [])
            time.sleep(0.3)
        sums, libs_pos, libs_zero, libs_with = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
        bucheon = []
        for rec in recs:
            vals = {"/".join(pth[-2:]): v for pth, v in walk(rec) if any("상호대차" in x for x in pth)}
            for k, v in vals.items():
                n = num(v)
                if n is None:
                    continue
                sums[k] += n; libs_with[k] += 1
                (libs_pos if n > 0 else libs_zero)[k] += 1
            txt = json.dumps(rec, ensure_ascii=False)
            if "부천" in txt:
                bucheon.append({"name": next((v for pth, v in walk(rec) if pth[-1] in ("libName", "도서관명")), None), "ill": vals})
        per[gname] = {"count": cnt, "records": len(recs), "sums": dict(sums), "libs_with_value": dict(libs_with),
                      "libs_positive": dict(libs_pos), "libs_zero": dict(libs_zero), "bucheon": bucheon,
                      "sample_record": recs[0] if recs else None}
        print(year, gname, "도서관", cnt, "받은 기록", len(recs), "상호대차 항목", len(sums), flush=True)
    summary["years"][str(year)] = {"mapinfo_ill_keys": keys_ill, "by_gubun": per}
    (OUT / f"libstat_ill_{year}.json").write_text(json.dumps(summary["years"][str(year)], ensure_ascii=False, indent=1), encoding="utf-8")

L = ["# 전국 공공도서관 상호대차 실적: 국가도서관통계시스템 공개 API 합산", "",
     f"- 만든 때 {summary['made']} · 출처 {BASE}/stat (키 없음, 매뉴얼은 프로젝트 문서) · 정보나루 호출 없음", ""]
for y, d in summary["years"].items():
    L += [f"## {y}년", ""]
    for g, p in d["by_gubun"].items():
        L += [f"### {g}(도서관 {p['count']}곳, 받은 기록 {p['records']}건)", ""]
        if not p["sums"]:
            L += ["- 상호대차가 들어간 항목을 찾지 못함(첫 기록의 모양은 json 파일 sample_record)", ""]
            continue
        L += ["| 항목 | 합계 | 값이 있는 도서관 | 0보다 큰 도서관 | 0인 도서관 |", "|---|---|---|---|---|"]
        for k in sorted(p["sums"]):
            L.append(f"| {k} | {p['sums'][k]:,.0f} | {p['libs_with_value'].get(k, 0)} | {p['libs_positive'].get(k, 0)} | {p['libs_zero'].get(k, 0)} |")
        if p["bucheon"]:
            L += ["", f"- 부천이 들어간 기록 {len(p['bucheon'])}건(대조용): " + "; ".join(
                f"{b['name']} " + ", ".join(f"{k}={v}" for k, v in b["ill"].items()) for b in p["bucheon"][:20])]
        L.append("")
(OUT / "libstat_ill.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L[:80]))
