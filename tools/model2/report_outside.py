#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 몫 다시 재기(시연 도서 밖 15권 · 문의 20건) 기록표.

11. 2. 독립 심사 지적에 따라 보고를 둘로 나눈다.
  가. 모델이 한 일: 이용자의 말을 맞는 책으로 바꿔 넘겼나, 한국어판 제목으로 바꿔 넘겼나, 세 번 모두 맞았나,
      판정 한 줄(도구가 준 verdict)을 답에 그대로 옮겼나, 안내문 사실(조회일·누리집 주소·도서관·관 수)을 옮겼나,
      모호한 말에 되물었나, 외국어 문의에 그 언어로 답했나.
  나. 도구가 한 일: 같은 책을 넘기면 판정(갈래·판정 한 줄)은 도구가 정하므로 모델이 달라도 같다(받아 둔 같은 자료로 판정).
      이것은 모델의 능력이 아니라 도구의 성질이라 따로 적는다.
실행: python3 report_outside.py <결과 json 폴더> <기록을 쓸 폴더> [실행 주소]"""
import json, sys, pathlib, collections, datetime

KST = datetime.timezone(datetime.timedelta(hours=9))
src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
run_url = sys.argv[3] if len(sys.argv) > 3 else ""
docs = []
for p in sorted(src.glob("ai_metrics_run*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    if d.get("caseset") == "outside20" and d.get("rows"):
        docs.append(d)
refs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(src.glob("ai_metrics_ref_*_outside20.json"))]
if not docs:
    sys.exit("outside20 결과가 없습니다")
NAME = {"gpt-oss:20b": "GPT-OSS 20B", "exaone3.5:2.4b": "엑사원 3.5 2.4B", "solar-pro4": "Solar Pro 4"}
by_model = collections.defaultdict(list)
for d in docs:
    by_model[d["model"]].append(d)


def frac(rows, key, cond=lambda r: True):
    xs = [r.get(key) for r in rows if cond(r) and r.get(key) is not None]
    return f"{sum(1 for x in xs if x)}/{len(xs)}" if xs else "-"


L = [f"# AI가 맡는 몫 다시 재기: 시연 도서 밖 15권 · 문의 20건({datetime.datetime.now(KST).strftime('%Y. %-m. %-d.')})", "",
     "문의 목록은 실측 전에 커밋해 두고 바꾸지 않았다(tools/model2/run_ai_metrics.py `CASES_OUTSIDE`). 시연 도서 5종과 그 찾기 낱말, "
     "직원 측정(기록지 B)의 책은 넣지 않았다. 정보나루 자료는 책마다 한 번 받아 두고 모든 모델·회차가 같은 자료로 판정했다"
     "(tools/model2/replay_relay.py, 받은 날의 전일 기준). 채점은 기계로 했고 실패도 그대로 적는다.", ""]
if run_url:
    L += [f"- 실행: {run_url}"]
for r in refs:
    rp = r.get("replay") or {}
    L += [f"- 기준(모델 없이 정확한 제목으로 도구 한 번) 받은 날 {r.get('finished')} · 저장소 main {r.get('commit')} · "
          f"정보나루 호출 {rp.get('live_calls', '?')}회"]
L += ["", "## 가. 모델이 한 일", "",
      "| 모델 | 회차 | 맞는 책을 넘김 | 한국어판 제목으로 바꿔 넘김(묘사·외국어) | 세 번 모두 맞는 책(문의 수) | 판정 한 줄 그대로 | 안내문 사실 모두 | 되물음(모호) | 그 언어로 답 | 확인 불가 |",
      "|---|---|---|---|---|---|---|---|---|---|"]
for m, ds in sorted(by_model.items(), key=lambda kv: NAME.get(kv[0], kv[0])):
    rows = [r for d in ds for r in d["rows"]]
    per_q = collections.defaultdict(list)
    for d in ds:
        for r in d["rows"]:
            if r.get("book_ok") is not None:
                per_q[r["no"]].append(bool(r["book_ok"]))
    all3 = sum(1 for v in per_q.values() if len(v) >= 3 and all(v))
    L.append(f"| {NAME.get(m, m)} | {len(ds)} | {frac(rows, 'book_ok')} | "
             f"{frac(rows, 'title_arg_ok', lambda r: r.get('cat') in ('묘사', '외국어'))} | {all3}/{len(per_q)} | "
             f"{frac(rows, 'verdict_ok')} | "
             f"{sum(1 for r in rows if (r.get('facts') or {}).get('all'))}/{sum(1 for r in rows if (r.get('facts') or {}).get('all') is not None)} | "
             f"{frac(rows, 'asked')} | {frac(rows, 'lang_ok', lambda r: r.get('lang') != 'ko')} | "
             f"{sum(1 for r in rows if r.get('infra'))} |")
L += ["", "- 맞는 책: 도구가 받은 책의 본서명이 기대한 책과 같음(판본·권은 따지지 않음). 확인 불가는 정보나루 예산·연결 때문에 소장을 못 본 건(모델 탓 아님, 따로 셈).",
      "- 판정 한 줄 그대로: 도구가 준 판정 한 줄(verdict, 11. 4.~)이 답에 글자 그대로 있음. 확인 불가·미확정 건은 세지 않음.", "",
      "## 나. 도구가 한 일(모델 능력이 아님)", ""]
same = tot = 0
for d in docs:
    ref = d.get("ref") or {}
    for r in d["rows"]:
        if r.get("book_ok") and str(r["no"]) in ref and r.get("tool_verdict"):
            tot += 1
            same += r["tool_verdict"] == ref[str(r["no"])].get("verdict")
L += [f"- 맞는 책을 넘긴 {tot}번 가운데 판정 한 줄이 기준과 같은 것 {same}번. 판정은 규칙 도구가 정하고 모두 같은 자료로 판정했으므로, "
      "이 숫자는 모델이 판정을 잘해서가 아니라 판정이 도구에 있다는 뜻이다.", ""]
L += ["## 다. 문의별(세 회차 · 맞는 책 ○, 다른 책 ×, 못 찾음·되물음 -, 확인 불가 !)", "",
      "| 번호 | 갈래 | 이용자의 말 | 기대한 책 | " + " | ".join(NAME.get(m, m) for m in sorted(by_model, key=lambda k: NAME.get(k, k))) + " |",
      "|---|---|---|---|" + "---|" * len(by_model)]
cases = {}
for d in docs:
    for r in d["rows"]:
        cases.setdefault(r["no"], r)
for no in sorted(cases):
    c = cases[no]
    cells = []
    for m in sorted(by_model, key=lambda k: NAME.get(k, k)):
        marks = []
        for d in sorted(by_model[m], key=lambda x: x.get("rep", 0)):
            r = next((x for x in d["rows"] if x["no"] == no), None)
            if not r: marks.append("?"); continue
            if r.get("infra"): marks.append("!")
            elif r.get("book_ok"): marks.append("○")
            elif r.get("wrong_book"): marks.append("×")
            elif c.get("expect") is None: marks.append("○" if r.get("asked") else "×")
            else: marks.append("-")
        cells.append("".join(marks))
    ask = c["ask"].replace("|", "/")
    L.append(f"| {no} | {c['cat']} | {ask[:60]}{'…' if len(ask) > 60 else ''} | {c.get('expect') or '(되물어야 함)'} | " + " | ".join(cells) + " |")
used = [d.get("replay") or {} for d in docs]
L += ["", f"정보나루 호출: 기준 받기 {sum((r.get('replay') or {}).get('live_calls', 0) for r in refs)}회 + 모델 작업 {sum(u.get('live_calls', 0) for u in used)}회"
      f"(받아 둔 자료에 없던 검색어·판본만), 예산을 넘어 확인 불가로 답한 요청 {sum(u.get('over', 0) for u in used)}건.", ""]
out = dst / f"ai_outside_record_{datetime.datetime.now(KST).strftime('%Y-%m-%d_%H%M')}.md"
out.write_text("\n".join(L) + "\n", encoding="utf-8")
print(out)
print("\n".join(L[:40]))
