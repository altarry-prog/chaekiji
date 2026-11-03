#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""업스테이지 Solar Pro 4를 공개 모델 실측 도구에 그대로 붙이는 작은 중계(Ollama 모양 → 오픈AI 모양).

왜: AI가 맡는 몫 지표(tools/model2/run_ai_metrics.py)와 공개 모델 호스트(main의 server/hosts/ollama_host.py)는
Ollama의 /api/chat 모양으로 모델을 부른다. 이 중계가 127.0.0.1:11434에서 그 모양을 받아 업스테이지 API
(https://api.upstage.ai/v1/chat/completions, 오픈AI 모양)로 옮겨 보내고, 답을 다시 Ollama 모양으로 돌려준다.
그래서 지시문(프롬프트 consult)·모델에 보이는 도구(consult_request 하나)·문의 24건·채점이 공개 모델 실측과 같다.

인증: 환경변수 UPSTAGE_API_KEY(깃허브 Secrets). 키 값은 출력·기록하지 않는다.
보내는 것: 지시문, 이용자의 말(책 제목·도서관 이름), 도구 결과(소장·대출·안내문). 개인정보는 없다.
사용: UPSTAGE_API_KEY=… python3 upstage_ollama_proxy.py            (127.0.0.1:11434에서 기다림)
      UPSTAGE_API_KEY=… python3 upstage_ollama_proxy.py --check    (연결·모델 이름·도구 호출 지원을 한 번 확인)"""
import json, os, sys, time, threading, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.environ.get("UPSTAGE_BASE", "https://api.upstage.ai/v1").rstrip("/")
KEY = os.environ.get("UPSTAGE_API_KEY", "")
PORT = int(os.environ.get("PROXY_PORT", "11434"))
USAGE_FILE = os.environ.get("SOLAR_USAGE_FILE", "/content/solar_usage.json")
VERSION = "upstage-api-proxy-1"
_lock = threading.Lock()
_usage = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "models": {}, "errors": {}}


def _args(v):
    if isinstance(v, dict):
        return v
    try:
        return json.loads(v or "{}")
    except json.JSONDecodeError:
        return {"utterance": str(v)}


def to_openai(messages):
    """Ollama 모양 대화를 오픈AI 모양으로. 도구 결과에는 앞 호출의 id를 차례로 붙인다(오픈AI 대화 규칙)."""
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


def _mask(s):
    return (s or "").replace(KEY, "***") if KEY else (s or "")


def upstage_chat(body_in, timeout=600):
    """Ollama /api/chat 요청 하나를 업스테이지로 보내고 Ollama 모양 답을 돌려준다. 오류는 (코드, 내용)으로 올린다."""
    body = {"model": body_in.get("model") or "solar-pro4", "messages": to_openai(body_in.get("messages") or []),
            "temperature": (body_in.get("options") or {}).get("temperature", 0)}
    if body_in.get("tools"):
        body["tools"] = body_in["tools"]
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    t0 = time.perf_counter()
    for attempt in range(7):
        req = urllib.request.Request(BASE + "/chat/completions", data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.load(r)
            break
        except urllib.error.HTTPError as e:
            detail = _mask(e.read().decode("utf-8", "replace")[:800])
            with _lock:
                _usage["errors"][str(e.code)] = _usage["errors"].get(str(e.code), 0) + 1
            if e.code in (429, 500, 502, 503, 504) and attempt < 6:      # 짧은 시간에 몰리면 잠깐 막힘(안내서) — 쉬고 다시
                wait = min(int(e.headers.get("Retry-After") or 0) or 10 * (attempt + 1), 90)
                print(f"(업스테이지 {e.code}: {wait}초 쉬고 다시, {attempt + 1}번째) {detail[:160]}", flush=True)
                time.sleep(wait)
                continue
            raise RuntimeError((e.code, detail))
        except urllib.error.URLError as e:
            if attempt < 6:
                time.sleep(10 * (attempt + 1))
                continue
            raise RuntimeError((502, f"업스테이지에 연결할 수 없습니다: {e.reason}"))
    ch = ((out.get("choices") or [{}])[0]).get("message") or {}
    msg = {"role": "assistant", "content": ch.get("content") or ""}
    tcs = [{"id": tc.get("id"), "function": {"name": tc["function"]["name"], "arguments": _args(tc["function"].get("arguments"))}}
           for tc in (ch.get("tool_calls") or [])]
    if tcs:
        msg["tool_calls"] = tcs
    u = out.get("usage") or {}
    with _lock:
        _usage["requests"] += 1
        _usage["prompt_tokens"] += int(u.get("prompt_tokens") or 0)
        _usage["completion_tokens"] += int(u.get("completion_tokens") or 0)
        m = out.get("model") or body["model"]
        _usage["models"][m] = _usage["models"].get(m, 0) + 1
        try:
            with open(USAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(_usage, f, ensure_ascii=False)
        except OSError:
            pass
    return {"model": out.get("model") or body["model"], "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "message": msg, "done": True, "total_duration": int((time.perf_counter() - t0) * 1e9),
            "prompt_eval_count": u.get("prompt_tokens"), "eval_count": u.get("completion_tokens")}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/api/version"):
            return self._send(200, {"version": VERSION})
        if self.path.startswith("/api/tags"):
            return self._send(200, {"models": [{"name": "solar-pro4"}]})
        self._send(404, {"error": "없는 주소"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "JSON이 아닙니다"})
        if not self.path.startswith("/api/chat"):
            return self._send(404, {"error": "없는 주소"})
        try:
            self._send(200, upstage_chat(body))
        except RuntimeError as e:
            code, detail = e.args[0]
            print(f"(업스테이지 오류 {code}) {detail[:300]}", flush=True)
            self._send(code if 400 <= int(code) < 600 else 502, {"error": detail})


def check():
    """연결·모델 이름·도구 호출 지원을 작은 요청 하나로 확인한다(문의 24건 전에)."""
    tools = [{"type": "function", "function": {"name": "consult_request", "description": "책 제목으로 상호대차 판정",
                                               "parameters": {"type": "object", "properties": {"utterance": {"type": "string"}},
                                                              "required": ["utterance"]}}}]
    r = upstage_chat({"model": os.environ.get("AI_MODEL", "solar-pro4"),
                      "messages": [{"role": "system", "content": "책 제목을 도구로 확인한다."},
                                   {"role": "user", "content": "불편한 편의점 빌릴 수 있어요?"}], "tools": tools})
    tc = (r["message"].get("tool_calls") or [{}])[0].get("function", {})
    print(json.dumps({"model": r["model"], "tool_call": tc.get("name"), "arguments": tc.get("arguments"),
                      "content_head": (r["message"].get("content") or "")[:80]}, ensure_ascii=False))
    if not tc:
        print("(도구를 부르지 않았습니다. 호스트가 json 방식으로 넘어갈 수 있습니다)", flush=True)


if __name__ == "__main__":
    if not KEY:
        sys.exit("UPSTAGE_API_KEY가 없습니다(깃허브 Secrets에 넣고 다시 돌립니다)")
    if "--check" in sys.argv:
        check()
        sys.exit(0)
    print(f"업스테이지 중계: 127.0.0.1:{PORT} → {BASE}/chat/completions", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
