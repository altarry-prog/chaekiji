#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI가 맡는 몫 지표 기록표: run_ai_metrics.py 작업들(모델 × 지시문 × 회차)의 결과 JSON을 모아 한 장으로 만든다.
쓰는 법: python3 report_ai_metrics.py <결과 JSON이 있는 폴더> <기록표를 쓸 폴더>"""
import sys, json, glob, pathlib, datetime, collections

KST = datetime.timezone(datetime.timedelta(hours=9))
SRC = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
DST = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else ".")
RUN_URL = sys.argv[3] if len(sys.argv) > 3 else "—"
docs = [json.load(open(p, encoding="utf-8")) for p in sorted(glob.glob(str(SRC / "**" / "ai_metrics_run*.json"), recursive=True))]
if not docs:
    sys.exit("결과 JSON이 없습니다.")
RUN_ID = docs[0]["run_id"]
NAME = {"gpt-oss:20b": "GPT-OSS 20B", "exaone3.5:2.4b": "EXAONE 3.5 2.4B"}
VAR = {"main": "지금 지시문", "title": "고친 안", "title2": "고친 안 2(언어 유지)", "retry": "고친 안 3(못 찾으면 한국어판 제목으로 다시)", "title_lang": "고친 안 4(고친 안 + 번역 7항)"}
ORDER = sorted({(d["model"], d["variant"]) for d in docs}, key=lambda k: (k[0] != "gpt-oss:20b", k[1] != "main"))
by = collections.defaultdict(list)
for d in docs:
    by[(d["model"], d["variant"])].append(d)

def R(key):
    return [r for d in by[key] for r in d["rows"]]

def frac(rows, pred, cond=lambda r: True):
    rs = [r for r in rows if cond(r)]
    if not rs:
        return "—"
    return f"{sum(1 for r in rs if pred(r))}/{len(rs)}"

def pct(rows, pred, cond=lambda r: True):
    rs = [r for r in rows if cond(r)]
    if not rs:
        return ""
    return f" ({round(100 * sum(1 for r in rs if pred(r)) / len(rs))}%)"

def fact(r, k, tr=False):
    f = r.get("facts_tr" if tr else "facts") or {}
    return f.get(k)

clear = lambda r: r.get("expect") is not None
amb = lambda r: r.get("expect") is None
LINES = []
A = LINES.append
reps = sorted({d["rep"] for d in docs})
commits = sorted({d["commit"] for d in docs})
now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
A(f"# AI가 맡는 몫 지표 — 공개 모델 {len({k[0] for k in ORDER})}종 · 고정 문의 24건 × {len(reps)}회 ({now} KST)")
A("")
A("- 무엇을 재나: 이용자가 제목을 정확히 말하지 않거나 외국어로 물을 때 ① 모델이 말을 책으로 바꾸는지(책 식별) "
  "② 도구가 정한 판정을 그대로 두는지(갈래 일치) ③ 안내문에 도구가 준 사실을 옮기는지 ④ 모호한 말에 되묻는지.")
A("- 실행 환경: GitHub Actions(ubuntu-latest, 사람 손 없음) · " +
  f"CPU {docs[0]['env'].get('cpu')}코어 · GPU 없음 · 메모리 {docs[0]['env'].get('mem')}(전체·사용) · Ollama {docs[0]['env'].get('ollama')} · 인증키·결제 없음")
A(f"- 실행 기록(공개): {RUN_URL}")
smodes = sorted({d.get("server_mode", "auto") for d in docs})
A(f"- 책이지: 저장소 main 커밋 `{'`, `'.join(commits)}` · 서버 `server.py`(모드 {', '.join(smodes)}) · "
  "호스트 `server/hosts/ollama_host.py` · 모델에 보이는 도구는 `consult_request` 하나 · 문맥 8192")
if "snapshot" in smodes:
    A("- 서버 모드 snapshot: 시연 도서 5종의 그날 새벽 자료만 쓰고 정보나루를 부르지 않는다. 시연 도서 5종의 판정은 auto 모드와 같다. "
      "같은 날 13:44에 시작한 첫 실행이 시연 도서 밖 책을 정보나루로 조회하다 하루 호출 한도(500건)를 넘겨 취소하고, 정보나루를 부르지 않는 이 방식으로 다시 돌렸다. "
      "그래서 문의 24건의 기대한 책은 모두 시연 도서 5종이고, 모델이 다른 말을 넘기면 대개 「도서 미확정」으로 끝난다(다른 책으로 답하는 실패는 도구의 찾기 낱말에 걸린 경우만 생긴다).")
A("- 받을 도서관·이용자 언어: 창구가 정하는 값이라 호스트 인자로 주었다(지금까지의 실측과 같은 방식). 모델이 할 일은 말을 책으로 바꾸고 안내문을 옮기는 것")
A("- 지시문 두 가지: **지금 지시문**(저장소 main 그대로) · **고친 안**(1·2항만 바꿈: 내용·저자·외국어판 제목을 한국어판 제목으로 바꿔 넘기고, "
  "하나로 정해지지 않으면 되묻기). 고친 안은 이 실측의 복제본에서만 돌렸고 저장소 main에는 없다. 바꾼 문장은 맨 아래에 적었다.")
A("- 기준 판정: 기대한 책의 정확한 제목으로 도구를 직접 부른 결과(모델 없이, 같은 작업 안에서)")
A("- 책 확인: 모델의 도구 호출이 돌려준 ISBN이 기준과 같거나 본서명이 같으면 맞음(판이 다른 같은 책 포함)")
A("- 기록용 계측: 복제본 호스트가 도구 결과의 서지·주소·소장관·안내문을 기록 줄에 함께 남김(모델에 가는 내용은 같음)")
A("- 원 기록: 같은 폴더의 `ai_metrics_run" + RUN_ID + "_*.json`(채점 결과·답 원문)·`*_calls_*.ndjson`(도구 호출)·`*_answers_*.ndjson`(최종 답). "
  "실제로 돌린 결과이며 사람이 고치지 않았다")
A("")
A("## 한눈에")
A("")
hdr = " | ".join(f"{NAME.get(m, m)} · {VAR.get(v, v)}" for m, v in ORDER)
A(f"| 항목 | {hdr} |")
A("|---|" + "---|" * len(ORDER))

def row(label, f):
    A(f"| {label} | " + " | ".join(f(R(k)) for k in ORDER) + " |")

row("도구를 불렀다(명확한 문의 20건)", lambda rs: frac(rs, lambda r: r["called"], clear))
row("**책을 맞게 찾았다**(모델 + 도구, 20건)", lambda rs: frac(rs, lambda r: r["book_ok"], clear) + pct(rs, lambda r: r["book_ok"], clear))
for cat, label in (("묘사", "  ㄴ 제목 없이 저자·내용(6건)"), ("오타", "  ㄴ 제목 글자 틀림(4건)"), ("외국어", "  ㄴ 외국어(8건)"), ("대조", "  ㄴ 정확한 제목(대조 2건)")):
    row(label, lambda rs, c=cat: frac(rs, lambda r: r["book_ok"], lambda r: r["cat"] == c))
row("**모델이 한국어판 제목으로 바꿔 넘겼다**(묘사·오타·외국어 18건)", lambda rs: frac(rs, lambda r: r.get("title_arg_ok"), lambda r: clear(r) and r["cat"] != "대조")
    + pct(rs, lambda r: r.get("title_arg_ok"), lambda r: clear(r) and r["cat"] != "대조"))
for cat, label in (("묘사", "  ㄴ 제목 없이 저자·내용(6건)"), ("오타", "  ㄴ 제목 글자 틀림(4건)"), ("외국어", "  ㄴ 외국어(8건)")):
    row(label, lambda rs, c=cat: frac(rs, lambda r: r.get("title_arg_ok"), lambda r: r["cat"] == c))
row("다른 책으로 답함(위험한 실패)", lambda rs: frac(rs, lambda r: r["wrong_book"], clear))
row("책을 찾지 못함(안전한 실패)", lambda rs: frac(rs, lambda r: r["not_found"], clear))
row("**판정 갈래가 기준과 같다**(책을 맞게 알아들은 경우)", lambda rs: frac(rs, lambda r: r["route_ok"], lambda r: r.get("route_ok") is not None))
row("안내문에 조회일 그대로", lambda rs: frac(rs, lambda r: fact(r, "date"), lambda r: fact(r, "date") is not None))
row("안내문에 누리집 주소 그대로", lambda rs: frac(rs, lambda r: fact(r, "link"), lambda r: fact(r, "link") is not None))
row("안내문에 도서관 이름(소장관·수령관)", lambda rs: frac(rs, lambda r: fact(r, "lib"), lambda r: fact(r, "lib") is not None))
row("안내문에 대출 가능(중) 관 수", lambda rs: frac(rs, lambda r: fact(r, "count"), lambda r: fact(r, "count") is not None))
row("**안내문 사실 모두 옮김**", lambda rs: frac(rs, lambda r: fact(r, "all"), lambda r: fact(r, "all") is not None)
    + pct(rs, lambda r: fact(r, "all"), lambda r: fact(r, "all") is not None))
row("번역문에도 사실 모두(한국어 원문 줄 빼고)", lambda rs: frac(rs, lambda r: fact(r, "all", True), lambda r: fact(r, "all", True) is not None))
row("이용자 언어로 답했다(외국어 9건)", lambda rs: frac(rs, lambda r: r["lang_ok"], lambda r: r["lang"] != "ko"))
row("**모호한 말에 되물었다**(4건)", lambda rs: frac(rs, lambda r: r["asked"], amb))
row("  ㄴ 도구를 부르기 전에 모델이 먼저 되물음", lambda rs: frac(rs, lambda r: r.get("asked_before_tool"), amb))
row("모호한 말에 아무 책이나 골라 답함", lambda rs: frac(rs, lambda r: r.get("answered_some_book"), amb))
row("중계 조회 불가로 판정 못함(환경)", lambda rs: frac(rs, lambda r: r.get("infra")))
row("문의 1건 평균 시간(초)", lambda rs: str(round(sum(r["seconds"] for r in rs) / max(1, len(rs)), 1)))
A("")
A("「책을 맞게 찾았다」는 모델이 넘긴 말로 도구가 기대한 책을 찾은 것이다. 도구는 시연 도서마다 찾기 낱말(예: 「편의점」·「온실」·「humanacts」)을 들고 있어, "
  "모델이 제목을 다 말하지 않아도 찾을 때가 있다. 그래서 모델만의 몫은 「한국어판 제목으로 바꿔 넘겼다」(넘긴 말에 본서명이 들어 있음)로 따로 센다.")
A("")
A("분모는 해당하는 답만 센다(예: 누리집 주소는 도구가 주소를 준 답, 관 수는 관내 상호대차·예약·책바다 갈래). "
  "안내문 사실은 그 답의 근거가 된 도구 호출의 결과와 견준다(책을 잘못 알아들었어도 그 책의 사실을 옮겼는지 본다).")
A("")
A("## 문의별")
A("")
A("칸마다 회차 합계: 책 = 도구가 기대한 책을 찾은 횟수, 제목 = 모델이 한국어판 제목을 넣어 넘긴 횟수, 갈래 = 판정이 기준과 같은 횟수, 사실 = 안내문 사실을 모두 옮긴 횟수, 되물음 = 모호한 말에 되물은 횟수.")
A("")
A(f"| 번호 | 갈래 | 이용자의 말 | 기준(기대한 책 → 판정) | {hdr} |")
A("|---|---|---|---|" + "---|" * len(ORDER))
ref0 = docs[0]["ref"]
case_ids = sorted({r["no"] for d in docs for r in d["rows"]})
for no in case_ids:
    any_r = next(r for d in docs for r in d["rows"] if r["no"] == no)
    refs = {d["ref"].get(str(no), {}).get("route_label") for d in docs if d["ref"].get(str(no))}
    base = f"{any_r['expect']} → {' / '.join(sorted(x for x in refs if x)) or '—'}" if any_r["expect"] else "(되물어야 함)"
    cells = []
    for k in ORDER:
        rs = [r for r in R(k) if r["no"] == no]
        if not rs:
            cells.append("—"); continue
        if any_r["expect"]:
            c = f"책 {sum(1 for r in rs if r['book_ok'])}/{len(rs)} · 제목 {sum(1 for r in rs if r.get('title_arg_ok'))}/{len(rs)} · 갈래 {sum(1 for r in rs if r['route_ok'])}/{len(rs)}"
            fs = [r for r in rs if fact(r, 'all') is not None]
            if fs:
                c += f" · 사실 {sum(1 for r in fs if fact(r, 'all'))}/{len(fs)}"
            wrong = sorted({str(r.get('tool_title') or '').strip() for r in rs if r.get('wrong_book')})
            if wrong:
                c += "<br>다른 책: " + ", ".join(f"『{w}』" for w in wrong)
            args = sorted({str(r.get('utterance_arg') or '(도구 안 부름)') for r in rs if not r['book_ok']})
            if args:
                c += "<br>못 맞힌 말: " + ", ".join(f"「{a}」" for a in args)
        else:
            c = f"되물음 {sum(1 for r in rs if r['asked'])}/{len(rs)}"
            some = sorted({str(r.get('tool_title') or '').strip() for r in rs if r.get('answered_some_book')})
            if some:
                c += "<br>골라 답한 책: " + ", ".join(f"『{w}』" for w in some)
        cells.append(c)
    ask = any_r["ask"].replace("|", "/")
    A(f"| {no} | {any_r['cat']} | {ask} | {base} | " + " | ".join(cells) + " |")
A("")
A("## 읽는 법과 한계")
A("")
A("- 판정은 도구가 정한다. 모델이 책을 맞게 알아들으면 판정은 기준과 같아야 하고, 이 표의 「판정 갈래가 기준과 같다」가 그것을 센다. "
  "모델이 책을 잘못 알아들으면 판정도 다른 책의 것이 되므로, 책이지는 답과 접수 메모 첫 줄에 제목·저자·ISBN을 적어 사서가 바로 확인하게 했다.")
A("- 「다른 책으로 답함」은 사서의 ISBN 확인이 꼭 필요한 경우이고, 「책을 찾지 못함」은 되묻거나 창구 조회로 넘어가는 경우다.")
A("- 안내문 사실은 기계 판정이다: 조회일은 여러 나라 날짜 표기, 도서관 이름은 한글·로마자·일부 한자 표기, 관 수는 숫자와 세는 말이 붙어 있을 때만 맞음으로 센다. "
  "숫자를 글자로 쓰거나 다른 표기를 쓰면 틀림으로 세어질 수 있다(실제보다 낮게 나올 수 있음).")
A("- 언어 판정은 글자 종류로 본 자동 판정이며 번역의 정확성은 원어민 확인 전이다.")
A("- 그래픽카드 없는 CPU 서버라 시간이 길다. 시간은 환경 차이를 그대로 적은 것이고, 판정은 도구가 정하므로 시간과 상관없다.")
A("- 중계에 닿지 못하면 도구는 「소장 확인 불가」로 답한다. 그런 경우는 「중계 조회 불가」 줄에 따로 세었다.")
A("")
items = {d["variant"]: d.get("prompt_items") for d in docs}
shas = {}
for d in docs:
    if d.get("prompt_sha"): shas.setdefault(d["variant"], set()).add(d["prompt_sha"])
if shas:   # [11. 2.] 서버가 실제로 읽은 지시문 파일의 지문 — 고친 안이 정말 들어갔는지 기록으로 남긴다
    A("지시문 파일 지문(서버가 실제로 읽은 파일, sha256 앞 12자): " + " · ".join(f"{k} {'/'.join(sorted(v))}" for k, v in sorted(shas.items())))
    A("")
if "title" in items:
    A("## 고친 안에서 바꾼 지시문(1·2항)")
    A("")
    A("지금 지시문:")
    A("")
    for l in (items.get("main") or "").splitlines():
        A(f"> {l}")
    A("")
    A("고친 안:")
    A("")
    for l in (items.get("title") or "").splitlines():
        A(f"> {l}")
    A("")
if "title_lang" in items:
    A("## 고친 안 4(고친 안 + 번역 7항)의 지시문(1·2·7항)")
    A("")
    A("고친 안(1·2항)에 7항을 「판정 한 줄과 안내문을 그 언어로 직접 번역해 먼저 쓰고, 번역하지 않은 한국어를 외국어 자리에 두지 않는다」로 고쳤다. 저장소 main의 지시문은 바꾸지 않았다.")
    A("")
    for l in (items.get("title_lang") or "").splitlines():
        A(f"> {l}")
    A("")
if "retry" in items:
    A("## 고친 안 3(못 찾으면 한국어판 제목으로 다시)의 지시문(1·2항)")
    A("")
    A("1·2항은 저장소 그대로 두고, 도구가 책을 못 찾았을 때만 한국어판 제목으로 한 번 더 부르고 답은 이용자의 언어 그대로 쓰라는 문장을 2항 끝에 더했다. 저장소 main의 지시문은 바꾸지 않았다.")
    A("")
    for l in (items.get("retry") or "").splitlines():
        A(f"> {l}")
    A("")
if "title2" in items:
    A("## 고친 안 2(언어 유지)의 지시문(1·2항)")
    A("")
    A("고친 안의 2항 끝에 「제목을 한국어판으로 바꿔 넘겨도 언어 코드와 답의 언어는 이용자가 쓴 말 그대로」 한 문장을 더했다. 저장소 main의 지시문은 바꾸지 않았다.")
    A("")
    for l in (items.get("title2") or "").splitlines():
        A(f"> {l}")
    A("")
A("---")
A("대출 상태는 정보나루 조회일 전일 기준이며, 이 기록의 어떤 상담도 실제 접수로 이어지지 않았다. "
  "GPT-OSS(오픈AI)와 EXAONE(LG AI연구원)은 내려받는 공개 모델로, 참가 안내서(10. 21. 변경판)가 행정안전부 AI 공통기반에서 지원(또는 지원 예정)하는 모델로 든 것이다.")
DST.mkdir(parents=True, exist_ok=True)
stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d_%H%M")
out = DST / f"ai_metrics_record_actions_{stamp}.md"
out.write_text("\n".join(LINES) + "\n", encoding="utf-8")
print("\n".join(LINES[:45]))
print("기록:", out)
