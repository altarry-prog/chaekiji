#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI가 맡는 몫 지표: 고정 문의 24건으로 공개 모델이
① 이용자의 말을 책으로 바꾸는지(책 식별) ② 도구가 정한 판정을 그대로 두는지(갈래 일치)
③ 안내문에 도구가 준 사실(도서관 이름·대출 가능 관 수·조회일·누리집 주소)을 옮기는지 ④ 모호한 말에 되묻는지를 잰다.
작업 하나가 (모델, 지시문, 회차) 하나를 돌고, 여러 작업의 결과는 report_ai_metrics.py가 모아 기록표를 만든다.

같은 것: 저장소 main의 서버(server.py)·호스트(server/hosts/ollama_host.py)·지시문(프롬프트 consult).
         서버 모드는 snapshot: 시연 도서 5종의 그날 새벽 자료만 쓰고 정보나루를 부르지 않는다(하루 호출 한도 500건 보호.
         11. 1. 13:44 첫 실행이 시연 도서 밖 책을 정보나루로 조회하다 한도를 넘겨 취소했다). 시연 도서 5종은 auto 모드와 같은 판정이다.
         모델에 보이는 도구는 consult_request 하나. 받을 도서관·이용자 언어는 창구가 정하는 값이라 호스트 인자로 준다(지금까지의 실측과 같은 방식).
지시문 두 가지: main(저장소 그대로) · title(1·2항을 고친 안: 내용·저자·외국어판 제목을 한국어판 제목으로 바꿔 넘기고,
         하나로 정해지지 않으면 되묻는다). title은 이 실측의 복제본에서만 지시문 파일을 바꿔 돌린 것이며 저장소 main에는 없다.
기록용 계측: 복제본의 호스트가 도구 결과 가운데 서지·주소·소장관·안내문을 기록 파일에 함께 남기게 한 줄을 더한다(모델에 가는 내용은 같다).
채점은 사람 손 없이 기계로 한다. 인증키·결제 없음. 실패도 그대로 적는다."""
import os, sys, re, json, time, datetime, pathlib, subprocess, urllib.request

KST = datetime.timezone(datetime.timedelta(hours=9))
WORK = pathlib.Path(os.environ.get("WORK_DIR", "/content"))
MODEL = os.environ.get("AI_MODEL", "gpt-oss:20b")
VARIANT = os.environ.get("AI_VARIANT", "main")          # main | title | title2 | retry | title_lang
REP = int(os.environ.get("AI_REP", "1"))
RUN_ID = os.environ.get("RUN_ID", datetime.datetime.now(KST).strftime("%m%d%H%M"))
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MIN_GAP = float(os.environ.get("AI_MIN_GAP", "0"))     # 문의 사이 최소 간격(초). snapshot 모드는 정보나루·중계를 부르지 않아 기본 0
SMODE = os.environ.get("AI_SERVER_MODE", "snapshot")    # snapshot: 정보나루 호출 0(시연 도서 5종만) · auto: 중계로 그날 조회(하루 한도 주의)
SLUG = re.sub(r"[^a-z0-9]+", "-", MODEL.lower()).strip("-")

# (번호, 갈래, 이용자의 말, 받을 도서관, 이용자 언어, 기대한 책 제목 또는 None(되묻기 기대), 보는 것)
CASES = [
    (1, "묘사", "한강 작가가 광주 이야기 쓴 책 있잖아요, 역곡에서 받을 수 있어요?", "역곡", "ko", "소년이 온다", "제목 없이 저자·내용으로"),
    (2, "묘사", "히가시노 게이고 소설인데 잡화점에 고민 편지 보내는 이야기 빌리고 싶어요", "상동", "ko", "나미야 잡화점의 기적", "저자와 줄거리로"),
    (3, "묘사", "서울역 노숙자가 편의점에서 야간 알바하는 소설 있죠? 역곡에서 받고 싶어요", "역곡", "ko", "불편한 편의점", "줄거리만으로"),
    (4, "묘사", "김초엽 작가 SF인데 더스트 이후에 식물 키우는 온실 이야기요", "상동", "ko", "지구 끝의 온실", "저자와 줄거리로"),
    (5, "묘사", "김호연 작가 소설인데 독고라는 노숙자가 나오는 거요, 원미에서 받을게요", "원미", "ko", "불편한 편의점", "저자와 등장인물로"),
    (6, "묘사", "아이가 보는 설민석 선생님 한국사 만화 시리즈 있죠?", "상동", "ko", "설민석의 한국사 대모험", "저자와 갈래로"),
    (7, "오타", "불편한편의점 잇나요? 원미에서 받을게요", "원미", "ko", "불편한 편의점", "띄어쓰기·맞춤법"),
    (8, "오타", "나미야 잡하점의 기적 빌릴수있나요", "상동", "ko", "나미야 잡화점의 기적", "제목 글자 틀림"),
    (9, "오타", "지구끝에 온실 송내에서 받을래요", "송내", "ko", "지구 끝의 온실", "띄어쓰기·조사 틀림"),
    (10, "오타", "한강 소년이 온데 있어요? 북부에서 받을게요", "북부", "ko", "소년이 온다", "제목 끝 글자 틀림"),
    (11, "외국어", "Xin chào, tôi muốn mượn cuốn \"Cửa hàng tiện lợi bất tiện\". Tôi có thể nhận ở thư viện Sangdong không?", "상동", "vi",
     "불편한 편의점", "베트남어 번역 제목"),
    (12, "외국어", "Tôi muốn mượn cuốn sách của nhà văn Han Kang viết về sự kiện Gwangju.", "상동", "vi", "소년이 온다", "베트남어로 저자·내용만"),
    (13, "외국어", "Thư viện có cuốn \"Điều kỳ diệu của tiệm tạp hóa Namiya\" không? Tôi muốn nhận ở thư viện Yeokgok.", "역곡", "vi",
     "나미야 잡화점의 기적", "베트남어 번역 제목"),
    (14, "외국어", "我想借《解忧杂货店》，可以在上东图书馆取书吗？", "상동", "zh", "나미야 잡화점의 기적", "중국어 번역 제목"),
    (15, "외국어", "有没有韩江写的关于光州事件的小说？我想在驿谷图书馆取。", "역곡", "zh", "소년이 온다", "중국어로 저자·내용만"),
    (16, "외국어", "Do you have Human Acts by Han Kang? I'd like to pick it up at Sangdong library.", "상동", "en", "소년이 온다", "영어 번역 제목"),
    (17, "외국어", "I'm looking for The Greenhouse at the End of the Earth by Kim Cho-yeop. Can I get it at Wonmi?", "원미", "en",
     "지구 끝의 온실", "영어 번역 제목"),
    (18, "외국어", "『ナミヤ雑貨店の奇蹟』を借りたいです。上洞図書館で受け取れますか。", "상동", "ja", "나미야 잡화점의 기적", "일본어 원제"),
    (19, "대조", "지구 끝의 온실 상동에서 빌릴 수 있어요?", "상동", "ko", "지구 끝의 온실", "정확한 제목(대조)"),
    (20, "대조", "나미야 잡화점의 기적 역곡에서 받을 수 있나요?", "역곡", "ko", "나미야 잡화점의 기적", "정확한 제목(대조)"),
    (21, "모호", "한강 책 빌리고 싶어요", "상동", "ko", None, "저자 이름만: 어느 책인지 되물어야 함"),
    (22, "모호", "히가시노 게이고 소설 빌리고 싶은데요", "상동", "ko", None, "저자 이름만: 어느 책인지 되물어야 함"),
    (23, "모호", "Tôi muốn mượn sách của Han Kang.", "상동", "vi", None, "베트남어로 저자 이름만: 되물어야 함"),
    (24, "모호", "요즘 많이 읽는 소설 하나 빌려 주세요", "상동", "ko", None, "책을 정하지 않음: 되물어야 함"),
]

# 지시문 고친 안(title): 1·2항만 바꾼다. 예시는 문의 24건에 없는 책으로 골랐다(문제에 맞춘 예시가 되지 않게).
P1_OLD = "1. 사실은 도구로만 확인합니다. 책 제목, 어느 도서관에 있는지, 대출 가능 여부, 상호대차 규정은 추측하지 않습니다."
P1_NEW = ("1. 사실은 도구로만 확인합니다. 어느 도서관에 있는지, 대출 가능 여부, 상호대차 규정은 추측하지 않습니다. "
          "책 제목은 2항대로 바꿔 넘기되, 그 책이 맞는지는 도구가 돌려준 서지(제목·저자·ISBN)로 확인합니다.")
P2_OLD = ("발화를 넘길 때는 가능하면 책 제목 부분만 넘깁니다(예: 「한강 소년이 온다 빌리고 싶어요」 → `utterance`에 「소년이 온다」).")
P2_NEW = ("`utterance`에는 책의 한국어판 제목만 넘깁니다(예: 「한강 소년이 온다 빌리고 싶어요」 → 「소년이 온다」). "
          "이용자가 제목 대신 내용·저자·등장인물로 말하거나 외국어판 제목으로 말하면, 어느 책인지 알 때 그 책의 한국어판 제목으로 바꿔 넘깁니다"
          "(예: 「김영하 작가가 쓴, 기억을 잃어 가는 연쇄살인범 이야기」 → 「살인자의 기억법」, 「Almond by Sohn Won-pyung」 → 「아몬드」). "
          "저자 이름만 듣는 등 어느 책인지 하나로 정해지지 않으면 도구를 부르지 말고 어느 책인지 되묻습니다.")

# 지시문 고친 안 2(title2, 11. 2.): 고친 안에서 Solar의 외국어 답이 26/27에서 13/27로 줄어, 제목만 한국어판으로 바꿔 넘기고
# 언어 코드와 답의 언어는 이용자가 쓴 말 그대로 두라는 한 문장을 2항 끝에 더한다(1항은 고친 안과 같음).
P2_NEW2 = P2_NEW + (" 제목을 한국어판으로 바꿔 넘겨도 `lang`에는 이용자가 실제로 쓴 언어의 코드를 넣고, "
                    "답과 안내문은 7항대로 그 언어로 씁니다.")

# 지시문 고친 안 3(retry, 11. 2.): 고친 안·고친 안 2는 책 찾기는 늘었지만 외국어 문의의 답이 한국어로 바뀌었다(제목을 먼저 한국어로 바꿔 넘기면
# 답까지 한국어로 쓰는 경향). 그래서 1·2항은 저장소 그대로 두고, 도구가 책을 못 찾았을 때만 한국어판 제목으로 한 번 더 부르게 하는 문장을 2항 끝에 더한다.
P2_RETRY = P2_OLD + (" 도구가 책을 찾지 못했다고 오면(`route: unknown`), 이용자가 내용·저자·외국어판 제목으로 말한 책이 무엇인지 알 때는 "
                     "그 책의 한국어판 제목으로 바꿔 한 번 더 부릅니다(예: 「Almond by Sohn Won-pyung」 → 「아몬드」). "
                     "그래도 못 찾거나 어느 책인지 하나로 정해지지 않으면 3항대로 되묻습니다. 답의 언어는 처음 물은 이용자의 언어 그대로입니다.")

# 지시문 고친 안 4(title_lang, 11. 2.): 고친 안(1·2항)에 7항을 세게 고친 것. 앞선 실측에서 책을 찾은 외국어 문의의 답이
# 도구의 한국어 안내문을 그대로 옮겨 한국어로 남는 일이 많아(「(Tiếng Việt)」라고 적고 한국어를 둠), 직접 번역하라는 말을 7항에 넣는다.
P7_OLD = "7. 이용자 언어가 한국어가 아니면(`translate_to`) 안내문을 그 언어로 옮기고, 한국어 원문을 바로 아래 함께 둡니다. 짧은 문장, 쉬운 말."
P7_NEW = ("7. 이용자 언어가 한국어가 아니면(`translate_to`) 판정 한 줄과 안내문을 그 언어로 직접 번역해 먼저 쓰고, 한국어 원문을 바로 아래 함께 둡니다. "
          "도구의 안내문은 한국어로 오므로 반드시 번역하며, 번역하지 않은 한국어를 외국어 자리에 두지 않습니다. "
          "조회일·누리집 주소·도서관 이름은 번역문에도 그대로 둡니다. 짧은 문장, 쉬운 말.")

WORK.mkdir(parents=True, exist_ok=True)
os.chdir(WORK)
if not (WORK / "chaekiji").exists():
    # 보안 검토(2026-11-09): 저장소 안의 고정된 파이썬 스크립트·명령을 인자 목록으로 실행하며 셸을 거치지 않음
    subprocess.run(["git", "clone", "--depth", "1", "https://github.com/altarry-prog/chaekiji.git"], check=True)  # nosemgrep
os.chdir(WORK / "chaekiji" / "server")
# 보안 검토(2026-11-09): 저장소 안의 고정된 파이썬 스크립트·명령을 인자 목록으로 실행하며 셸을 거치지 않음
subprocess.run([sys.executable, "-m", "pip", "-q", "install", "pyyaml"], check=True)  # nosemgrep
# 보안 검토(2026-11-09): 저장소 안의 고정된 파이썬 스크립트·명령을 인자 목록으로 실행하며 셸을 거치지 않음
COMMIT = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()  # nosemgrep
OUT_DIR = pathlib.Path("lab/out"); OUT_DIR.mkdir(parents=True, exist_ok=True)
TAG = f"run{RUN_ID}_{SLUG}_{VARIANT}_r{REP}"
print("저장소 main", COMMIT, "· 모델", MODEL, "· 지시문", VARIANT, "· 회차", REP, "· 서버 모드", SMODE, flush=True)

# 지시문 고친 안 적용(복제본만)
PROMPT = pathlib.Path("prompts/상담비서-지시문.md")
ptxt = PROMPT.read_text(encoding="utf-8")
if VARIANT in ("title", "title2"):
    if P1_OLD not in ptxt or P2_OLD not in ptxt:
        sys.exit("지시문 1·2항의 문장이 바뀌어 고친 안을 적용할 수 없습니다(실측 중단).")
    ptxt = ptxt.replace(P1_OLD, P1_NEW).replace(P2_OLD, P2_NEW if VARIANT == "title" else P2_NEW2)
elif VARIANT == "title_lang":
    if P1_OLD not in ptxt or P2_OLD not in ptxt or P7_OLD not in ptxt:
        sys.exit("지시문 1·2·7항의 문장이 바뀌어 고친 안 4를 적용할 수 없습니다(실측 중단).")
    ptxt = ptxt.replace(P1_OLD, P1_NEW).replace(P2_OLD, P2_NEW).replace(P7_OLD, P7_NEW)
elif VARIANT == "retry":
    if P2_OLD not in ptxt:
        sys.exit("지시문 2항의 문장이 바뀌어 고친 안 3을 적용할 수 없습니다(실측 중단).")
    ptxt = ptxt.replace(P2_OLD, P2_RETRY)
# [11. 2. 13:30 고침] 고친 안을 복제본 지시문 파일에 쓰는 줄이 retry 갈래 안에만 들어가 있어(fe5b84d부터), title·title2·title_lang은
# 메모리의 글만 바뀌고 서버가 읽는 파일은 저장소 그대로였다(12:25 title_lang 기록이 무효가 된 까닭). 이제 갈래와 상관없이 쓰고,
# 서버가 실제로 읽을 파일을 다시 읽어 고친 문장이 들어 있는지 확인한 뒤에만 실측한다. 파일 지문(sha256 앞 12자)을 기록에 남긴다.
PROMPT.write_text(ptxt, encoding="utf-8")
_served = PROMPT.read_text(encoding="utf-8")
_need = {"title": [P1_NEW, P2_NEW], "title2": [P1_NEW, P2_NEW2], "title_lang": [P1_NEW, P2_NEW, P7_NEW], "retry": [P2_RETRY]}.get(VARIANT, [P1_OLD, P2_OLD])
if not all(x in _served for x in _need):
    sys.exit(f"지시문 파일에 {VARIANT} 문장이 들어가지 않았습니다(실측 중단).")
import hashlib
PROMPT_SHA = hashlib.sha256(_served.encode("utf-8")).hexdigest()[:12]
print("지시문 파일 지문", PROMPT_SHA, "· 갈래", VARIANT, flush=True)
PROMPT_ITEMS = "\n".join(l for l in ptxt.splitlines() if l.startswith(("1. ", "2. ") + (("7. ",) if VARIANT == "title_lang" else ())))

# 기록용 계측(복제본 호스트): 도구 결과의 서지·주소·소장관·안내문을 기록 줄에 함께 남긴다
HOST = pathlib.Path("hosts/ollama_host.py")
hsrc = HOST.read_text(encoding="utf-8")
ANCHOR = '                    row.update({k: o[k] for k in ("found", "route", "route_label", "mode") if k in o})\n'
INSTRUMENTED = ANCHOR in hsrc
if INSTRUMENTED:
    ADD = ('                    row["metrics"] = {"isbn13": (o.get("book") or {}).get("isbn13"), "title": (o.get("book") or {}).get("title"), '
           '"official_link": o.get("official_link"), "from_lib": o.get("from_lib"), "pickup": o.get("pickup"), '
           '"available_at": (o.get("availability") or {}).get("available_at"), "loaned_at": (o.get("availability") or {}).get("loaned_at"), '
           '"notice": o.get("notice")}\n')
    HOST.write_text(hsrc.replace(ANCHOR, ANCHOR + ADD, 1), encoding="utf-8")

def _sh(cmd):
    # 보안 검토(2026-11-09): 측정 기록용으로 코드에 적힌 고정 명령(ollama·nproc 등)만 실행하며 이용자 입력은 들어가지 않음
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()  # nosemgrep
# 보안 검토(2026-11-09): 호출 주소는 코드·환경설정에 고정된 로컬 Ollama 주소이며 이용자 입력으로 바뀌지 않음
OLLAMA_VER = json.load(urllib.request.urlopen(OLLAMA + "/api/version"))["version"]  # nosemgrep
ENVINFO = {"cpu": os.cpu_count(), "mem": " ".join(_sh("free -h | sed -n 2p").split()[1:3]), "ollama": OLLAMA_VER,
           "models": [l for l in _sh("ollama list").splitlines()[1:] if l.strip()]}

sys.path.insert(0, "hosts")
import ollama_host as oh  # noqa: E402
_CACHE = {}
def tool(args):
    key = json.dumps(args, ensure_ascii=False, sort_keys=True)
    if key in _CACHE:
        return _CACHE[key]
    mcp = oh.MCP("server.py", dict(os.environ, CHAEKIJI_MODE=SMODE, PYTHONUTF8="1"))
    try:
        text, err = mcp.call("consult_request", args)
    finally:
        mcp.close()
    try:
        o = json.loads(text)
    except Exception:
        o = {"_raw": (text or "")[:300]}; err = True
    _CACHE[key] = (o, err)
    return o, err

def brief(o):
    av = o.get("availability") or {}
    return {"found": o.get("found"), "route": o.get("route"), "route_label": o.get("route_label"), "mode": o.get("mode"),
            "isbn13": (o.get("book") or {}).get("isbn13"), "title": (o.get("book") or {}).get("title"),
            "official_link": o.get("official_link"), "from_lib": o.get("from_lib"), "pickup": o.get("pickup"),
            "available_at": av.get("available_at"), "loaned_at": av.get("loaned_at"), "asof": av.get("asof"), "notice": o.get("notice")}

# ① 기준: 기대한 책의 정확한 제목으로 도구를 직접 부른다(모델 없이, 같은 받을 도서관·언어)
REF = {}
for no, cat, ask, pickup, lang, title, _ in CASES:
    if not title:
        continue
    o, err = tool({"utterance": title, "pickup": pickup, "lang": lang})
    REF[no] = {**brief(o), "q": title, "error": err}
    print(f"기준 {no}: 「{title}」 → {REF[no]['route_label']} · {REF[no]['isbn13']} · {REF[no]['asof']}", flush=True)
    time.sleep(3)

# ② 모델 실행: 문의 24건, 이 작업의 회차 하나
CALLS = OUT_DIR / f"ai_metrics_calls_{TAG}.ndjson"
ANS = OUT_DIR / f"ai_metrics_answers_{TAG}.ndjson"
RUNLOG = {}
for no, cat, ask, pickup, lang, title, _ in CASES:
    t0 = time.time()
    try:
        # 보안 검토(2026-11-09): 저장소 안의 고정된 파이썬 스크립트·명령을 인자 목록으로 실행하며 셸을 거치지 않음
        r = subprocess.run([sys.executable, "hosts/ollama_host.py", "--model", MODEL, "--ollama", OLLAMA, "--mode", SMODE,  # nosemgrep
                            "--pickup", pickup, "--lang", lang, "--ask", ask, "--log", str(CALLS), "--answers", str(ANS),
                            "--tools", "consult", "--timeout", "900", "--num-ctx", "8192"], capture_output=True, text=True,
                           encoding="utf-8", timeout=1500, env=dict(os.environ))
        out = (r.stdout or "")[-1500:] + ("\n" + (r.stderr or "")[-500:] if r.returncode else "")
    except subprocess.TimeoutExpired:
        out = "(시간 초과 25분: 답 없음으로 기록)"
    RUNLOG[no] = out
    dt = time.time() - t0
    print(f"\n━━ 문의 {no} ({dt:.0f}초)\n{out[-600:]}", flush=True)
    if dt < MIN_GAP:
        time.sleep(MIN_GAP - dt)
PS = _sh("ollama ps")

# ③ 채점
def rows(p):
    p = pathlib.Path(p)
    return [json.loads(l) for l in open(p, encoding="utf-8")] if p.exists() else []

def norm(s):
    return re.sub(r"[\W_]+", "", str(s or "")).lower()
def main_title(s):
    return norm(re.split(r"[:(\[=]", str(s or ""))[0])

LIB_ALIASES = {
    "꿈빛": ["kkumbit", "ggumbit", "kumbit"], "꿈여울": ["kkumyeoul", "ggumyeoul", "kumyeoul"], "도당": ["dodang", "道堂"],
    "동화": ["donghwa", "童话", "童話"], "별빛마루": ["byeolbitmaru", "byeolbit", "byulbit"], "북부": ["bukbu", "北部"],
    "상동": ["sangdong", "上洞", "上东", "上東"], "송내": ["songnae", "松内", "松內"], "수주": ["suju"],
    "심곡": ["simgok", "shimgok", "深谷"], "역곡": ["yeokgok", "yeokkok", "驿谷", "驛谷"], "역곡밝은": ["yeokgokbalgeun"],
    "오정": ["ojeong", "ojung"], "원미": ["wonmi", "远美", "遠美"], "책마루": ["chaekmaru", "chaegmaru"], "한울빛": ["hanulbit", "hanwoolbit"],
}
def has_lib(text, lib):
    t = re.sub(r"[\s\-]", "", (text or "").lower())
    return bool(lib) and (lib in (text or "") or any(a.lower() in t for a in LIB_ALIASES.get(lib, [])))

COUNTER = r"\s*(곳|개관|개 관|관|개 도서관|개의 도서관|libraries|library|locations|branches|places|sites|thư viện|nơi|địa điểm|chi nhánh|所|个|個|家|館|馆|か所|カ所|ヶ所|ケ所)"
def has_count(text, n):
    return n is not None and bool(re.search(rf"(?<!\d){n}{COUNTER}", text or "", re.I))

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
def has_date(text, asof):
    if not asof:
        return False
    y, m, d = asof.split("-"); m, d = int(m), int(d); mn = MONTHS[m - 1]
    pats = [rf"{y}\.\s*{m}\.\s*{d}(?!\d)", rf"{y}\.\s*{m:02d}\.\s*{d:02d}", rf"{y}-{m:02d}-{d:02d}", rf"{y}/{m:02d}/{d:02d}",
            rf"(?<!\d){d:02d}/{m:02d}/{y}", rf"(?<!\d){d}/{m}/{y}", rf"{y}\s*年\s*{m}\s*月\s*{d}\s*日", rf"ngày\s*{d}\s*tháng\s*{m}",
            rf"(?<!\d){d}\s*tháng\s*{m}(?!\d)", rf"{mn}\s+{d},?\s+{y}", rf"{d}\s+{mn},?\s+{y}", rf"{mn[:3]}\.?\s+{d},?\s+{y}"]
    return any(re.search(p, text or "", re.I) for p in pats)

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

def foreign_part(text):
    """한국어 원문 줄을 뺀 나머지(번역문). 한 줄에서 한글이 글자의 절반 이상이면 한국어 줄로 본다."""
    keep = []
    for line in (text or "").splitlines():
        letters = re.findall(r"[^\W\d_]", line)
        hangul = re.findall(r"[가-힣]", line)
        if letters and len(hangul) * 2 >= len(letters):
            continue
        keep.append(line)
    return "\n".join(keep)

ASKBACK = re.compile(r"[?？]|어느|어떤|알려\s*주|말씀해|확인해\s*주시|which|Which|cuốn nào|sách nào|哪|どの|どれ")

def facts(o, text):
    """도구 결과 o(그 답의 근거가 된 호출)의 사실이 답 text에 있는가. 해당 없는 항목은 None."""
    route = o.get("route")
    lib = o.get("from_lib") if route == "ill" else (o.get("pickup") if route == "visit" else None)
    n = len(o.get("available_at") or []) if route == "ill" else (len(o.get("loaned_at") or []) if route == "reserve"
                                                                  else (16 if route == "sea" else None))
    f = {"lib": has_lib(text, lib) if lib else None,
         "count": has_count(text, n) if n is not None else None,
         "date": has_date(text, o.get("asof")) if route not in ("check", "unknown") and o.get("asof") else None,
         "link": (o.get("official_link") in (text or "")) if o.get("official_link") else None}
    vals = [v for v in f.values() if v is not None]
    f["all"] = all(vals) if vals else None
    return f

calls = rows(CALLS); answers = rows(ANS)
S = []
for no, cat, ask, pickup, lang, title, what in CASES:
    cs = [c for c in calls if c.get("ask") == ask and c.get("tool") == "consult_request"]
    an = next((a for a in answers if a.get("ask") == ask), None)
    text = (an or {}).get("answer", "") or ""
    ok_calls = [c for c in cs if not c.get("error") and c.get("found")]
    last = ok_calls[-1] if ok_calls else (cs[-1] if cs else None)
    args = (last or {}).get("arguments") or {}
    res = None
    if last and not last.get("error"):
        if isinstance(last.get("metrics"), dict):
            res = {**last["metrics"], "found": last.get("found"), "route": last.get("route"), "route_label": last.get("route_label"),
                   "asof": last.get("asof"), "mode": last.get("mode")}
        else:                                           # 계측이 없으면 같은 인자로 도구를 다시 불러 확인(같은 작업 안이라 같은 자료)
            o, _ = tool({"utterance": args.get("utterance", ""), "pickup": args.get("pickup") or pickup, "lang": args.get("lang") or lang})
            res = brief(o)
    found = bool(res and res.get("found"))
    ref = REF.get(no) or {}
    row = {"no": no, "cat": cat, "lang": lang, "ask": ask, "pickup": pickup, "expect": title, "what": what,
           "called": bool(cs), "n_calls": len(cs), "utterance_arg": args.get("utterance"),
           "tool_found": found, "tool_route": (res or {}).get("route"), "tool_route_label": (res or {}).get("route_label"),
           "tool_isbn": (res or {}).get("isbn13"), "tool_title": (res or {}).get("title"),
           "seconds": round((an or {}).get("total_ms", 0) / 1000, 1), "answer": text, "protocol": (an or {}).get("protocol")}
    if title:
        ua = norm(args.get("utterance"))
        row["title_arg_ok"] = bool(ua) and main_title(title) in ua      # 모델이 한국어판 제목(본서명)을 넣어 넘겼나(도구의 느슨한 찾기와 따로)
        book_ok = found and ((res.get("isbn13") and res.get("isbn13") == ref.get("isbn13"))
                             or (main_title(res.get("title")) and main_title(res.get("title")) == main_title(title)))
        row.update({"book_ok": bool(book_ok),
                    "wrong_book": bool(found and not book_ok),
                    "not_found": bool(not found),
                    "infra": bool(res and res.get("route") == "check"),
                    "route_ok": (res.get("route") == ref.get("route")) if book_ok else None,
                    "asked": None})
    else:
        row.update({"book_ok": None, "wrong_book": None, "not_found": None, "infra": bool(res and res.get("route") == "check"),
                    "route_ok": None, "asked": (not found) and bool(ASKBACK.search(text)), "answered_some_book": found,
                    "asked_before_tool": (not cs) and bool(ASKBACK.search(text)), "title_arg_ok": None})
    if found and text.strip():
        row["facts"] = facts(res, text)
        row["facts_tr"] = facts(res, foreign_part(text)) if lang != "ko" else None
    else:
        row["facts"] = row["facts_tr"] = None
    row["lang_ok"] = lang_ok(text, lang) if (lang != "ko" and text.strip()) else (None if lang == "ko" else False)
    S.append(row)

OUT = OUT_DIR / f"ai_metrics_{TAG}.json"
OUT.write_text(json.dumps({"model": MODEL, "variant": VARIANT, "rep": REP, "run_id": RUN_ID, "commit": COMMIT, "server_mode": SMODE,
                           "finished": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "env": ENVINFO, "ollama_ps": PS,
                           "instrumented": INSTRUMENTED, "prompt_items": PROMPT_ITEMS, "prompt_sha": PROMPT_SHA, "ref": REF, "rows": S,
                           "runlog_tail": {str(k): v[-800:] for k, v in RUNLOG.items() if not any(r["no"] == k and r["answer"].strip() for r in S)}},
                          ensure_ascii=False, indent=1), encoding="utf-8")
ok = sum(1 for r in S if r.get("book_ok")); n = sum(1 for r in S if r.get("book_ok") is not None)
print(f"\n책 식별 {ok}/{n} · 되물음 {sum(1 for r in S if r.get('asked'))}/{sum(1 for r in S if r.get('asked') is not None)} · 기록 {OUT}")
