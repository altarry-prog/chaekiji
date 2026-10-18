#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""원격 상담 비서(relay/mcp.js)가 쓰는 자료 파일 relay/mcp_data.js를 만든다.

원본은 파이썬 참조 서버(server/)의 것을 그대로 쓴다. 판정 숫자·도서관 코드·지시문을 두 곳에 따로 적지 않기 위해서다.
  server/config/bucheon.yaml        설정(도서관 코드·규정 숫자·공식 누리집 주소 틀)
  server/fixtures/catalog.json      실측 서지 픽스처(시연 도서 5종 + 제외 규정 예시 2종)
  server/fixtures/holdings.json     2026. 8. 18. 실측 소장 픽스처(중계가 안 될 때 돌아갈 값)
  server/prompts/상담비서-지시문.md  사서 모드 지시문(MCP 프롬프트 consult)
  server/server.py                  도구 설명(TOOLS)·프롬프트 목록(PROMPTS)

실행:  python3 relay/build_mcp_data.py          → relay/mcp_data.js를 다시 쓴다
점검:  python3 relay/build_mcp_data.py --check  → 원본과 어긋나면 실패(깃허브 액션 tests.yml)
키·토큰·내부 주소는 이 파일에 들어가지 않는다(설정에서 필요한 칸만 골라 옮긴다)."""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "server"
OUT = ROOT / "relay" / "mcp_data.js"
REMOTE_TOOLS = ("consult_request", "search_item", "check_availability")
CFG_KEYS = ("city", "region_code", "home_library", "libraries", "rules", "ill_eta_days", "hold_days", "official_search_url",
            "ill_eta_text", "hold_includes_arrival_day", "no_pickup_block_days", "reserve_converts_to_ill")   # [10/18] 누리집 규정 대조
REMOTE_NOTE = {
    "consult_request": " [원격 판] 회원 토큰을 받지 않는다(개인정보를 받지 않음) — 한도·연체·중복은 늘 창구 확인으로 보류.",
    "search_item": " [원격 판] 시연 도서 5종은 실측 서지, 그 밖의 책은 정보나루 전국 서지 검색(제목 부분일치).",
    "check_availability": " [원격 판] 오늘 새벽 매일 갱신 자료에 있으면 그 자료, 없으면 정보나루를 그 자리에서 조회(전일 기준).",
}


def build() -> str:
    sys.path.insert(0, str(SERVER))
    os.environ["CHAEKIJI_MODE"] = "demo"                 # 자료만 읽는다 — 네트워크·키 없음
    os.environ.pop("CHAEKIJI_STORE", None)
    os.environ.pop("CHAEKIJI_AUDIT", None)
    import server as srv                                 # TOOLS·PROMPTS·tools.CFG를 그대로 쓴다

    cfg = {k: srv.tools.CFG[k] for k in CFG_KEYS if k in srv.tools.CFG}
    catalog = json.load(open(SERVER / "fixtures" / "catalog.json", encoding="utf-8"))["books"]
    hold = json.load(open(SERVER / "fixtures" / "holdings.json", encoding="utf-8"))
    hold = {k: hold[k] for k in ("_examples", "holdings", "nation") if k in hold}
    body = (SERVER / "prompts" / "상담비서-지시문.md").read_text(encoding="utf-8")
    body = body.split("\n", 2)[2] if body.startswith("#") else body   # server.py prompt_text와 같은 처리

    tools = []
    for t in srv.TOOLS:
        if t["name"] not in REMOTE_TOOLS:
            continue
        t = json.loads(json.dumps(t, ensure_ascii=False))
        props = t["inputSchema"].get("properties", {})
        props.pop("user", None)                           # 원격 판은 회원 토큰을 받지 않는다
        t["description"] += REMOTE_NOTE[t["name"]]
        tools.append(t)
    tools.sort(key=lambda t: REMOTE_TOOLS.index(t["name"]))

    dump = lambda o: json.dumps(o, ensure_ascii=False, indent=1)
    return "\n".join([
        "// 자동 생성 파일 — 손으로 고치지 말 것. relay/build_mcp_data.py가 server/의 원본으로 만든다.",
        "// 원본: server/config/bucheon.yaml · server/fixtures/catalog.json · server/fixtures/holdings.json ·",
        "//       server/prompts/상담비서-지시문.md · server/server.py(TOOLS·PROMPTS)",
        f"export const SERVER_VERSION = {dump(srv.SERVER['version'])};",
        f"export const CFG = {dump(cfg)};",
        f"export const CATALOG = {dump(catalog)};",
        f"export const HOLD = {dump(hold)};",
        f"export const PROMPT_BODY = {dump(body)};",
        f"export const TOOLS = {dump(tools)};",
        f"export const PROMPTS = {dump(srv.PROMPTS)};",
        "",
    ])


if __name__ == "__main__":
    text = build()
    if "--check" in sys.argv:
        now = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if now != text:
            sys.exit("relay/mcp_data.js가 server/의 원본과 다릅니다 — python3 relay/build_mcp_data.py 로 다시 만드세요")
        print("원격 상담 비서 자료 파일 — server/ 원본과 같음")
    else:
        OUT.write_text(text, encoding="utf-8")
        print(f"썼음: {OUT.relative_to(ROOT)} ({len(text):,}자)")
