#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""다른 도시 실측: 책이지 코드는 그대로 두고 설정 파일만 바꿔 시흥·광명의 공공도서관으로 판정이 도는지 잰다.

순서(도시마다)
  ① main의 lab/make_city_config.py로 정보나루 libSrch(세부지역) 1회 → 그 도시 공공도서관 코드표로 설정 초안
  ② 이름 줄이기(「시흥시」·「광명시」 접두와 「도서관」 접미를 뗀다)와 확인한 규정 값만 덮어쓴다(나머지는 【확인】 그대로)
  ③ 같은 server/tools.py를 live 모드·관내 출처 정보나루로 불러 책 5권을 판정(consult_request)한다
기록은 실제로 돌린 결과만 담는다. 정보나루 인증키는 깃허브 비밀값(NARU_KEY)으로만 받고 어디에도 적지 않는다.
대출 상태는 정보나루 전일 기준이고, 어떤 판정도 접수로 이어지지 않는다(이 도구는 접수하지 않음)."""
import os, sys, re, json, time, datetime, pathlib, subprocess

KST = datetime.timezone(datetime.timedelta(hours=9))
WORK = pathlib.Path(os.environ.get("WORK_DIR", "/content"))
STAMP = datetime.datetime.now(KST).strftime("%Y-%m-%d_%H%M")

# 도시: (이름, 정보나루 세부지역 코드, 받을 도서관 이름에 들어갈 낱말)
CITIES = [("시흥", "31150", "중앙"), ("광명", "31060", "하안")]
ASKS = ["소년이 온다", "불편한 편의점", "나미야 잡화점의 기적", "채식주의자", "지구 끝의 온실"]

# 확인한 규정 값만 덮어쓴다. 근거가 기사·이용안내 자료라 누리집에서 다시 확인할 값이다(기록에 그대로 적는다).
CONFIRMED = {
    "시흥": {"per_lib_limit": (10, "시흥시 도서관 이용안내 자료(lib.siheung.go.kr 게시 PDF) 「1인당, 도서관별 10권」"),
             "total_limit": (30, "같은 자료 「전체도서관 30권」")},
    "광명": {"hold_days": (3, "광명시 공식 블로그(2023. 3.) 「도서 수령 문자를 받고 3일 이내에 대출」"),
             "total_limit": (7, "기호일보 기사 「기존 대출 권수인 7권」(시점 확인 필요)")},
}

if not os.environ.get("NARU_KEY"):
    sys.exit("NARU_KEY 비밀값이 없어 멈춥니다(Settings → Secrets → NARU_KEY)")

WORK.mkdir(parents=True, exist_ok=True)
os.chdir(WORK)
if not (WORK / "chaekiji").exists():
    subprocess.run(["git", "clone", "--depth", "1", "https://github.com/altarry-prog/chaekiji.git"], check=True)
SRV = WORK / "chaekiji" / "server"
os.chdir(SRV)
subprocess.run([sys.executable, "-m", "pip", "-q", "install", "pyyaml"], check=True)
import yaml  # noqa: E402
COMMIT = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
OUT = SRV / "lab" / "out"; OUT.mkdir(parents=True, exist_ok=True)
print("저장소 main", COMMIT, flush=True)

CHILD = r'''
import os, sys, json, time
sys.path.insert(0, ".")
import tools
from connectors import naru
pickup = os.environ["CITY_PICKUP"]
rows = []
for ask in json.loads(os.environ["CITY_ASKS"]):
    naru.calls_reset(); t0 = time.perf_counter()
    try:
        r = tools.consult_request(ask, pickup=pickup, lang="ko"); err = None
    except Exception as e:
        r, err = {}, f"{type(e).__name__}: {e}"
    ms = round((time.perf_counter() - t0) * 1000)
    av = {}
    try:
        if r.get("book") and r["book"].get("isbn13"):
            av = tools.check_availability(r["book"]["isbn13"])   # 같은 책을 다시 물으면 10분 캐시(호출 0)
    except Exception as e:
        av = {"error": str(e)}
    cs = naru.calls_summary()
    ra = r.get("availability") or {}
    rows.append({"ask": ask, "error": err, "ms": ms, "calls": cs,
                 "found": r.get("found"), "route": r.get("route"), "route_label": r.get("route_label"),
                 "book": r.get("book"), "from_lib": r.get("from_lib"),
                 "available_at": ra.get("available_at", av.get("available_at")), "loaned_at": ra.get("loaned_at", av.get("loaned_at")),
                 "holding_count": av.get("holding_count"), "basis": ra.get("basis") or av.get("basis"), "asof": ra.get("asof"),
                 "official_link": r.get("official_link"),
                 "notice": r.get("notice"), "desk_memo": r.get("desk_memo"), "reason": r.get("reason")})
print("@@JSON@@" + json.dumps(rows, ensure_ascii=False))
'''

def short_name(name, city):
    s = re.sub(r"\s+", "", name)
    for pre in (city + "시립", city + "시"):
        if s.startswith(pre) and len(s) > len(pre):
            s = s[len(pre):]; break
    if s.endswith("도서관") and len(s) > 3:
        s = s[:-3]
    return s

RESULTS = {}
for city, region, hint in CITIES:
    raw = WORK / f"cfg_{city}_raw.yaml"
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, "lab/make_city_config.py", "--dtl-region", region, "--city", city, "--out", str(raw)],
                       capture_output=True, text=True, env=dict(os.environ, PYTHONUTF8="1"))
    gen_log = (p.stdout + p.stderr).strip()
    print(f"━━ {city}({region}) 설정 초안\n{gen_log}", flush=True)
    if p.returncode != 0 or not raw.exists():
        RESULTS[city] = {"error": gen_log[-1500:], "region": region}
        continue
    cfg = yaml.safe_load(raw.read_text(encoding="utf-8"))
    libs_raw = dict(cfg["libraries"])
    libs = {}
    for n, c in libs_raw.items():
        s = short_name(n, city); k = s; i = 2
        while k in libs: k = f"{s}{i}"; i += 1
        libs[k] = str(c)
    home = next((n for n in libs if hint in n), next(iter(libs)))
    cfg["libraries"] = libs; cfg["home_library"] = home
    applied = []
    for k, (v, why) in CONFIRMED.get(city, {}).items():
        if k in cfg.get("rules", {}):
            cfg["rules"][k] = v
        else:
            cfg[k] = v
        applied.append((k, v, why))
    final = OUT / f"city_{city}_config_{STAMP}.yaml"
    head = [f"# 책이지 — {city} 설정(다른 도시 실측 {STAMP}, tools/city/run_city.py)",
            f"# 도서관 코드표: 정보나루 libSrch(dtl_region={region}) · lab/make_city_config.py 초안에서 이름만 줄임(「{city}시」 접두·「도서관」 접미)",
            "# 규정 값: 아래 「확인한 값」 말고는 부천 값을 자리표시로 둔 【확인】 — 그 도시 누리집 규정으로 바꿔야 운영에 쓸 수 있다"]
    for k, v, why in applied:
        head.append(f"# 확인한 값 {k}={v}: {why}")
    final.write_text("\n".join(head) + "\n" + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    env = dict(os.environ, PYTHONUTF8="1", CHAEKIJI_MODE="live", CHAEKIJI_LOCAL_SOURCE="naru",
               CHAEKIJI_CONFIG=str(final), CITY_PICKUP=home, CITY_ASKS=json.dumps(ASKS, ensure_ascii=False))
    env.pop("CHAEKIJI_RELAY", None)
    c = subprocess.run([sys.executable, "-c", CHILD], capture_output=True, text=True, env=env, timeout=1800)
    out = c.stdout
    rows = json.loads(out.split("@@JSON@@", 1)[1]) if "@@JSON@@" in out else []
    if not rows:
        print(c.stdout[-2000:], c.stderr[-2000:], flush=True)
    RESULTS[city] = {"region": region, "libs": libs, "libs_raw": libs_raw, "home": home, "applied": applied,
                     "rows": rows, "config": final.name, "gen_log": gen_log, "stderr": c.stderr[-1500:],
                     "sec": round(time.perf_counter() - t0, 1)}
    for r in rows:
        b = r.get("book") or {}
        print(f"  · {r['ask']} → {r.get('route_label')} · {b.get('title')} {b.get('isbn13')} · "
              f"대출 가능 {len(r.get('available_at') or [])}곳·대출 중 {len(r.get('loaned_at') or [])}곳 · "
              f"호출 {r['calls'].get('total')}회 · {r['ms']} ms {('· 오류 ' + r['error']) if r.get('error') else ''}", flush=True)

# 기록표
now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
bcfg = yaml.safe_load(open("config/bucheon.yaml", encoding="utf-8"))
L = [f"# 다른 도시 실측: 시흥·광명 — 설정 파일만 바꿔 판정 ({now} KST)", "",
     "- 무엇을 보았나: 책이지 코드(`server/tools.py`·`connectors/naru.py`)는 그대로 두고 **설정 파일만 바꿔** 다른 도시 공공도서관의 소장·대출로 판정이 도는지",
     f"- 실행: GitHub Actions(사람 손 없음) · 저장소 main 커밋 `{COMMIT}` · 실행 기록 {os.environ.get('RUN_URL', '—')}",
     "- 자료: 정보나루 Open API 실호출(live 모드, 관내 출처 정보나루) · 대출 상태는 **조회일 전일 기준** · 인증키는 깃허브 비밀값으로만",
     "- 설정 만들기: `lab/make_city_config.py`(정보나루 libSrch 1회) → 이름 줄이기 → 확인한 규정 값만 덮어쓰기. 나머지 규정은 부천 값을 자리표시로 둔 【확인】",
     "- 판정은 회원 정보 없이(손님 모드) 했다. 회원 한도·연체는 창구 확인으로 남고, 어떤 판정도 접수로 이어지지 않았다", ""]
for city, region, hint in CITIES:
    R = RESULTS.get(city, {})
    L += [f"## {city}(정보나루 세부지역 {region})", ""]
    if R.get("error"):
        L += ["설정 초안을 만들지 못했다(실패 그대로 적음):", "", "```", R["error"], "```", ""]
        continue
    rows = R["rows"]
    tot_calls = sum((r.get("calls") or {}).get("total", 0) for r in rows)
    L += [f"- 도서관 {len(R['libs'])}곳(코드표 채택) · 받을 도서관(기본) **{R['home']}** · 설정 파일 `{R['config']}`",
          "- 도서관: " + " · ".join(f"{n}({c})" for n, c in R["libs"].items()),
          "- 부천 설정과 바뀐 줄: `city`·`region_code`·`home_library`·`libraries`(도서관 코드표) + 규정 값(확인한 것만, 나머지 【확인】)"]
    for k, v, why in R["applied"]:
        L.append(f"  - 확인한 값 `{k}: {v}` — {why}")
    L += [f"- 정보나루 호출: 판정 {len(rows)}건에 {tot_calls}회(설정 초안 1회 별도)", "",
          "| 문의 | 고른 책(ISBN) | 판정 | 대출 가능 관 | 대출 중 관 | 호출 | 시간 |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        b = r.get("book") or {}
        ok = r.get("available_at") or []; busy = r.get("loaned_at") or []
        bk = f"{b.get('title', '—')} ({b.get('isbn13', '—')})" if b else "—"
        L.append(f"| {r['ask']} | {bk} | {r.get('route_label') or ('오류: ' + str(r.get('error')))} | "
                 f"{len(ok)}곳 {('(' + ', '.join(ok[:4]) + (' 등' if len(ok) > 4 else '') + ')') if ok else ''} | "
                 f"{len(busy)}곳 | {(r.get('calls') or {}).get('total', 0)}회 | {r['ms'] / 1000:.1f}초 |")
    L.append("")
    for r in rows:
        L += [f"<details><summary>{r['ask']}: 안내문·접수 메모 원문</summary>", "",
              (r.get("notice") or r.get("reason") or "(없음)").replace("\n", "<br>"), "",
              "```", (r.get("desk_memo") or "").strip(), "```", "", "</details>", ""]
L += ["## 읽는 법과 한계", "",
      "- 같은 코드가 설정 파일만 바뀐 채 다른 도시 도서관의 소장·대출로 갈래(바로 이용·관내 상호대차·예약·책바다)를 정했다. 바뀐 것은 도서관 코드표와 규정 값뿐이다.",
      "- 규정 값은 대부분 【확인】(부천 값 자리표시)이다. 운영하려면 그 도시 사서가 누리집 규정으로 바꿔야 한다. 안내문의 도착·보관 문장도 그 값에 따른다.",
      "- 정보나루가 도서관을 「공공도서관」으로 등록한 곳만 들어간다. 작은도서관·학교도서관은 make_city_config의 기본 거르기로 뺐다.",
      "- 대출 상태는 정보나루 조회일 전일 기준이라 그 도시 누리집의 실시간 상태와 다를 수 있다.", "",
      "---", "이 기록은 실제로 돌린 결과이며 사람이 고치지 않았다. 실패도 그대로 적는다."]
REC = OUT / f"city_record_actions_{STAMP}.md"
REC.write_text("\n".join(L) + "\n", encoding="utf-8")
(OUT / f"city_raw_actions_{STAMP}.json").write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("\n".join(L[:60]))
print("기록:", REC)
