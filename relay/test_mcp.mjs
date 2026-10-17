// 원격 상담 비서(relay/mcp.js) 점검 — MCP 규약(초기화·목록·호출·오류)과 판정 몇 가지를 모의 정보나루로 돌려 본다.
// 실행: node relay/test_mcp.mjs   (네트워크·키 불필요. 파이썬 판과의 대조는 relay/test_mcp_parity.py)
import worker from "./worker.js";
import { _resetForTest } from "./mcp.js";
import { mockFetch, rpc, call } from "./test_naru_mock.mjs";
import { readFileSync } from "node:fs";

const sc = JSON.parse(readFileSync(new URL("./test_mcp_scenarios.json", import.meta.url), "utf-8"));
const today = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
const snapshot = { ...sc.snapshot, asof: today };
const log = [];
globalThis.fetch = mockFetch(sc, snapshot, log);
const env = { NARU_KEY: "FAKE" };
let n = 0; const ok = (c, m) => { if (!c) { console.error("  ✗ " + m); process.exit(1); } n++; console.log("  ✓ " + m); };

// 1. 초기화와 목록
let r = await rpc(worker, env, { jsonrpc: "2.0", id: 1, method: "initialize",
  params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "test", version: "0" } } });
const init = r.body.result;
ok(r.status === 200 && init.protocolVersion === "2025-06-18" && init.capabilities.tools && init.capabilities.prompts &&
   init.serverInfo.name === "chaekiji-consult" && init.instructions.includes("상담 비서") && !JSON.stringify(r.body).includes("FAKE"),
   "initialize — 규약 판 그대로 · 도구·프롬프트 · 사용 안내(instructions) · 키 없음");
r = await rpc(worker, env, { jsonrpc: "2.0", id: 2, method: "initialize", params: { protocolVersion: "1999-01-01" } });
ok(r.body.result.protocolVersion === "2025-06-18", "모르는 규약 판 → 지원하는 최신 판으로 답함");
r = await rpc(worker, env, { jsonrpc: "2.0", method: "notifications/initialized" });
ok(r.status === 202 && r.body === null, "알림(notifications/initialized) → 202, 본문 없음");
r = await rpc(worker, env, { jsonrpc: "2.0", id: 3, method: "tools/list" });
const tools = r.body.result.tools;
ok(tools.map(t => t.name).join() === "consult_request,search_item,check_availability" &&
   tools.every(t => t.annotations.readOnlyHint === true) && !("user" in tools[0].inputSchema.properties),
   "tools/list — 읽기 전용 3종 · 회원 토큰 칸 없음");
r = await rpc(worker, env, { jsonrpc: "2.0", id: 4, method: "prompts/list" });
ok(r.body.result.prompts[0].name === "consult", "prompts/list — 사서 모드 지시문 consult");
r = await rpc(worker, env, { jsonrpc: "2.0", id: 5, method: "prompts/get", params: { name: "consult", arguments: { pickup: "원미" } } });
ok(r.body.result.messages[0].content.text.includes("「원미」") && !r.body.result.messages[0].content.text.includes("{pickup}"),
   "prompts/get — 받을 도서관이 지시문에 채워짐");
r = await rpc(worker, env, { jsonrpc: "2.0", id: 6, method: "ping" });
ok(JSON.stringify(r.body.result) === "{}", "ping");

// 2. 규약 오류
let raw = await worker.fetch(new Request("https://relay.test/mcp"), env);
const sse = await worker.fetch(new Request("https://relay.test/mcp", { headers: { Accept: "text/event-stream" } }), env);
const page = await worker.fetch(new Request("https://relay.test/mcp", { headers: { Accept: "text/html,application/xhtml+xml,*/*;q=0.8" } }), env);
const pageText = await page.text();
ok(raw.status === 405 && raw.headers.get("Allow") === "POST" && sse.status === 405 && sse.headers.get("Allow") === "POST" &&
   page.status === 200 && (page.headers.get("Content-Type") || "").startsWith("text/html") &&
   pageText.includes("커넥터에 넣는 주소") && pageText.includes("https://relay.test/mcp") && !pageText.includes("<script"),
   "GET /mcp → 405(이어 받기 통로 없음) · 인터넷 창으로 열면 안내 화면(스크립트 없음)");
r = await rpc(worker, env, "{not json");
ok(r.status === 400 && r.body.error.code === -32700, "JSON이 아님 → 400 · -32700");
r = await rpc(worker, env, []);
ok(r.status === 400 && r.body.error.code === -32600, "빈 묶음 → -32600");
r = await rpc(worker, env, [{ jsonrpc: "2.0", id: 7, method: "ping" }, { jsonrpc: "2.0", method: "notifications/initialized" },
                            { jsonrpc: "2.0", id: 8, method: "tools/list" }]);
ok(Array.isArray(r.body) && r.body.length === 2 && r.body[0].id === 7 && r.body[1].id === 8, "묶음 요청 — 요청 2건에만 답(알림 제외)");
r = await rpc(worker, env, { jsonrpc: "2.0", id: 9, method: "resources/list" });
ok(r.body.error.code === -32601, "없는 메서드 → -32601");
r = await rpc(worker, env, { jsonrpc: "2.0", id: 10, method: "tools/call", params: { name: "request_service", arguments: {} } });
ok(r.body.error.code === -32602, "접수 도구(request_service)는 원격 판에 없음 → -32602");

// 3. 판정
log.length = 0;
let c = await call(worker, env, "consult_request", { utterance: "나미야 잡화점의 기적 빌리고 싶어요", pickup: "상동" });
ok(!c.isError && c.out.route === "ill" && c.out.from_lib === "꿈여울" && c.out.availability.asof === today &&
   c.out.notice.includes(`정보나루 ${+today.slice(0, 4)}. ${+today.slice(5, 7)}. ${+today.slice(8, 10)}. 조회, 전일 기준`) &&
   !log.some(u => u.includes("data4library")),
   "나미야 — 오늘 새벽 자료로 판정(정보나루 호출 0회) · 관내 상호대차 · 안내문에 조회일");
ok(c.out.official_link === "https://alpasq.bcl.go.kr/search/keyword/" + encodeURIComponent("나미야 잡화점의 기적") &&
   c.out.notice.includes("공식 누리집에서 이 책 보기·신청") && c.out.desk_memo.includes("접수: 창구에서"),
   "   공식 누리집 링크 · 접수 메모(접수는 창구)");
c = await call(worker, env, "consult_request", { utterance: "작별하지 않는다 빌리고 싶어요" });
ok(!c.isError && c.out.pickup === "상동" && c.out.route === "ill" && c.out.book.isbn13 === "9788954682152" &&
   c.out.availability.available_at.join() === "꿈빛,원미" && c.out.policy.pending.length === 6 &&
   c.out.policy.pending.includes("상호대차 제외 자료 아님"),
   "목록 밖 책 — 정보나루 서지 검색 → 그 자리 조회 → 관내 상호대차 · 회원 규정 5건 + 자료 유형·신착(정보나루에 없음)은 창구 확인");
c = await call(worker, env, "consult_request", { utterance: "희랍어 시간 있나요?", pickup: "상동" });
ok(!c.isError && c.out.route === "check" && c.out.notice.includes("확인하지 못했습니다") && !c.out.notice.includes("소장되어 있지 않습니다") &&
   c.out.availability.nation === null && c.out.policy.pending.some(x => x.includes("비치")) && c.out.desk_memo.includes("확인 불가") &&
   c.out.official_link !== null,
   "목록 밖 책인데 소장 조회 실패 — 「미소장」이 아니라 「소장 확인 불가 → 창구 조회」 · 비치 규정도 창구 확인 · 누리집 링크");
c = await call(worker, env, "consult_request", { utterance: "흐르는 강물처럼", pickup: "상동" });
ok(!c.isError && c.out.found === false && c.out.route === "check" && c.out.notice.includes("연결되지 않아") &&
   c.out.desk_memo.startsWith("[조회 불가]"),
   "서지 검색부터 연결 끊김 — 「저자·출판사를 알려 달라」고 되묻지 않고 「조회 불가 → 창구 조회」");
c = await call(worker, env, "consult_request", { utterance: "나미야", user: "tok_demo" });
ok(c.isError && c.text.includes("회원 토큰을 받지 않습니다"), "회원 토큰을 넘기면 거절(개인정보를 받지 않음)");
c = await call(worker, env, "consult_request", { utterance: "나미야", pickup: "없는관" });
ok(c.isError && c.text.startsWith("ValueError: 수령관 「없는관」"), "설정에 없는 수령관 → 오류(파이썬 판과 같은 문구)");
c = await call(worker, env, "check_availability", { isbn13: "12345" });
ok(c.isError, "ISBN 형식 오류 → 오류");

// 4. 지키는 것
raw = await worker.fetch(new Request("https://relay.test/mcp", { method: "POST", headers: { Origin: "https://evil.example" },
  body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "ping" }) }), env);
ok(raw.status === 403, "허용 밖 출처(Origin) → 403");
raw = await worker.fetch(new Request("https://relay.test/mcp", { method: "OPTIONS", headers: { Origin: "https://claude.ai",
  "Access-Control-Request-Method": "POST" } }), env);
ok(raw.status === 204 && raw.headers.get("Access-Control-Allow-Origin") === "https://claude.ai" &&
   raw.headers.get("Access-Control-Allow-Methods").includes("POST"), "claude.ai 출처의 사전 확인(OPTIONS) → 204 · CORS 허용");
r = await rpc(worker, env, { jsonrpc: "2.0", id: 11, method: "ping" }, { Origin: "https://claude.ai" });
ok(r.status === 200 && r.headers["access-control-allow-origin"] === "https://claude.ai", "claude.ai 출처에서 부르기 → 200 · CORS 헤더");
raw = await worker.fetch(new Request("https://relay.test/mcp", { method: "POST", body: "{}" }), {});
ok(raw.status === 503, "키 미설정 → 503");
_resetForTest();
let limited = false;
for (let i = 0; i < 70 && !limited; i++) {
  const x = await call(worker, env, "search_item", { utterance: "나미야" }, 100 + i);
  limited = x.isError && x.text.includes("호출 한도");
}
ok(limited, "호출 상한(10분에 60회) — 넘으면 도구 오류로 알림");
console.log(`\n원격 상담 비서 점검 ${n}건 통과`);
