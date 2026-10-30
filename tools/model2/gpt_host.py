#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책이지 MCP 서버 × GPT(오픈AI 모델) 호스트: 깃허브 모델(GitHub Models, 무료 시험용)로 부른다.

공개 모델 호스트(main의 server/hosts/ollama_host.py)를 그대로 불러 쓰고, 모델을 부르는 함수 하나(ollama_chat)만
깃허브 모델 주소로 바꾼다. 그래서 지시문(프롬프트 consult), 모델에 보이는 도구(consult_request 하나),
수령관·언어 고정, 멈춤 규칙, 기록 형식(--log·--answers)이 공개 모델 실측과 같다.

인증: 깃허브 액션의 기본 토큰(GITHUB_TOKEN, 워크플로 권한 models: read). 인증키·결제 없음. 토큰 값은 출력·기록하지 않는다.
사용: CHAEKIJI_SERVER_DIR=/content/chaekiji/server python3 gpt_host.py --model openai/gpt-4.1-mini \
        --ollama https://models.github.ai/inference/chat/completions --mode auto --pickup 상동 --lang ko --ask "…" --tools consult
      (인자는 ollama_host.py와 같다. --ollama 자리에 깃허브 모델 주소를 넣는다)"""
import sys, os, json, time, urllib.request, urllib.error
from pathlib import Path

SERVER_DIR = Path(os.environ.get("CHAEKIJI_SERVER_DIR", "/content/chaekiji/server"))
sys.path.insert(0, str(SERVER_DIR / "hosts"))
import ollama_host as oh                                  # noqa: E402  (main의 공개 모델 호스트 그대로)

TOKEN = os.environ.get("GITHUB_TOKEN", "")
REASONING = ("gpt-5", "o1", "o3", "o4")                  # 이 계열은 temperature를 바꿀 수 없다(기본값만)

def _args(v):
    if isinstance(v, dict): return v
    try: return json.loads(v or "{}")
    except json.JSONDecodeError: return {"utterance": str(v)}

def to_openai(messages):
    """공개 모델 호스트가 쌓은 대화(Ollama 모양)를 오픈AI 모양으로. 도구 결과에는 앞 호출의 id를 차례로 붙인다."""
    out, pending = [], []
    for m in messages:
        role = m.get("role")
        if role == "assistant" and m.get("tool_calls"):
            tcs = [{"id": tc.get("id") or f"call_{len(out)}_{i}", "type": "function",
                    "function": {"name": tc["function"]["name"],
                                 "arguments": json.dumps(_args(tc["function"].get("arguments")), ensure_ascii=False)}}
                   for i, tc in enumerate(m["tool_calls"])]
            pending = [t["id"] for t in tcs]
            out.append({"role": "assistant", "content": m.get("content") or None, "tool_calls": tcs})
        elif role == "tool":
            out.append({"role": "tool", "tool_call_id": pending.pop(0) if pending else "call_unknown", "content": m.get("content", "")})
        else:
            out.append({"role": role, "content": m.get("content", "")})
    return out

def gh_chat(base, model, messages, tools=None, num_ctx=4096, timeout=600):
    body = {"model": model, "messages": to_openai(messages)}
    if tools: body["tools"] = tools
    if not model.split("/")[-1].startswith(REASONING): body["temperature"] = 0
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
               "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    t0 = time.perf_counter()
    for attempt in range(6):
        req = urllib.request.Request(base, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.load(r)
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:600].replace(TOKEN or "§", "***")
            if e.code == 429 and attempt < 5:                       # 무료 시험용의 분당·하루 한도 — 잠깐 쉬고 다시
                wait = min(int(e.headers.get("Retry-After") or 0) or 20 * (attempt + 1), 90)
                print(f"(깃허브 모델 호출 한도: {wait}초 쉬고 다시, {attempt + 1}번째)", flush=True)
                time.sleep(wait); continue
            raise oh.OllamaError(e.code, detail)
        except urllib.error.URLError as e:
            raise SystemExit(f"깃허브 모델에 연결할 수 없습니다: {e.reason}")
    ch = ((out.get("choices") or [{}])[0]).get("message") or {}
    msg = {"role": "assistant", "content": ch.get("content") or ""}
    tcs = [{"id": tc.get("id"), "function": {"name": tc["function"]["name"], "arguments": _args(tc["function"].get("arguments"))}}
           for tc in (ch.get("tool_calls") or [])]
    if tcs: msg["tool_calls"] = tcs
    return {"message": msg, "_ms": round((time.perf_counter() - t0) * 1000), "_usage": out.get("usage", {})}

if __name__ == "__main__":
    if not TOKEN:
        sys.exit("GITHUB_TOKEN이 없습니다(깃허브 액션에서 permissions: models: read로 돌린다)")
    oh.ollama_chat = gh_chat                             # 바꾸는 곳은 이 한 줄뿐
    oh.main()
