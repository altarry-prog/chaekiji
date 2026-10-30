#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPT 모델 구동 실측: 공개 모델 2종 노트북(server/lab/colab_model2.ipynb)과 같은 문의 5건을 GPT 모델로 돌리고 기록표를 만든다.

같은 것: 저장소 main의 서버(server.py)·지시문(프롬프트 consult)·문의 5건·받을 도서관·언어, 모델에 보이는 도구는 consult_request 하나,
         호스트 코드(ollama_host.py의 대화·고정·멈춤 규칙)와 기록 형식.
다른 것: 모델을 부르는 곳(깃허브 모델, 무료 시험용). 그리고 모델 없이 도구를 직접 부른 「기준 판정」을 함께 적어
         모델마다 판정이 기준과 같은지 본다(판정은 도구가 정하므로 같아야 정상).
인증키·결제 없음(깃허브 액션 기본 토큰). 기록은 실제로 돌린 결과만 담고, 실패도 그대로 적는다."""
import os, sys, json, time, datetime, pathlib, subprocess

KST = datetime.timezone(datetime.timedelta(hours=9))
WORK = pathlib.Path(os.environ.get("WORK_DIR", "/content"))
HERE = pathlib.Path(__file__).resolve().parent
ENDPOINT = os.environ.get("GH_MODELS_URL", "https://models.github.ai/inference/chat/completions")
MODELS = [m.strip() for m in os.environ.get("GPT_MODELS", "openai/gpt-4.1-mini,openai/gpt-5-mini").split(",") if m.strip()]
GAP = int(os.environ.get("GPT_GAP_SEC", "8"))            # 문의 사이 쉬는 시간(무료 시험용의 분당 한도)

# ① 저장소 main 받기(노트북 ① 칸과 같음)
WORK.mkdir(parents=True, exist_ok=True)
os.chdir(WORK)
if not (WORK / "chaekiji").exists():
    subprocess.run(["git", "clone", "--depth", "1", "https://github.com/altarry-prog/chaekiji.git"], check=True)
os.chdir(WORK / "chaekiji" / "server")
subprocess.run([sys.executable, "-m", "pip", "-q", "install", "pyyaml"], check=True)
COMMIT = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
print("저장소 준비 완료 · 커밋", COMMIT, "· 모델", MODELS, flush=True)

# ② 같은 문의 5건(노트북 ④ 칸의 ASKS 그대로)
ASKS = [
    ("나미야 잡화점의 기적 빌리고 싶어요, 상동에서 받을게요", "상동", "ko"),
    ("소년이 온다 있나요? 꿈빛도서관에서 받을게요", "꿈빛", "ko"),
    ("채식주의자 상호대차 되나요?", "상동", "ko"),
    ("불편한 편의점 원미도서관으로 가져다줄 수 있어요?", "원미", "ko"),
    ("Tôi muốn mượn cuốn 나미야 잡화점의 기적", "상동", "vi"),
]
OUT_DIR = pathlib.Path("lab/out"); OUT_DIR.mkdir(parents=True, exist_ok=True)
STAMP = datetime.datetime.now(KST).strftime("%Y-%m-%d_%H%M")
CALLS = OUT_DIR / f"gpt_host_log_actions_{STAMP}.ndjson"
ANSWERS = OUT_DIR / f"gpt_host_answers_actions_{STAMP}.ndjson"

# ②-1 연결 점검: 모델마다 짧은 요청 한 번. 상태 코드와 오류 문구(토큰 가림)를 기록에 남긴다(10. 30. 첫 실행이 답 없이 끝나 까닭을 보려고)
import urllib.request, urllib.error
TOKEN = os.environ.get("GITHUB_TOKEN", "")
PROBE = {}
for m in MODELS:
    body = {"model": m, "messages": [{"role": "user", "content": "한 단어로 답하세요: 안녕"}]}
    if not m.split("/")[-1].startswith(("gpt-5", "o1", "o3", "o4")): body["temperature"] = 0
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
                                          "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            o = json.load(r); PROBE[m] = f"200 · 답: {(((o.get('choices') or [{}])[0].get('message') or {}).get('content') or '(도구 호출 또는 빈 답)')[:40]!r}"
    except urllib.error.HTTPError as e:
        PROBE[m] = f"{e.code} · {e.read().decode('utf-8', 'replace')[:300].replace(TOKEN or '§', '***')}"
    except Exception as e:
        PROBE[m] = f"연결 실패 · {type(e).__name__}: {str(e)[:200]}"
    print(f"연결 점검 · {m}: {PROBE[m]}", flush=True)
    time.sleep(GAP)

# ③ 기준 판정: 모델 없이 도구를 직접 부른다(같은 모드·같은 받을 도서관·같은 언어). 중계 캐시도 먼저 데워 모델 실행과 같은 자료를 쓰게 한다
sys.path.insert(0, "hosts")
import ollama_host as oh                                  # noqa: E402
REF = {}
mcp = oh.MCP("server.py", dict(os.environ, CHAEKIJI_MODE="auto", PYTHONUTF8="1"))
for ask, pickup, lang in ASKS:
    text, err = mcp.call("consult_request", {"utterance": ask, "pickup": pickup, "lang": lang})
    try: o = json.loads(text)
    except Exception: o = {}
    REF[ask] = {"route": o.get("route"), "route_label": o.get("route_label", "—"), "error": err,
                "asof": (o.get("availability") or {}).get("asof", "—") if isinstance(o.get("availability"), dict) else "—",
                "mode": o.get("mode", "—")}
    print(f"기준 · 「{ask}」 → {REF[ask]['route_label']} ({REF[ask]['mode']} · {REF[ask]['asof']})", flush=True)
mcp.close()

# ④ GPT 모델로 같은 문의 5건(호스트는 main의 ollama_host.py, 모델 부르는 함수만 깃허브 모델로)
env = dict(os.environ, CHAEKIJI_SERVER_DIR=str(WORK / "chaekiji" / "server"))
RUNLOG = {}
for m in MODELS:
    for ask, pickup, lang in ASKS:
        t0 = time.time()
        try:
            r = subprocess.run([sys.executable, str(HERE / "gpt_host.py"), "--model", m, "--ollama", ENDPOINT, "--mode", "auto",
                                "--pickup", pickup, "--lang", lang, "--ask", ask, "--log", str(CALLS), "--answers", str(ANSWERS),
                                "--tools", "consult", "--timeout", "300"], capture_output=True, text=True, encoding="utf-8",
                               timeout=900, env=env)
            out = (r.stdout or "")[-1800:] + ("\n" + (r.stderr or "")[-600:] if r.returncode else "")
        except subprocess.TimeoutExpired:
            out = "(시간 초과 15분: 이 문의는 답 없음으로 기록하고 다음 문의로 넘어갑니다)"
        RUNLOG[(m, ask)] = out.replace(os.environ.get('GITHUB_TOKEN') or '§', '***')
        print(f"\n━━ {m} · 「{ask}」 ({time.time() - t0:.0f}초)\n{out}", flush=True)
        time.sleep(GAP)

# ⑤ 기록표(노트북 ⑤ 칸의 기준·형식 그대로, 「기준 판정과 같음」 열을 더함)
def _rows(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")] if pathlib.Path(p).exists() else []
calls, answers = _rows(CALLS), _rows(ANSWERS)
KEY = {"visit": "바로 이용", "ill": "관내 상호대차", "reserve": "예약", "sea": "책바다", "unknown": "미확정", "check": "소장 확인 불가"}
def summary(model, ask):
    cs = [c for c in calls if c["model"] == model and c.get("ask") == ask]
    an = next((a for a in answers if a["model"] == model and a["ask"] == ask), None)
    consult = [c for c in cs if c["tool"] == "consult_request" and not c["error"]]
    route = next((c.get("route") for c in reversed(cs) if c.get("route")), None)
    text = (an or {}).get("answer", "")
    return {"model": model, "ask": ask, "tools": " → ".join(c["tool"] for c in cs) or "(도구 호출 없음)",
            "route": route, "route_label": next((c.get("route_label") for c in reversed(cs) if c.get("route_label")), "—"),
            "asof": next((c.get("asof") for c in reversed(cs) if c.get("asof")), "—"),
            "data_mode": next((c.get("mode") for c in reversed(cs) if c.get("mode")), "—"),
            "protocol": (an or {}).get("protocol") or (cs[-1]["protocol"] if cs else "—"),
            "seconds": round((an or {}).get("total_ms", 0) / 1000, 1), "ok": bool(consult) and bool(text.strip()),
            "relayed": bool(route) and KEY.get(route, "§") in text, "answer": text,
            "same_ref": bool(route) and route == REF[ask]["route"],
            "no_tool": (not consult) and bool(text.strip()) and not text.startswith("(멈춤)")}
S = [summary(m, a[0]) for m in MODELS for a in ASKS]
now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
L = [f"# GPT 모델 구동 실측 기록 — 깃허브 액션·깃허브 모델 ({now} KST)", "",
     "- 실행 환경: GitHub Actions(ubuntu-latest, 사람 손 없음) · 모델 호출: GitHub Models(models.github.ai, 무료 시험용) · "
     "인증은 깃허브 액션 기본 토큰(권한 models: read), 인증키·결제 없음",
     f"- 실행 기록(공개): {os.environ.get('RUN_URL', '—')}",
     f"- 책이지: 저장소 main 커밋 `{COMMIT}` · 같은 서버(`server.py`, 모드 auto) · 같은 지시문(프롬프트 `consult`) · "
     f"공개 모델 2종 노트북과 같은 문의 {len(ASKS)}건 · 모델에 보이는 도구는 `consult_request` 하나 · 호스트는 `server/hosts/ollama_host.py` 그대로(모델 부르는 함수만 깃허브 모델로, `tools/model2/gpt_host.py`)",
     "- 기준 판정: 모델 없이 같은 도구를 같은 값으로 직접 부른 결과. 판정은 도구가 정하므로 모델의 판정은 기준과 같아야 정상",
     f"- 원 기록: `{CALLS.name}`(도구 호출) · `{ANSWERS.name}`(최종 답) — 실제로 돌린 결과이며 사람이 고치지 않았다", "",
     "## 연결 점검(모델마다 짧은 요청 한 번)", ""] + [f"- {m}: {PROBE[m]}" for m in MODELS] + ["",
     "## 한눈에", "", "| 모델 | 방식 | 성공 | 기준 판정과 같음 | 판정을 답에 옮김 | 도구 없이 답함 | 평균 시간 |", "|---|---|---|---|---|---|---|"]
for m in MODELS:
    ss = [s for s in S if s["model"] == m]
    proto = ", ".join(sorted({s["protocol"] for s in ss}))
    avg = sum(s["seconds"] for s in ss) / max(len(ss), 1)
    L.append(f"| {m} | {proto} | {sum(s['ok'] for s in ss)}/{len(ss)} | {sum(s['same_ref'] for s in ss)}/{len(ss)} | "
             f"{sum(s['relayed'] for s in ss)}/{len(ss)} | {sum(s['no_tool'] for s in ss)}/{len(ss)} | {avg:.1f}초 |")
L += ["", "성공 = 상담 도구가 오류 없이 불렸고 최종 답이 있음 · 기준 판정과 같음 = 모델이 부른 도구의 판정 갈래가 기준 판정과 같음 · "
      "판정을 답에 옮김 = 갈래 이름이 모델의 답에 들어 있음 · 도구 없이 답함 = 도구 결과 없이 모델이 스스로 쓴 답(창구에서 쓰면 안 됨) · "
      "(멈춤) = 같은 오류가 되풀이되거나 호출 한도에 닿아 호스트가 멈춘 문의", ""]
for i, (ask, pickup, lang) in enumerate(ASKS, 1):
    ref = REF[ask]
    L += [f"## 문의 {i}. {ask}", "", f"받을 도서관 {pickup} · 언어 {lang} · 기준 판정 **{ref['route_label']}**({ref['mode']} · {ref['asof']})", "",
          "| 모델 | 부른 도구 | 판정 | 기준과 같음 | 자료 | 시간 |", "|---|---|---|---|---|---|"]
    for s in [s for s in S if s["ask"] == ask]:
        L.append(f"| {s['model']} | {s['tools']} | {s['route_label']} | {'같음' if s['same_ref'] else '다름'} | {s['data_mode']} · {s['asof']} | {s['seconds']}초 |")
    for s in [s for s in S if s["ask"] == ask]:
        body = s["answer"].strip().replace("\n", "<br>") or "(답 없음)"
        L += ["", f"<details><summary>{s['model']}의 답 원문</summary>", "", body, "", "</details>"]
        if not s["ok"]:
            tail = (RUNLOG.get((s["model"], ask)) or "").strip()[-900:]
            L += ["", f"<details><summary>{s['model']} 호스트 출력(끝부분, 실패 까닭)</summary>", "", "```", tail or "(출력 없음)", "```", "", "</details>"]
    L.append("")
L += ["---", "대출 상태는 정보나루 조회일 전일 기준이며, 이 기록의 어떤 상담도 실제 접수로 이어지지 않았다. "
      "깃허브 모델은 무료 시험용(분당·하루 호출 한도 있음)이라 운영 경로가 아니라 「GPT 계열에서도 같은 도구가 돈다」는 실측용이다."]
REC = OUT_DIR / f"model_gpt_record_actions_{STAMP}.md"
REC.write_text("\n".join(L), encoding="utf-8")
print("\n".join(L[:16]))
print("\n기록 파일:", REC)
