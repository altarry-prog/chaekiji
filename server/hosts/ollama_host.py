#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책이지 공개 모델 호스트 — Ollama(로컬 공개 모델)로 책이지 MCP 서버의 도구를 돌린다. 표준 라이브러리만 쓴다.

왜 있나: 「모델을 바꿔도 같은 도구가 돈다」를 입증하려면 상용 모델(클로드 데스크톱) 말고도
공통기반 지원 계열의 공개 모델(엑사원·라마·젬마 …)에서 같은 서버를 같은 지시문으로 돌려 봐야 한다.
이 스크립트가 그 두 번째 호스트다. 서버는 손대지 않는다 — 클로드 데스크톱과 똑같이 `python server.py`를 붙인다.

준비: Ollama 설치(https://ollama.com) → 모델 받기 예) ollama pull exaone3.5:2.4b  또는  ollama pull llama3.2:3b
실행: python hosts/ollama_host.py --model exaone3.5:2.4b --ask "나미야 잡화점의 기적 빌리고 싶어요"
      python hosts/ollama_host.py --model llama3.2:3b          (대화형)
기록: --log lab/out/host_log.ndjson 에 호출된 도구·인자·소요 시간·판정 갈래가 한 줄씩 남는다(구동안내서·2종 실측 기록 재료).
      --answers lab/out/host_answers.ndjson 에는 질문마다 모델의 최종 답이 남는다(10/16 — 코랩 2종 구동 노트북이 기록표를 만든다).

도구 호출 방식은 둘 다 지원한다.
  native — Ollama의 도구 호출(tool_calls) 기능을 쓴다(라마 3.1/3.2 등 지원 모델).
  json   — 모델이 도구 호출을 지원하지 않으면, 지시문으로 「JSON 한 덩어리로만 답하라」고 시켜 같은 일을 한다(엑사원·젬마 등).
  --protocol auto(기본)는 native를 먼저 시도하고 Ollama가 거부하면 json으로 넘어간다."""
import sys, os, json, time, argparse, subprocess, urllib.request, urllib.error, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MAX_STEPS = 6
HARD_STEPS = MAX_STEPS + 2      # [10/18] 한도 안내 뒤에도 도구만 부르면 여기서 멈춘다(실측에서 같은 오류를 30분 되풀이)
SAME_ERROR_STOP = 3             # [10/18] 같은 도구·같은 인자의 오류가 이만큼 되풀이되면 멈춘다

try:
    sys.stdout.reconfigure(encoding="utf-8")            # 윈도우 콘솔 한글
except Exception:
    pass

# ── MCP 클라이언트(stdio JSON-RPC) — 클로드 데스크톱이 하는 일을 그대로 ───────────────────
class MCP:
    def __init__(self, server, env):
        self.p = subprocess.Popen([sys.executable, str(server)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env)
        self.n = 0
        self.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                "clientInfo": {"name": "chaekiji-ollama-host", "version": "0.3.4"}})
        self.notify("notifications/initialized")
    def rpc(self, method, params=None):
        self.n += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}, ensure_ascii=False) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError("MCP 서버가 응답 없이 끝났습니다: " + self.p.stderr.read()[-800:])
        msg = json.loads(line)
        if "error" in msg: raise RuntimeError(f"MCP 오류: {msg['error']}")
        return msg["result"]
    def notify(self, method):
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n"); self.p.stdin.flush()
    def tools(self): return self.rpc("tools/list")["tools"]
    def prompt(self, name, args):
        r = self.rpc("prompts/get", {"name": name, "arguments": args})
        return "\n".join(m["content"]["text"] for m in r["messages"] if m["content"].get("type") == "text")
    def call(self, name, args):
        r = self.rpc("tools/call", {"name": name, "arguments": args})
        text = "\n".join(c.get("text", "") for c in r.get("content", []))
        return text, bool(r.get("isError"))
    def close(self):
        try: self.p.stdin.close(); self.p.wait(timeout=5)
        except Exception: pass

# ── Ollama ──────────────────────────────────────────────────────────────────────────────
def ollama_chat(base, model, messages, tools=None, num_ctx=4096, timeout=600):
    body = {"model": model, "messages": messages, "stream": False, "options": {"temperature": 0, "num_ctx": num_ctx}}
    if tools: body["tools"] = tools
    req = urllib.request.Request(base.rstrip("/") + "/api/chat", data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise OllamaError(e.code, detail)
    except urllib.error.URLError as e:
        raise SystemExit(f"Ollama에 연결할 수 없습니다({base}). 설치·실행 여부를 확인하세요: {e.reason}")
    out["_ms"] = round((time.perf_counter() - t0) * 1000)
    return out

class OllamaError(Exception):
    def __init__(self, code, detail): super().__init__(detail); self.code, self.detail = code, detail

def to_ollama_tools(mcp_tools):
    return [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                               "parameters": t.get("inputSchema", {"type": "object", "properties": {}})}}
            for t in mcp_tools]

def catalog_text(mcp_tools):
    lines = []
    for t in mcp_tools:
        props = t.get("inputSchema", {}).get("properties", {})
        req = set(t.get("inputSchema", {}).get("required", []))
        args = ", ".join(f"{k}{'' if k in req else '?'}: {v.get('type', 'string')}" for k, v in props.items())
        lines.append(f"- {t['name']}({args}) — {t.get('description', '')}")
    return "\n".join(lines)

JSON_RULES = """
답하는 방법(중요): 반드시 JSON 한 덩어리로만 답합니다. 설명·인사·코드 울타리를 붙이지 않습니다.
도구를 부를 때:  {"tool": "도구이름", "arguments": {"인자": "값"}}
최종 답을 줄 때: {"answer": "사서에게 줄 답 전체(판정 한 줄 · 이용자 안내문 · 접수 메모)"}
도구 결과는 [도구 결과] 로 시작하는 메시지로 돌아옵니다. 결과를 받기 전에는 최종 답을 쓰지 않습니다.

쓸 수 있는 도구:
"""

def extract_json(text):
    """모델 답에서 첫 JSON 객체를 꺼낸다(코드 울타리·앞뒤 말 허용). 없으면 None."""
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"): s = s[4:]
    dec = json.JSONDecoder()
    for i, ch in enumerate(s):
        if ch == "{":
            try:
                obj, _ = dec.raw_decode(s[i:])
                if isinstance(obj, dict): return obj
            except json.JSONDecodeError:
                continue
    return None

# ── 대화 1회(도구 호출 포함) ───────────────────────────────────────────────────────────
def run_turn(a, mcp, tools, system, user_text, state, logf):
    protocol = state["protocol"]
    tool_names = {t["name"] for t in tools}
    messages = [{"role": "system", "content": system + (JSON_RULES + catalog_text(tools) if protocol == "json" else "")},
                {"role": "user", "content": user_text}]
    step, errs, last_err = 0, {}, ""
    while True:
        try:
            resp = ollama_chat(a.ollama, a.model, messages, tools=(to_ollama_tools(tools) if protocol == "native" else None),
                               num_ctx=a.num_ctx, timeout=a.timeout)
        except OllamaError as e:
            if protocol == "native" and e.code == 400 and "tool" in e.detail.lower():
                print(f"※ {a.model}은(는) Ollama 도구 호출을 지원하지 않아 json 방식으로 넘어갑니다.")
                state["protocol"] = protocol = "json"
                messages[0]["content"] = system + JSON_RULES + catalog_text(tools)
                continue
            raise SystemExit(f"Ollama 오류 {e.code}: {e.detail[:300]}")
        msg = resp.get("message", {})
        calls = []
        if protocol == "native" and msg.get("tool_calls"):
            calls = [(tc["function"]["name"], tc["function"].get("arguments") or {}) for tc in msg["tool_calls"]]
        elif protocol == "json":
            obj = extract_json(msg.get("content", "") or "")
            if obj and obj.get("tool"):
                calls = [(obj["tool"], obj.get("arguments") or {})]
            elif obj and "answer" in obj:
                return str(obj["answer"]), resp["_ms"]
        if not calls:
            return (msg.get("content") or "").strip(), resp["_ms"]
        messages.append(msg if protocol == "native" else {"role": "assistant", "content": msg.get("content", "")})
        for name, args in calls:
            step += 1
            if isinstance(args, str):
                try: args = json.loads(args)
                except json.JSONDecodeError: args = {"utterance": args}
            print(f"▶ 도구 호출 {step}: {name} {json.dumps(args, ensure_ascii=False)}  (모델 {resp['_ms']} ms)")
            ms, o = 0, None
            if name not in tool_names:
                result, err = json.dumps({"error": f"없는 도구: {name}", "available": sorted(tool_names)}, ensure_ascii=False), True
            else:
                t0 = time.perf_counter(); result, err = mcp.call(name, args); ms = round((time.perf_counter() - t0) * 1000)
                brief = ""
                try:
                    o = json.loads(result)
                    brief = " · ".join(f"{k}={o[k]}" for k in ("route_label", "found", "mode") if k in o)
                except Exception:
                    pass
                print(f"◀ 결과 {'(오류) ' if err else ''}{ms} ms {brief}")
            if logf:
                row = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "model": a.model,
                       "protocol": protocol, "step": step, "tool": name, "arguments": args,
                       "error": err, "result_chars": len(result), "model_ms": resp["_ms"], "tool_ms": ms, "ask": user_text}
                if isinstance(o, dict):                   # 판정 결과의 요점(갈래·데이터 출처·조회일) — 기록표용
                    row.update({k: o[k] for k in ("found", "route", "route_label", "mode") if k in o})
                    if isinstance(o.get("availability"), dict): row["asof"] = o["availability"].get("asof")
                logf.write(json.dumps(row, ensure_ascii=False) + "\n")
                logf.flush()
            if protocol == "native":
                messages.append({"role": "tool", "content": result})
            else:
                messages.append({"role": "user", "content": "[도구 결과] " + name + "\n" + result})
            if err:
                key = name + json.dumps(args, ensure_ascii=False, sort_keys=True)
                errs[key] = errs.get(key, 0) + 1
                last_err = result
        if errs and max(errs.values()) >= SAME_ERROR_STOP:     # [10/18] 무한 반복 막기 — 멈춘 사실을 답으로 그대로 남긴다
            return (f"(멈춤) 같은 도구 오류가 {SAME_ERROR_STOP}번 되풀이되어 멈췄습니다. 마지막 오류: {last_err[:200]}", resp["_ms"])
        if step >= HARD_STEPS:
            return (f"(멈춤) 도구 호출이 {HARD_STEPS}번에 닿도록 최종 답이 없어 멈췄습니다.", resp["_ms"])
        if step >= MAX_STEPS:
            messages.append({"role": "user", "content": "도구 호출 한도에 닿았습니다. 지금까지의 결과로 최종 답을 주세요." +
                             (' {"answer": "..."} 형식으로만.' if protocol == "json" else "")})

def main():
    ap = argparse.ArgumentParser(description="책이지 MCP 서버 × Ollama 공개 모델 호스트")
    ap.add_argument("--model", default="exaone3.5:2.4b", help="Ollama 모델 이름(예: exaone3.5:2.4b, llama3.2:3b, gemma3:4b)")
    ap.add_argument("--ollama", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    ap.add_argument("--server", default=str(ROOT / "server.py"))
    ap.add_argument("--mode", default=os.environ.get("CHAEKIJI_MODE", "auto"), help="서버 데이터 원천: auto|demo|relay|live")
    ap.add_argument("--relay", default=os.environ.get("CHAEKIJI_RELAY", ""), help="중계 주소(비우면 설정 relay_url)")
    ap.add_argument("--pickup", default="", help="받을 도서관(기본: 설정 home_library)")
    ap.add_argument("--lang", default="ko")
    ap.add_argument("--ask", default="", help="한 문장만 묻고 끝낸다(없으면 대화형)")
    ap.add_argument("--protocol", default="auto", choices=["auto", "native", "json"])
    ap.add_argument("--tools", default="all", choices=["all", "consult"],
                    help="모델에 보여 줄 도구 — all(11종) / consult(상담 묶음 consult_request 하나만, 작은 모델이 다른 도구로 새지 않게)")
    ap.add_argument("--log", default="", help="호출 기록 JSONL 경로(예: lab/out/host_log.ndjson)")
    ap.add_argument("--answers", default="", help="최종 답 기록 JSONL 경로(예: lab/out/host_answers.ndjson)")
    ap.add_argument("--num-ctx", type=int, default=4096)
    ap.add_argument("--timeout", type=int, default=600, help="모델 응답 대기(초) — CPU에서는 길게")
    a = ap.parse_args()

    env = dict(os.environ, CHAEKIJI_MODE=a.mode, PYTHONUTF8="1")
    if a.relay: env["CHAEKIJI_RELAY"] = a.relay
    mcp = MCP(a.server, env)
    tools = mcp.tools()
    if a.tools == "consult":                              # [10/18] 실측에서 작은 모델이 찾기 도구만 부르고 추측으로 답함 → 상담 묶음 하나만
        tools = [t for t in tools if t["name"] == "consult_request"]
    system = mcp.prompt("consult", {k: v for k, v in {"pickup": a.pickup, "lang": a.lang}.items() if v})
    state = {"protocol": "native" if a.protocol in ("auto", "native") else "json"}
    logf = open(a.log, "a", encoding="utf-8") if a.log else None
    print(f"[책이지 호스트] 모델 {a.model} · Ollama {a.ollama} · 서버 {a.mode} 모드 · 도구 {len(tools)}종 · 지시문 {len(system)}자")
    try:
        if a.ask:
            t0 = time.perf_counter()
            answer, ms = run_turn(a, mcp, tools, system, a.ask, state, logf)
            print("\n" + answer + f"\n\n(방식 {state['protocol']} · 마지막 응답 {ms} ms)")
            if a.answers:                                 # [10/16] 질문마다 최종 답 — 코랩 2종 구동 노트북이 기록표를 만든다
                with open(a.answers, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": datetime.datetime.now().isoformat(timespec="seconds"), "model": a.model,
                                        "protocol": state["protocol"], "ask": a.ask, "pickup": a.pickup, "lang": a.lang,
                                        "answer": answer, "last_model_ms": ms,
                                        "total_ms": round((time.perf_counter() - t0) * 1000)}, ensure_ascii=False) + "\n")
        else:
            print("이용자의 말을 적고 Enter. 빈 줄이면 끝.")
            while True:
                try: q = input("\n사서> ").strip()
                except EOFError: break
                if not q: break
                answer, ms = run_turn(a, mcp, tools, system, q, state, logf)
                print("\n" + answer + f"\n(방식 {state['protocol']} · {ms} ms)")
    finally:
        if logf: logf.close()
        mcp.close()

if __name__ == "__main__":
    main()
