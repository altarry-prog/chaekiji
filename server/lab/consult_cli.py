#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""상담 비서를 명령 창에서 한 번 부르기 — 모델 없이, 도구(consult_request)가 돌려주는 판정·안내문·접수 메모를 읽기 쉽게 보인다.

무엇을 하나: server.py를 띄워 MCP 요청(initialize → tools/call consult_request)을 보내고, 돌아온 결과를 사람이 읽는 모양으로 찍는다.
            claude.ai·클로드 데스크톱·공개 모델 호스트가 부르는 것과 같은 도구, 같은 요청이다(모델이 하는 말 다듬기만 빠진다).
데이터: 환경변수 CHAEKIJI_MODE(기본 auto — 중계 → 2일 이내 매일 갱신 파일 → 8/18 실측 자료). 인증키 불필요.
실행: python lab/consult_cli.py "나미야 잡화점의 기적 빌리고 싶어요" 상동
      python lab/consult_cli.py "소년이 온다" 꿈빛 --json      (결과 원문 JSON까지)
보이는 모양: 안내문 속 누리집 주소는 「(아래 링크)」로 두고 「◀ 링크:」 줄에 한글을 풀어 보인다(%로 바뀐 글자를 되돌린 같은 주소).
            도구가 돌려준 원문 그대로는 --json으로 본다.
접수는 하지 않는다 — 이 도구는 판정·안내문·접수 메모까지만 만든다."""
import argparse, json, os, re, subprocess, sys
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent.parent           # server/


def main():
    ap = argparse.ArgumentParser(description="상담 비서(consult_request) 한 번 부르기")
    ap.add_argument("utterance", help="이용자의 말(가능하면 책 제목)")
    ap.add_argument("pickup", nargs="?", default=None, help="받을 도서관(예: 상동). 비우면 설정의 기본 도서관")
    ap.add_argument("--lang", default="ko")
    ap.add_argument("--json", action="store_true", help="결과 원문(JSON)도 찍기")
    a = ap.parse_args()
    env = dict(os.environ, PYTHONUTF8="1")
    env.setdefault("CHAEKIJI_MODE", "auto")
    args = {"utterance": a.utterance, "lang": a.lang}
    if a.pickup:
        args["pickup"] = a.pickup
    lines = [json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "consult-cli", "version": "1"}}}),
             json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                         "params": {"name": "consult_request", "arguments": args}}, ensure_ascii=False)]
    p = subprocess.run([sys.executable, str(HERE / "server.py")], input="\n".join(lines) + "\n", capture_output=True,
                       text=True, encoding="utf-8", env=env, cwd=str(HERE), timeout=120)
    replies = {json.loads(l)["id"]: json.loads(l) for l in p.stdout.splitlines() if l.strip()}
    if 2 not in replies:
        sys.exit("서버 응답 없음:\n" + p.stderr[-800:])
    res = replies[2]["result"]
    text = res["content"][0]["text"]
    print("▶ 도구 호출: consult_request " + json.dumps(args, ensure_ascii=False))
    if res.get("isError"):
        print("◀ 오류: " + text); sys.exit(1)
    o = json.loads(text)
    print(f"◀ 판정: {o['route_label']}" + (f" — 소장관 {o['from_lib']}" if o.get("route") == "ill" else ""))
    if o.get("book"):
        b = o["book"]; print(f"◀ 책: 『{b['title']}』 {b.get('author') or ''} · ISBN {b['isbn13']}")
    av = o.get("availability") or {}
    if av.get("basis"):
        print(f"◀ 근거: {av['basis']}")
    links = re.findall(r"https?://\S+", o["notice"])
    shown = o["notice"]
    for u in links:
        shown = shown.replace(u, "(아래 링크)")
    print("◀ 안내문: " + shown)
    for u in links:
        print("◀ 링크: " + unquote(u).replace(" ", "%20"))
    print("◀ 접수 메모:")
    for ln in o["desk_memo"].splitlines():
        print("   " + ln)
    if a.json:
        print(json.dumps(o, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
