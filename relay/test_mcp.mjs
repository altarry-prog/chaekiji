// 원격 상담 비서(relay/mcp.js) 점검 — MCP 규약(초기화·목록·호출·오류)과 판정 몇 가지를 모의 정보나루로 돌려 본다.
// 실행: node relay/test_mcp.mjs   (네트워크·키 불필요. 파이썬 판과의 대조는 relay/test_mcp_parity.py)
import worker from "./worker.js";
import { _resetForTest, snapshotOk, splitVolume, cleanTitle } from "./mcp.js";
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
ok(c.out.official_link === "https://alpasq.bcl.go.kr/search/keyword/9788972756194" &&   // [10/18] 부천 링크 틀 제목 → ISBN(그 판본 화면까지)
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
ok(c.out.official_link === "https://alpasq.bcl.go.kr/search/keyword/" + encodeURIComponent(c.out.book.title),
   "   [10/18] 소장 확인 불가인 책의 누리집 링크는 제목 검색(그 판본이 없을 수도 있어 ISBN 대신)");
c = await call(worker, env, "consult_request", { utterance: "흐르는 강물처럼", pickup: "상동" });
ok(!c.isError && c.out.found === false && c.out.route === "check" && c.out.notice.includes("연결되지 않아") &&
   c.out.desk_memo.startsWith("[조회 불가]"),
   "서지 검색부터 연결 끊김 — 「저자·출판사를 알려 달라」고 되묻지 않고 「조회 불가 → 창구 조회」");
c = await call(worker, env, "consult_request", { utterance: "나미야", user: "tok_demo" });
ok(c.isError && c.text.includes("회원 토큰을 받지 않습니다"), "회원 토큰을 넘기면 거절(개인정보를 받지 않음)");
c = await call(worker, env, "consult_request", { utterance: "나미야 잡화점의 기적", pickup: "상동역칙칙폭폭" });
ok(!c.isError && c.out.pickup === "상동역 칙칙폭폭" && c.out.route === "ill" && c.out.notice.includes("상동역 칙칙폭폭도서관에서 받으실 수 있고") &&
   !c.out.notice.includes("도서관에는") && c.out.notice.includes("도착일과 보관 기한은 창구에서 확인") &&
   c.out.policy.pending.some(x => x.includes("비치")) && c.out.desk_memo.includes("작은도서관"),
   "[10/18] 작은도서관 받을 곳 — 관내 상호대차로 판정, 그곳 서가 비치·도착일·보관은 창구 확인(파이썬 판과 같음)");
c = await call(worker, env, "consult_request", { utterance: "나미야", pickup: "없는관" });
ok(c.isError && c.text.startsWith("ValueError: 수령관 「없는관」"), "설정에 없는 수령관 → 오류(파이썬 판과 같은 문구)");
c = await call(worker, env, "search_item", { utterance: "채식주의자 상호대차 되나요?" });
ok(!c.isError && c.out.found && c.out.query === "채식주의자" && c.out.isbn13 === "9788936433598",
   "[10/18] 문장째 넘어온 「채식주의자 상호대차 되나요?」 → 검색어 「채식주의자」(「되나요」까지 걷어냄)");
c = await call(worker, env, "consult_request", { utterance: "채식주의자 상동도서관으로 가져다줄 수 있어요?", pickup: "부천시립 상동도서관" });
ok(!c.isError && c.out.book.isbn13 === "9788936433598" && c.out.pickup === "상동" && c.out.route === "visit",
   "[10/18] 수령관 「부천시립 상동도서관」 → 「상동」 · 검색어에서 「상동도서관으로」를 뺌 → 바로 이용");
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
// [10/19] 심사 기간 고정 자료 — 동결 뒤 새벽 갱신이 멈춰도 11/8 자료로 결선까지 답한다(파이썬 naru.snapshot_ok와 같은 규칙, 날짜를 넣어 확인)
ok(snapshotOk("2026-11-08", "2026-11-13") && snapshotOk("2026-11-08", "2026-11-17") && snapshotOk("2026-11-08", "2026-11-25") && snapshotOk("2026-11-08", "2026-11-26") &&
   !snapshotOk("2026-11-08", "2026-11-27") && !snapshotOk("2026-11-07", "2026-11-13") && !snapshotOk("2026-11-09", "2026-11-08") &&
   snapshotOk("2026-10-19", "2026-10-19") && snapshotOk("2026-10-17", "2026-10-19") && !snapshotOk("2026-10-16", "2026-10-19") && !snapshotOk("bad", "2026-11-13"),
   "심사 기간 고정 자료 — 11/8 자료는 11/13~11/26에 신선, 11/27·11/7 자료·미래 날짜는 아님 · 평소 2일 규칙 그대로");

// [10/19] 서지 고르기 — AI 대조 시험(상담 비서로 실제 책 12건)에서 다른 책을 고른 3건·못 찾은 2건을 고친 것.
//   검색 결과는 2026. 10. 19. 실제 /search 응답(시나리오에 실음), 소장·대출과 「흔한남매」 권차는 모의 값. 호출 상한과 섞이지 않게 다른 IP로 부른다.
_resetForTest();
const call2 = async (name, args, id) => {
  const r = await rpc(worker, env, { jsonrpc: "2.0", id, method: "tools/call", params: { name, arguments: args } }, { "CF-Connecting-IP": "198.51.100.19" });
  const res = r.body.result; return res.isError ? { err: res.content[0].text } : JSON.parse(res.content[0].text);
};
ok(JSON.stringify(splitVolume("흔한남매 1권")) === '["흔한남매","1",true]' && JSON.stringify(splitVolume("불편한 편의점 2")) === '["불편한 편의점","2",false]' &&
   splitVolume("트렌드 코리아 2026")[1] === null && splitVolume("1984")[1] === null && splitVolume("82년생 김지영")[1] === null &&
   cleanTitle("양귀자 모순 빌리고 싶은데 상동역 칙칙폭폭에서 받을게요") === "양귀자 모순" &&
   cleanTitle("불편한 편의점 빌리고 싶대요, 송내에서 받는대요") === "불편한 편의점" && cleanTitle("숲속 작은 집") === "숲속 작은 집",
   "[10/19] 권차 나누기(「1권」·끝 숫자, 「2026」·「1984」는 권차 아님) · 말끝·작은도서관 이름 걷기(「숲속 작은 집」 같은 제목은 그대로)");
let s1 = await call2("consult_request", { utterance: "해리 포터와 마법사의 돌", pickup: "원미" }, 501);
ok(s1.book.isbn13 === "9788983920683" && s1.book.title === "해리포터와 마법사의 돌" && s1.book.evidence.includes("2번째") && s1.route === "ill",
   "[10/19] 「해리 포터와 마법사의 돌」 — 검색 첫 결과(혼혈 왕자)가 아니라 같은 책(2번째)을 고름 · 근거에 고른 사실");
s1 = await call2("consult_request", { utterance: "구름빵 백희나 있어요?", pickup: "별빛마루" }, 502);
ok(s1.book.isbn13 === "9788953527058" && !s1.book.title.includes("중문판") && s1.book.evidence.includes("「구름빵」") && s1.route === "visit" &&
   !("same_title_others" in s1) && !s1.notice.includes("같은 제목의 다른 책"),
   "[10/19] 「구름빵 백희나」 — 중문판만 나오면 고르지 않고 「구름빵」으로 다시 찾아 저자(백희나)로 확인 · 부서명이 다른 시리즈 책(「구름빵 : 키 크는 빵 주세요」)은 「같은 제목」으로 세지 않음");
s1 = await call2("consult_request", { utterance: "흔한남매 1권", pickup: "송내" }, 503);
const s1b = await call2("search_item", { utterance: "불편한 편의점 2" }, 504);
const s1d = await call2("search_item", { utterance: "흔한남매 9권" }, 508);
ok(s1.book.isbn13 === "9790000000103" && s1.book.vol === "1" && s1.notice.startsWith("『흔한남매 1권』은") && s1.desk_memo.includes("[1권]") && s1.route === "ill" && s1b.found && s1b.isbn13 === "9791161572062" && s1b.isbn13 !== "9791161571188" &&
   s1d.found === false && s1d.candidate_books.length === 3,
   "[10/19] 권차 — 「흔한남매 1권」은 1권(모의 권차 · 안내문에 「흔한남매 1권」), 「불편한 편의점 2」는 시연 도서 1권 픽스처로 가지 않음, 없는 권(9권)·권 모르는 판은 고르지 않고 되묻기");
s1 = await call2("consult_request", { utterance: "문헌정보학개론", pickup: "상동" }, 505);
const s1c = await call2("search_item", { utterance: "문헌정보학개론 정동열" }, 506);
ok(s1.route === "sea" && s1.same_title_others.length === 3 && s1.notice.includes("같은 제목의 다른 책도 있습니다") && s1.desk_memo.includes("저자 확인") &&
   s1c.found === false && s1c.candidate_books.length === 3 && s1c.reason.includes("고르지 못함"),
   "[10/19] 같은 제목·다른 저자 — 고른 책을 밝히고 저자 확인을 청함 · 말한 저자(정동열)가 어느 결과와도 안 맞으면 고르지 않고 후보 3건과 되묻기");
s1 = await call2("consult_request", { utterance: "양귀자 모순 빌리고 싶은데 상동역 칙칙폭폭에서 받을게요", pickup: "상동역 칙칙폭폭" }, 507);
ok(s1.found && s1.book.isbn13 === "9788998441012" && s1.availability.at_pickup === "point" && s1.route === "ill",
   "[10/19] 문장째 문의 — 「빌리고 싶은데」·「상동역 칙칙폭폭에서」를 걷어 「양귀자 모순」으로 찾고 작은도서관 받기로 판정");
// [10/19 밤] 판본 보정 — 고른 판이 관내에 없을 때만 같은 작품의 다른 판을 확인해 알린다(갈래는 그대로). 두 판의 소장 값은 모의
s1 = await call2("consult_request", { utterance: "문헌정보학개론 김수경", pickup: "상동" }, 509);
const s1e = await call2("consult_request", { utterance: "해리 포터와 마법사의 돌", pickup: "원미" }, 510);
ok(s1.route === "sea" && s1.book.isbn13 === "9791187268512" && (s1.other_editions || []).length === 1 && s1.other_editions[0].isbn13 === "9791187268758" &&
   s1.notice.includes("같은 책의 다른 판은 관내에 있습니다") && s1.notice.includes("상동도서관 서가에") && s1.desk_memo.includes("다른 판 관내:") &&
   s1.official_link === null && String(s1.other_editions[0].official_link).endsWith("9791187268758") && !("other_editions" in s1e) &&
   s1.notice.startsWith("『문헌정보학개론』은") && s1.desk_memo.startsWith("도서: 문헌정보학개론 ("),
   "[10/19 밤] 판본 보정 — 고른 판(2021)이 관내에 없으면 같은 작품의 다른 판(2024)을 확인해 알림·갈래(책바다)는 그대로 · 관내에 있는 책은 다른 판을 보지 않음 · 정보나루 서명 끝 빈칸은 안내문·메모에서 뗌(「은(는)」 방지)");

console.log(`\n원격 상담 비서 점검 ${n}건 통과`);
