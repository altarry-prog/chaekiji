#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPT-OSS 구동 실측: 공개 모델 2종 노트북(server/lab/colab_model2.ipynb)과 같은 문의 5건을 오픈AI의 공개 모델 GPT-OSS(Ollama)로 돌리고 기록표를 만든다.
(run_gpt.py의 틀을 그대로 쓰고, 모델 부르는 곳만 main의 server/hosts/ollama_host.py 그대로 — 깃허브 모델이 2026. 7. 30. 종료되어 GPT 계열은 공개 모델로 잰다)

같은 것: 저장소 main의 서버(server.py)·지시문(프롬프트 consult)·문의 5건·받을 도서관·언어, 모델에 보이는 도구는 consult_request 하나,
         호스트 코드(ollama_host.py의 대화·고정·멈춤 규칙)와 기록 형식.
다른 것: 모델(gpt-oss:20b, 받는 크기 약 14GB)과 문맥 길이(8192). 그리고 모델 없이 도구를 직접 부른 「기준 판정」을 함께 적어
         모델마다 판정이 기준과 같은지 본다(판정은 도구가 정하므로 같아야 정상).
인증키·결제 없음. 기록은 실제로 돌린 결과만 담고, 실패도 그대로 적는다."""
import os, sys, json, time, datetime, pathlib, subprocess

KST = datetime.timezone(datetime.timedelta(hours=9))
WORK = pathlib.Path(os.environ.get("WORK_DIR", "/content"))
HERE = pathlib.Path(__file__).resolve().parent
MODELS = [m.strip() for m in os.environ.get("OSS_MODELS", "gpt-oss:20b").split(",") if m.strip()]

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
CALLS = OUT_DIR / f"gptoss_host_log_actions_{STAMP}.ndjson"
ANSWERS = OUT_DIR / f"gptoss_host_answers_actions_{STAMP}.ndjson"

# ②-1 실행 환경: Ollama 판·모델 크기·메모리(기록표에 그대로)
import urllib.request
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
def _sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()
OLLAMA_VER = json.load(urllib.request.urlopen(OLLAMA + "/api/version"))["version"]
ENVINFO = [f"CPU {os.cpu_count()}코어 · GPU 없음", "메모리: " + " ".join(_sh("free -h | sed -n 2p").split()[1:3]) + "(전체·사용)",
           f"Ollama {OLLAMA_VER}", "모델: " + " · ".join(l for l in _sh("ollama list").splitlines()[1:] if l.strip())]
print("실행 환경:", ENVINFO, flush=True)

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

# ④ GPT-OSS로 같은 문의 5건(호스트는 main의 ollama_host.py 그대로 — 엑사원·라마 실측과 같은 코드)
env = dict(os.environ)
RUNLOG, PS = {}, ""
for m in MODELS:
    for ask, pickup, lang in ASKS:
        t0 = time.time()
        try:
            r = subprocess.run([sys.executable, "hosts/ollama_host.py", "--model", m, "--ollama", OLLAMA, "--mode", "auto",
                                "--pickup", pickup, "--lang", lang, "--ask", ask, "--log", str(CALLS), "--answers", str(ANSWERS),
                                "--tools", "consult", "--timeout", "1800", "--num-ctx", "8192"], capture_output=True, text=True,
                               encoding="utf-8", timeout=2400, env=env)
            out = (r.stdout or "")[-1800:] + ("\n" + (r.stderr or "")[-600:] if r.returncode else "")
        except subprocess.TimeoutExpired:
            out = "(시간 초과 40분: 이 문의는 답 없음으로 기록하고 다음 문의로 넘어갑니다)"
        RUNLOG[(m, ask)] = out
        print(f"\n━━ {m} · 「{ask}」 ({time.time() - t0:.0f}초)\n{out}", flush=True)

    PS = _sh("ollama ps"); print(PS, flush=True)

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
L = [f"# GPT-OSS 구동 실측 기록 — 깃허브 액션(CPU)·Ollama ({now} KST)", "",
     "- 실행 환경: GitHub Actions(ubuntu-latest, 사람 손 없음) · " + " · ".join(ENVINFO) + " · 인증키·결제 없음",
     f"- 실행 기록(공개): {os.environ.get('RUN_URL', '—')}",
     f"- 책이지: 저장소 main 커밋 `{COMMIT}` · 같은 서버(`server.py`, 모드 auto) · 같은 지시문(프롬프트 `consult`) · "
     f"공개 모델 2종 노트북과 같은 문의 {len(ASKS)}건 · 모델에 보이는 도구는 `consult_request` 하나 · 호스트는 `server/hosts/ollama_host.py` 그대로(엑사원·라마 실측과 같은 코드), 문맥 길이 8192",
     "- 실행 직후 모델 상태(ollama ps): " + (" / ".join(l.strip() for l in PS.splitlines()) or "(정보 없음)"),
     "- 기준 판정: 모델 없이 같은 도구를 같은 값으로 직접 부른 결과. 판정은 도구가 정하므로 모델의 판정은 기준과 같아야 정상",
     f"- 원 기록: `{CALLS.name}`(도구 호출) · `{ANSWERS.name}`(최종 답) — 실제로 돌린 결과이며 사람이 고치지 않았다", "",
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
      "GPT-OSS는 오픈AI가 공개한 내려받는 모델(행정안전부 AI 공통기반 목록, 참가 안내서 10. 21. 변경판)이며, 이 기록은 그래픽카드 없는 CPU 서버라 시간이 길다. 판정은 도구가 정하므로 같아야 정상이고, 시간은 환경 차이를 그대로 적는다."]
REC = OUT_DIR / f"model_gptoss_record_actions_{STAMP}.md"
REC.write_text("\n".join(L), encoding="utf-8")
print("\n".join(L[:16]))
print("\n기록 파일:", REC)
