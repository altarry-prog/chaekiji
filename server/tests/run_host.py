#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[v0.3.4] 공개 모델 호스트(hosts/ollama_host.py) 시험 — 진짜 Ollama 대신 이 PC 안의 모의 Ollama로 돈다.
검증하는 것:
  ① native 방식: 모델이 tool_calls로 consult_request를 부르면 호스트가 MCP 서버를 실제로 호출해 결과를 돌려준다
  ② json 방식: 도구 호출을 지원하지 않는 모델(400 거부)이면 스스로 json 방식으로 넘어가 같은 일을 한다
  ③ 호출 기록(JSONL)에 도구 이름·인자·소요 시간이 남는다
  ④ 모델이 없는 도구를 부르면 오류를 돌려주고 멈추지 않는다
실행: python3 tests/run_host.py   (네트워크·인증키·Ollama 불필요)"""
import subprocess, json, sys, os, threading, http.server, socketserver, time, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
PORT = 8796

class FakeOllama(http.server.BaseHTTPRequestHandler):
    """모델 2종 흉내: fake-native(tool_calls 지원) · fake-json(도구 호출 미지원 → 400)."""
    def log_message(self, *a): pass
    def _send(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); req = json.loads(self.rfile.read(n))
        model, msgs = req["model"], req["messages"]
        last_user = next((m["content"] for m in reversed(msgs) if m["role"] == "user"), "")
        if model == "fake-json" and req.get("tools"):
            return self._send({"error": f"registry.ollama.ai/library/{model} does not support tools"}, 400)
        has_tool_result = any(m["role"] == "tool" for m in msgs) or last_user.startswith("[도구 결과]")
        if model == "fake-badpickup":                 # [10/18] 수령관을 지어내는 모델(2차 실측의 엑사원: 「dream」·「book」)
            if not has_tool_result:
                return self._send({"message": {"role": "assistant", "content": "",
                                               "tool_calls": [{"function": {"name": "consult_request",
                                                                            "arguments": {"utterance": "나미야 잡화점의 기적", "pickup": "dream", "lang": "en"}}}]}})
        if model == "fake-nulluser":                  # [10/18] 회원 토큰 자리에 문자열 "null"을 넘기는 모델(3차 실측의 라마)
            if not has_tool_result:
                return self._send({"message": {"role": "assistant", "content": "",
                                               "tool_calls": [{"function": {"name": "consult_request",
                                                                            "arguments": {"utterance": "나미야 잡화점의 기적", "pickup": "상동", "lang": "ko", "user": "null"}}}]}})
        if model == "fake-loop":                      # [10/18] 설정에 없는 수령관으로 끝없이 되풀이하는 모델(실측에서 본 라마의 행동)
            return self._send({"message": {"role": "assistant", "content": "",
                                           "tool_calls": [{"function": {"name": "consult_request",
                                                                        "arguments": {"utterance": "나미야", "pickup": "없는관"}}}]}})
        if not has_tool_result:
            args = {"utterance": "나미야 잡화점의 기적", "pickup": "상동"}
            if "없는도구" in last_user:
                call = ("no_such_tool", {})
            else:
                call = ("consult_request", args)
            if model == "fake-native":
                return self._send({"message": {"role": "assistant", "content": "",
                                               "tool_calls": [{"function": {"name": call[0], "arguments": call[1]}}]}})
            return self._send({"message": {"role": "assistant",
                                           "content": "```json\n" + json.dumps({"tool": call[0], "arguments": call[1]}, ensure_ascii=False) + "\n```"}})
        # 도구 결과를 받은 뒤 — 결과 안의 갈래를 그대로 옮겨 적는다(모델이 지어내지 않는지 확인용)
        result_text = next((m["content"] for m in reversed(msgs) if m["role"] in ("tool", "user")), "")
        route = "?"
        try:
            o = json.loads(result_text.split("\n", 1)[1] if result_text.startswith("[도구 결과]") else result_text)
            route = o.get("route_label") or o.get("error", "?")
        except Exception:
            pass
        final = f"판정: {route}\n이용자 안내문: (도구 결과의 notice를 그대로)\n접수 메모: (도구 결과의 desk_memo를 그대로)"
        if model == "fake-native":
            return self._send({"message": {"role": "assistant", "content": final}})
        return self._send({"message": {"role": "assistant", "content": json.dumps({"answer": final}, ensure_ascii=False)}})

socketserver.TCPServer.allow_reuse_address = True
httpd = socketserver.TCPServer(("127.0.0.1", PORT), FakeOllama)
threading.Thread(target=httpd.serve_forever, daemon=True).start(); time.sleep(0.3)

PASS = 0
def ok(cond, label):
    global PASS
    assert cond, f"실패: {label}"
    PASS += 1; print(f"  ✓ {label}")

def run(model, ask, log, protocol="auto", extra=()):
    cmd = [sys.executable, str(ROOT/"hosts"/"ollama_host.py"), "--model", model, "--ollama", f"http://127.0.0.1:{PORT}",
           "--mode", "demo", "--ask", ask, "--log", log, "--protocol", protocol, *extra]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=str(ROOT))
    return r.stdout + r.stderr

log = Path(tempfile.mkdtemp()) / "host_log.ndjson"
print("── native 방식(tool_calls 지원 모델) ──")
out = run("fake-native", "나미야 잡화점의 기적 빌리고 싶어요", str(log))
ok("도구 호출 1: consult_request" in out and "관내 상호대차" in out, "① 모델의 tool_calls → MCP 서버 호출 → 갈래 「관내 상호대차」가 답에 옴")
ok("방식 native" in out, "   native 방식으로 끝남")

print("── json 방식(도구 호출 미지원 모델 → 자동 전환) ──")
out2 = run("fake-json", "나미야 잡화점의 기적 빌리고 싶어요", str(log))
ok("json 방식으로 넘어갑니다" in out2 and "도구 호출 1: consult_request" in out2 and "관내 상호대차" in out2,
   "② 400 거부 → json 방식 전환 → 같은 도구 호출 · 같은 판정")
ok("방식 json" in out2, "   json 방식으로 끝남")

rows = [json.loads(l) for l in open(log, encoding="utf-8")]
ok(len(rows) == 2 and all(r["tool"] == "consult_request" and r["arguments"]["utterance"] and r["model_ms"] >= 0 for r in rows)
   and {r["protocol"] for r in rows} == {"native", "json"},
   "③ 호출 기록 JSONL — 모델·방식·도구·인자·소요 시간")

out3 = run("fake-native", "없는도구 테스트", str(log))
ok("없는 도구" in out3 and "판정" in out3, "④ 없는 도구 호출 — 오류를 돌려주고 대화는 이어짐")

print("── [10/18] 되풀이 멈춤 · 도구 하나만 보이기 ──")
log2 = Path(tempfile.mkdtemp()) / "host_log2.ndjson"
out4 = run("fake-loop", "나미야 잡화점의 기적", str(log2))
rows2 = [json.loads(l) for l in open(log2, encoding="utf-8")]
ok("(멈춤) 같은 도구 오류가 3번" in out4 and len(rows2) == 3 and all(r["error"] for r in rows2),
   "⑤ 같은 인자의 도구 오류가 3번 되풀이되면 멈추고, 멈춘 사실을 답으로 남김(호출 기록 3줄)")
out5 = run("fake-native", "나미야 잡화점의 기적 빌리고 싶어요", str(log2), extra=("--tools", "consult"))
ok("도구 1종" in out5 and "관내 상호대차" in out5, "⑥ --tools consult — 모델에 상담 묶음 하나만 보여도 같은 판정")
log3 = Path(tempfile.mkdtemp()) / "host_log3.ndjson"
out6 = run("fake-badpickup", "나미야 잡화점의 기적 빌리고 싶어요", str(log3), extra=("--pickup", "상동", "--lang", "ko"))
rows3 = [json.loads(l) for l in open(log3, encoding="utf-8")]
ok("호출자 값으로 고정" in out6 and "관내 상호대차" in out6 and rows3[0]["arguments"]["pickup"] == "상동"
   and rows3[0]["arguments"]["lang"] == "ko" and rows3[0].get("forced"),
   "⑦ 모델이 지어낸 수령관·언어(dream·en)는 호출자 값(상동·ko)으로 고정하고 기록에 남김")
out7 = run("fake-nulluser", "나미야 잡화점의 기적 빌리고 싶어요", str(log3), extra=("--pickup", "상동"))
rows4 = [json.loads(l) for l in open(log3, encoding="utf-8")]
ok("관내 상호대차" in out7 and "user" not in rows4[-1]["arguments"] and not rows4[-1]["error"],
   "⑧ 모델이 넘긴 회원 토큰(user=\"null\")은 빼고 부름 — 도구 오류 없이 같은 판정")
httpd.shutdown()
print(f"\n호스트 시험 {PASS}건 통과 — 공개 모델에서도 같은 서버·같은 지시문·같은 도구.")
