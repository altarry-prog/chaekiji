#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책이지 MCP 참조 서버 v0.3.1
MCP(Model Context Protocol) stdio 전송: 줄 단위 JSON-RPC 2.0.
MCP를 지원하는 어떤 AI 도구(클로드 데스크톱·Codex CLI·VS Code 등)에도 그대로 연결된다 (README·lab/README 참조).
표준 도구 10종(핵심 8종+확장 2종)을 노출하며, 지역 고유값은 전부 config/*.yaml에 있다.
v0.3.1(실험실): 감사 기록(CHAEKIJI_AUDIT) — 모든 tools/call을 해시 사슬 JSONL로 남긴다."""
import sys, json, traceback
import tools, audit, store

SERVER = {"name": "chaekiji-mcp", "version": "0.3.3"}
PROTO  = "2024-11-05"

def S(o): return {"type": "object", **o}
TOOLS = [
 {"name": "search_item",
  "description": "일상어 발화에서 도서를 식별해 ISBN 단위로 확정한다(근거 포함).",
  "inputSchema": S({"properties": {"utterance": {"type": "string"}, "lang": {"type": "string"}},
                    "required": ["utterance"]})},
 {"name": "check_availability",
  "description": "관내 실시간 재고를 확인하고, 관내에 없으면 전국(정보나루·전일 기준)을 본다.",
  "inputSchema": S({"properties": {"isbn13": {"type": "string"}, "realtime": {"type": "boolean"}},
                    "required": ["isbn13"]})},
 {"name": "check_policy",
  "description": "상호대차 규정 7종(비치·한도 3종·연체정지·제외자료·중복)을 판정하고 규정별 근거를 돌려준다.",
  "inputSchema": S({"properties": {"user": {"type": "string"}, "isbn13": {"type": "string"},
                                   "pickup": {"type": "string"}},
                    "required": ["user", "isbn13", "pickup"]})},
 {"name": "request_service",
  "description": "신청 실행. 권한은 즉시 확인(confirmed_by_user) 또는 사전 위임(mandate_id) 중 하나이며, 어느 경로든 실행 직전 규정을 재판정한다. 위임 실행은 위임 범위(무료 경로·주기당 권수)를 벗어나면 스스로 건너뛴다. client_ref를 주면 같은 요청 재수신 시 새 신청 대신 기존 접수를 반환한다(이중 방지).",
  "inputSchema": S({"properties": {"user": {"type": "string"}, "isbn13": {"type": "string"},
                                   "from_lib": {"type": "string"}, "pickup": {"type": "string"},
                                   "confirmed_by_user": {"type": "boolean"},
                                   "mandate_id": {"type": "string"},
                                   "route": {"type": "string", "enum": ["ill", "sea"]},
                                   "client_ref": {"type": "string"}},
                    "required": ["user", "isbn13", "from_lib", "pickup"]})},
 {"name": "track_request",
  "description": "[v0.3] 신청 추적 — 접수 이후의 생애주기(접수→확보→이송→도착·보관기한→대출/실패/취소)를 본인에 한해 조회한다.",
  "inputSchema": S({"properties": {"user": {"type": "string"}, "request_no": {"type": "string"}},
                    "required": ["user", "request_no"]})},
 {"name": "cancel_request",
  "description": "[v0.3] 신청 취소 — 본인 신청만, 대출 완료 전까지. 취소 즉시 한도가 복원된다.",
  "inputSchema": S({"properties": {"user": {"type": "string"}, "request_no": {"type": "string"}},
                    "required": ["user", "request_no"]})},
 {"name": "find_alternative",
  "description": "점자·오디오북 등 대체자료 존재를 확인한다(책나래 분기 근거).",
  "inputSchema": S({"properties": {"isbn13": {"type": "string"}, "user": {"type": "string"}},
                    "required": ["isbn13"]})},
 {"name": "notify_user",
  "description": "이용자 선호 채널(문자·음성전화)로 알림을 보낸다.",
  "inputSchema": S({"properties": {"user": {"type": "string"}, "event": {"type": "string"},
                                   "message": {"type": "string"}},
                    "required": ["user", "event", "message"]})},
 {"name": "suggest_items",
  "description": "[확장 v0.2] 이달의 추천 도서 목록(운영: AI 책큐·정보나루 recommandList 커넥터).",
  "inputSchema": S({"properties": {"user": {"type": "string"}, "count": {"type": "integer"}},
                    "required": []})},
 {"name": "manage_mandate",
  "description": "[확장 v0.2] 사전 위임장(책이지 패스) 관리 — create(범위 명시 동의 1회)/status/revoke. 범위 안 신청은 확인 없이, 범위 밖은 확인으로 — 이용자 통제 장치.",
  "inputSchema": S({"properties": {"user": {"type": "string"},
                                   "op": {"type": "string", "enum": ["create", "status", "revoke"]},
                                   "pickup": {"type": "string"}},
                    "required": ["user", "op"]})},
]
IMPL = {"search_item": tools.search_item, "check_availability": tools.check_availability,
        "check_policy": tools.check_policy, "request_service": tools.request_service,
        "track_request": tools.track_request, "cancel_request": tools.cancel_request,
        "find_alternative": tools.find_alternative, "notify_user": tools.notify_user,
        "suggest_items": tools.suggest_items, "manage_mandate": tools.manage_mandate,
        "_sim": tools._sim}   # _sim: 데모·시험 전용 상태 전이 훅 — tools/list 비노출, 운영에 없음

def reply(id_, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": id_}
    if error is not None: msg["error"] = error
    else: msg["result"] = result
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n"); sys.stdout.flush()

def handle(req):
    m, id_, p = req.get("method"), req.get("id"), req.get("params") or {}
    if m == "initialize":
        reply(id_, {"protocolVersion": p.get("protocolVersion", PROTO),
                    "capabilities": {"tools": {}}, "serverInfo": SERVER})
    elif m == "notifications/initialized":
        pass                                            # 알림 — 응답 없음
    elif m == "ping":
        reply(id_, {})
    elif m == "tools/list":
        reply(id_, {"tools": TOOLS})
    elif m == "tools/call":
        name, args = p.get("name"), p.get("arguments") or {}
        if name == "request_service" and "from" in args:   # 편의: from → from_lib
            args["from_lib"] = args.pop("from")
        try:
            out = IMPL[name](**args)
            audit.record(name, args, out, False)            # [v0.3.1] 감사 기록(켜져 있을 때만)
            reply(id_, {"content": [{"type": "text",
                                     "text": json.dumps(out, ensure_ascii=False, indent=1)}],
                        "isError": False})
        except Exception as e:
            audit.record(name, args, f"{type(e).__name__}: {e}", True)
            reply(id_, {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}],
                        "isError": True})
    elif id_ is not None:
        reply(id_, error={"code": -32601, "message": f"method not found: {m}"})

def main():
    print(f"[chaekiji-mcp] {tools.CFG['city']} · {tools.MODE} 모드 · 관내 출처 {tools.LOCAL_SOURCE}"
          f" · {store.describe()} · 감사 기록 {'켜짐' if audit.enabled() else '꺼짐'}", file=sys.stderr)
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try: handle(json.loads(line))
        except Exception:
            traceback.print_exc(file=sys.stderr)

if __name__ == "__main__":
    main()
