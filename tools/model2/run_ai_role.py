#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI가 맡는 몫 반복 실측: 이용자가 제목을 정확히 말하지 않거나 외국어로 물을 때, 모델이 말을 책으로 바꾸고(도구 인자)
안내문을 이용자 언어로 옮기는지, 그리고 도구가 정한 판정·조회일·누리집 주소를 바꾸지 않는지를 문의 10건 × 2회로 잰다.

같은 것: 저장소 main의 서버(server.py, 모드 auto)·지시문(프롬프트 consult)·호스트(server/hosts/ollama_host.py) 그대로,
         모델에 보이는 도구는 consult_request 하나. 받을 도서관·이용자 언어는 창구가 정하는 값이라 호스트 인자로 준다(엑사원·라마·GPT-OSS 실측과 같은 방식).
다른 것: 문의 10건(묘사·오타·외국어 5종·모호한 말)과 반복 횟수(기본 2회). 모델은 GPT-OSS(gpt-oss:20b, 공개 모델).
채점은 사람 손 없이 기계로: ① 도구를 불렀나 ② 모델이 넘긴 말로 도구가 찾은 책이 기대한 책인가(같은 인자로 도구를 다시 불러 ISBN 확인)
  ③ 판정 갈래가 기준(정확한 제목으로 도구를 직접 부른 결과)과 같은가 ④ 답에 조회일·누리집 주소가 그대로 있나
  ⑤ 답이 이용자 언어인가(글자 종류로 본 자동 판정, 원어민 확인 전) ⑥ 모호한 말에는 되물었나.
인증키·결제 없음. 기록은 실제로 돌린 결과만 담고, 실패도 그대로 적는다."""
import os, sys, re, json, time, datetime, pathlib, subprocess, urllib.request

KST = datetime.timezone(datetime.timedelta(hours=9))
WORK = pathlib.Path(os.environ.get("WORK_DIR", "/content"))
MODEL = os.environ.get("AI_ROLE_MODEL", "gpt-oss:20b")
REPEATS = int(os.environ.get("AI_ROLE_REPEATS", "2"))
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")

# (번호, 이용자의 말, 받을 도서관, 이용자 언어, 기대한 책 ISBN 또는 None(되묻기 기대), 기대한 책 이름, 보는 것)
CASES = [
    (1, "한강 작가가 광주 이야기 쓴 책 있잖아요, 역곡에서 받을 수 있어요?", "역곡", "ko", "9788936434120", "소년이 온다", "제목 없이 내용으로(10. 30. 클로드 실측과 같은 문장)"),
    (2, "히가시노 게이고 소설인데 잡화점에 고민 편지 보내는 이야기 빌리고 싶어요", "상동", "ko", "9788972756194", "나미야 잡화점의 기적", "저자와 줄거리로"),
    (3, "불편한편의점 잇나요? 원미에서 받을게요", "원미", "ko", "9791161571188", "불편한 편의점", "띄어쓰기·맞춤법 틀림"),
    (4, "노벨상 받은 한강 작가 책 중에 고기를 안 먹게 된 여자 이야기요", "상동", "ko", "9788936433598", "채식주의자", "내용으로(시연 도서 밖, 그날 조회)"),
    (5, "Xin chào, tôi muốn mượn cuốn \"Cửa hàng tiện lợi bất tiện\". Tôi có thể nhận ở thư viện Sangdong không?", "상동", "vi",
     "9791161571188", "불편한 편의점", "베트남어 번역 제목(10. 30. 클로드 실측과 같은 문장)"),
    (6, "Tôi muốn mượn cuốn sách của nhà văn Han Kang viết về sự kiện Gwangju.", "상동", "vi", "9788936434120", "소년이 온다", "베트남어로 내용만"),
    (7, "我想借《解忧杂货店》，可以在上东图书馆取书吗？", "상동", "zh", "9788972756194", "나미야 잡화점의 기적", "중국어 번역 제목"),
    (8, "Do you have Human Acts by Han Kang? I'd like to pick it up at Sangdong library.", "상동", "en", "9788936434120", "소년이 온다", "영어 번역 제목"),
    (9, "『ナミヤ雑貨店の奇蹟』を借りたいです。上洞図書館で受け取れますか。", "상동", "ja", "9788972756194", "나미야 잡화점의 기적", "일본어 원제"),
    (10, "한강 책 빌리고 싶어요", "상동", "ko", None, "(되묻기)", "모호한 말: 어느 책인지 되물어야 함"),
]

WORK.mkdir(parents=True, exist_ok=True)
os.chdir(WORK)
if not (WORK / "chaekiji").exists():
    subprocess.run(["git", "clone", "--depth", "1", "https://github.com/altarry-prog/chaekiji.git"], check=True)
os.chdir(WORK / "chaekiji" / "server")
subprocess.run([sys.executable, "-m", "pip", "-q", "install", "pyyaml"], check=True)
COMMIT = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
OUT_DIR = pathlib.Path("lab/out"); OUT_DIR.mkdir(parents=True, exist_ok=True)
STAMP = datetime.datetime.now(KST).strftime("%Y-%m-%d_%H%M")
print("저장소 main", COMMIT, "· 모델", MODEL, "· 반복", REPEATS, flush=True)

def _sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()
OLLAMA_VER = json.load(urllib.request.urlopen(OLLAMA + "/api/version"))["version"]
ENVINFO = [f"CPU {os.cpu_count()}코어 · GPU 없음", "메모리: " + " ".join(_sh("free -h | sed -n 2p").split()[1:3]) + "(전체·사용)",
           f"Ollama {OLLAMA_VER}", "모델: " + " · ".join(l for l in _sh("ollama list").splitlines()[1:] if l.strip())]

# 도구를 직접 부르는 연결(기준 판정·책 확인용)
sys.path.insert(0, "hosts")
import ollama_host as oh  # noqa: E402
def tool(args):
    mcp = oh.MCP("server.py", dict(os.environ, CHAEKIJI_MODE="auto", PYTHONUTF8="1"))
    try:
        text, err = mcp.call("consult_request", args)
    finally:
        mcp.close()
    try:
        return json.loads(text), err
    except Exception:
        return {"_raw": (text or "")[:300]}, True

# ① 기준: 기대한 책의 정확한 제목으로 도구를 직접 부른다(같은 받을 도서관·언어)
REF = {}
for no, ask, pickup, lang, isbn, title, _ in CASES:
    q = title if isbn else ask
    o, err = tool({"utterance": q, "pickup": pickup, "lang": lang})
    REF[no] = {"q": q, "route": o.get("route"), "route_label": o.get("route_label", "—"), "isbn": (o.get("book") or {}).get("isbn13"),
               "asof": (o.get("availability") or {}).get("asof"), "link": o.get("official_link"), "mode": o.get("mode"), "error": err}
    print(f"기준 {no}: 「{q}」 → {REF[no]['route_label']} · {REF[no]['isbn']} · {REF[no]['asof']}", flush=True)

# ② 모델 실행: 문의 10건 × REPEATS회, 회차마다 기록 파일을 따로
RUNLOG = {}
for rep in range(1, REPEATS + 1):
    calls_p = OUT_DIR / f"ai_role_calls_actions_{STAMP}_r{rep}.ndjson"
    ans_p = OUT_DIR / f"ai_role_answers_actions_{STAMP}_r{rep}.ndjson"
    for no, ask, pickup, lang, isbn, title, _ in CASES:
        t0 = time.time()
        try:
            r = subprocess.run([sys.executable, "hosts/ollama_host.py", "--model", MODEL, "--ollama", OLLAMA, "--mode", "auto",
                                "--pickup", pickup, "--lang", lang, "--ask", ask, "--log", str(calls_p), "--answers", str(ans_p),
                                "--tools", "consult", "--timeout", "1800", "--num-ctx", "8192"], capture_output=True, text=True,
                               encoding="utf-8", timeout=2400, env=dict(os.environ))
            out = (r.stdout or "")[-1500:] + ("\n" + (r.stderr or "")[-500:] if r.returncode else "")
        except subprocess.TimeoutExpired:
            out = "(시간 초과 40분: 답 없음으로 기록)"
        RUNLOG[(rep, no)] = out
        print(f"\n━━ {rep}회차 · 문의 {no} ({time.time() - t0:.0f}초)\n{out[-700:]}", flush=True)
PS = _sh("ollama ps")

# ③ 채점
def rows(p):
    p = pathlib.Path(p)
    return [json.loads(l) for l in open(p, encoding="utf-8")] if p.exists() else []

VI = set("ăâđêôơưàáạảãầấậẩẫằắặẳẵèéẹẻẽềếệểễìíịỉĩòóọỏõồốộổỗờớợởỡùúụủũừứựửữỳýỵỷỹ")
def lang_ok(text, lang):
    t = re.sub(r"https?://\S+", "", text or "")
    hangul = len(re.findall(r"[가-힣]", t)); han = len(re.findall(r"[一-鿿]", t))
    kana = len(re.findall(r"[぀-ヿ]", t)); vi = sum(1 for ch in t.lower() if ch in VI)
    en_words = len(re.findall(r"\b[A-Za-z]{3,}\b", t))
    if lang == "ko": return hangul >= 30
    if lang == "vi": return vi >= 15
    if lang == "zh": return han >= 20 and kana < 5
    if lang == "ja": return kana >= 15
    if lang == "en": return en_words >= 25
    return False

def date_kept(text, asof):
    if not asof: return False
    y, m, d = asof.split("-"); m, d = int(m), int(d)
    pats = [rf"{y}\.\s*{m}\.\s*{d}\.?", rf"{y}-{m:02d}-{d:02d}", rf"{d:02d}/{m:02d}/{y}", rf"{d}/{m}/{y}", rf"{y}年{m}月{d}日",
            rf"ngày\s*{d}\s*tháng\s*{m}", rf"{d}\s*tháng\s*{m}", rf"(October|November)\s+{d},?\s+{y}", rf"{d}\s+(October|November)\s+{y}"]
    return any(re.search(p, text or "", re.I) for p in pats)

ASKBACK = re.compile(r"[?？]|어느|어떤|알려\s*주|말씀해|확인해\s*주시|which|Which|cuốn nào|哪|どの")
S = []
for rep in range(1, REPEATS + 1):
    calls = rows(OUT_DIR / f"ai_role_calls_actions_{STAMP}_r{rep}.ndjson")
    answers = rows(OUT_DIR / f"ai_role_answers_actions_{STAMP}_r{rep}.ndjson")
    for no, ask, pickup, lang, isbn, title, _ in CASES:
        cs = [c for c in calls if c.get("ask") == ask and c.get("tool") == "consult_request"]
        an = next((a for a in answers if a.get("ask") == ask), None)
        text = (an or {}).get("answer", "") or ""
        last = cs[-1] if cs else None
        args = (last or {}).get("arguments") or {}
        got_isbn, link, asof, route = None, None, None, (last or {}).get("route")
        if last and not last.get("error"):
            o, _ = tool({"utterance": args.get("utterance", ""), "pickup": args.get("pickup") or pickup, "lang": args.get("lang") or lang})
            got_isbn = (o.get("book") or {}).get("isbn13"); link = o.get("official_link"); asof = (o.get("availability") or {}).get("asof")
        ref = REF[no]
        if isbn:
            book_ok = got_isbn == isbn
            route_ok = bool(route) and route == ref["route"]
            kept_date = date_kept(text, asof or ref["asof"])
            kept_link = bool(link) and link in text
            asked = None
        else:
            book_ok = route_ok = kept_date = kept_link = None
            asked = (not last or not (last or {}).get("found")) and bool(ASKBACK.search(text))
        S.append({"rep": rep, "no": no, "lang": lang, "called": bool(cs), "n_calls": len(cs), "utterance_arg": args.get("utterance"),
                  "pickup_arg": args.get("pickup"), "lang_arg": args.get("lang"), "got_isbn": got_isbn, "book_ok": book_ok,
                  "route": (last or {}).get("route_label"), "route_ok": route_ok, "kept_date": kept_date, "kept_link": kept_link,
                  "lang_ok": lang_ok(text, lang) if text.strip() else False, "asked": asked,
                  "seconds": round((an or {}).get("total_ms", 0) / 1000, 1), "answer": text})

def yn(v): return "—" if v is None else ("○" if v else "×")
now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
book_cases = [c for c in CASES if c[4]]
def cnt(key, rep=None, langs=None):
    ss = [s for s in S if (rep is None or s["rep"] == rep) and s[key] is not None and (langs is None or s["lang"] in langs)]
    return f"{sum(1 for s in ss if s[key])}/{len(ss)}"
L = [f"# AI가 맡는 몫 반복 실측 — {MODEL} · 문의 10건 × {REPEATS}회 ({now} KST)", "",
     "- 무엇을 재나: 이용자가 제목을 정확히 말하지 않거나 외국어로 물을 때 **말을 책으로 바꾸는 일과 안내문을 옮기는 일은 모델이**, "
     "**판정·조회일·누리집 주소는 도구가** 정하는지. 모델이 도구 결과를 바꾸지 않는지.",
     "- 실행 환경: GitHub Actions(ubuntu-latest, 사람 손 없음) · " + " · ".join(ENVINFO) + " · 인증키·결제 없음",
     f"- 실행 기록(공개): {os.environ.get('RUN_URL', '—')}",
     f"- 책이지: 저장소 main 커밋 `{COMMIT}` · 서버 `server.py`(모드 auto: 시연 도서는 그날 새벽 자료, 그 밖의 책은 중계로 그날 조회) · "
     "지시문 프롬프트 `consult` · 호스트 `server/hosts/ollama_host.py` 그대로 · 모델에 보이는 도구는 `consult_request` 하나 · 문맥 8192",
     "- 받을 도서관·이용자 언어: 창구가 정하는 값이라 호스트 인자로 주었다(엑사원·라마·GPT-OSS 5건 실측과 같은 방식). 모델이 할 일은 말을 책으로 바꾸고 안내문을 옮기는 것",
     "- 기준 판정: 기대한 책의 정확한 제목으로 도구를 직접 부른 결과(모델 없이)",
     "- 책 확인: 모델이 도구에 넘긴 말을 같은 도구에 다시 넣어 나온 ISBN을 기대한 책과 견줌",
     "- 언어 판정: 글자 종류로 본 자동 판정(베트남어 성조 글자·한자·가나·영어 낱말 수). **원어민 확인 전**",
     f"- 실행 직후 모델 상태(ollama ps): " + (" / ".join(l.strip() for l in PS.splitlines()) or "(정보 없음)"),
     f"- 원 기록: `ai_role_calls_actions_{STAMP}_r*.ndjson`(도구 호출) · `ai_role_answers_actions_{STAMP}_r*.ndjson`(최종 답) — 실제로 돌린 결과이며 사람이 고치지 않았다", "",
     "## 한눈에", "",
     "| 항목 | " + " | ".join(f"{r}회차" for r in range(1, REPEATS + 1)) + " | 합계 |", "|---|" + "---|" * (REPEATS + 1)]
for key, name in [("called", "도구를 불렀다"), ("book_ok", "책을 맞게 알아들었다(9건)"), ("route_ok", "판정 갈래가 기준과 같다"),
                  ("kept_date", "조회일을 답에 그대로 옮겼다"), ("kept_link", "누리집 주소를 그대로 옮겼다")]:
    L.append(f"| {name} | " + " | ".join(cnt(key, r) for r in range(1, REPEATS + 1)) + f" | {cnt(key)} |")
L.append("| 이용자 언어로 답했다(외국어 5건) | " + " | ".join(cnt('lang_ok', r, {'vi', 'zh', 'en', 'ja'}) for r in range(1, REPEATS + 1))
         + f" | {cnt('lang_ok', None, {'vi', 'zh', 'en', 'ja'})} |")
L.append("| 모호한 말에 되물었다(1건) | " + " | ".join(cnt('asked', r) for r in range(1, REPEATS + 1)) + f" | {cnt('asked')} |")
L += ["", "○ 맞음 · × 틀림 · — 해당 없음. 판정 갈래가 기준과 다르면 대개 책을 잘못 알아들었거나 도구를 부르지 않은 경우다.", "",
      "## 문의별", "", "| 번호 | 보는 것 | 기준(기대한 책 → 판정) | 회차 | 모델이 넘긴 말 | 책 | 판정 | 조회일 | 주소 | 언어 | 되물음 | 시간 |",
      "|---|---|---|---|---|---|---|---|---|---|---|---|"]
for no, ask, pickup, lang, isbn, title, what in CASES:
    ref = REF[no]
    for s in [s for s in S if s["no"] == no]:
        L.append(f"| {no} | {what} | {title} → {ref['route_label']} | {s['rep']} | {s['utterance_arg'] or '(도구 안 부름)'} | {yn(s['book_ok'])} | "
                 f"{s['route'] or '—'} | {yn(s['kept_date'])} | {yn(s['kept_link'])} | {yn(s['lang_ok'])} | {yn(s['asked'])} | {s['seconds']}초 |")
L.append("")
for no, ask, pickup, lang, isbn, title, what in CASES:
    L += [f"### 문의 {no}. {ask}", "", f"받을 도서관 {pickup} · 언어 {lang} · 기대 {title} · 기준 판정 **{REF[no]['route_label']}**({REF[no]['mode']} · {REF[no]['asof']})", ""]
    for s in [s for s in S if s["no"] == no]:
        body = (s["answer"] or "").strip().replace("\n", "<br>") or "(답 없음)"
        L += [f"<details><summary>{s['rep']}회차 답 원문({s['seconds']}초)</summary>", "", body, "", "</details>", ""]
        if not s["answer"].strip():
            L += ["```", (RUNLOG.get((s['rep'], no)) or "").strip()[-800:] or "(출력 없음)", "```", ""]
L += ["## 읽는 법과 한계", "",
      "- 모델이 책을 잘못 알아들으면 판정도 다른 책의 것이 된다. 그래서 책이지의 답과 접수 메모 첫 줄에 책 제목·저자·ISBN을 적어 사서가 바로 확인하게 했다.",
      "- 도구를 부르지 않고 쓴 답(○가 없는 줄)은 판정 근거가 없으므로 창구에서 쓰지 않는다. 이 실측은 그런 경우가 몇 번 나오는지도 그대로 센다.",
      "- 그래픽카드 없는 CPU 서버라 시간이 길다. 시간은 환경 차이를 그대로 적은 것이고, 판정은 도구가 정하므로 시간과 상관없다.",
      "- 언어 판정은 글자 종류로 본 기계 판정이며 번역의 정확성은 원어민 확인 전이다.", "",
      "---", "대출 상태는 정보나루 조회일 전일 기준이며, 이 기록의 어떤 상담도 실제 접수로 이어지지 않았다. "
      "GPT-OSS는 오픈AI가 공개한 내려받는 모델로 행정안전부 AI 공통기반 목록(참가 안내서 10. 21. 변경판)에 있다."]
REC = OUT_DIR / f"ai_role_record_actions_{STAMP}.md"
REC.write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L[:40]))
print("기록:", REC)
