// 시험용 모의 정보나루 — 시나리오(JSON)로 srchBooks·libSrchByBook·bookExist와 매일 갱신 파일에 답한다.
// relay/test_mcp.mjs(원격 상담 비서 점검)와 relay/test_mcp_parity.mjs(파이썬 판과 대조)가 함께 쓴다. 네트워크·키 불필요.
//   scenario.books   {검색어: [{isbn13,title,author,publisher,year}]}  — srchBooks(title=검색어)
//   scenario.libs    {ISBN: {도서관코드: "ok"|"busy"}}                  — 소장관 목록과 대출 가능 여부(없으면 미소장)
//   scenario.nation  {ISBN: 경기 광역 소장관 수}
//   scenario.fail    [ISBN…]                                           — 이 ISBN이 실린 호출은 연결이 끊긴다
//   snapshot         매일 갱신 파일 내용(없으면 404)
import { SNAPSHOT_URL } from "./mcp.js";

export function mockFetch(scenario, snapshot, log = []) {
  const allBooks = Object.values(scenario.books || {}).flat();
  const reply = obj => new Response(JSON.stringify({ response: obj }), { status: 200, headers: { "Content-Type": "application/json" } });
  return async (url) => {
    url = String(url);
    log.push(url);
    if (url === SNAPSHOT_URL) {
      return snapshot ? new Response(JSON.stringify(snapshot), { status: 200 }) : new Response("nf", { status: 404 });
    }
    if (!url.includes("data4library.kr/api/")) return new Response("nf", { status: 404 });
    const u = new URL(url);
    if (u.searchParams.get("authKey") !== "FAKE") return new Response("{}", { status: 403 });
    const api = u.pathname.split("/").pop();
    const isbn = u.searchParams.get("isbn") || u.searchParams.get("isbn13") || "";
    if (isbn && (scenario.fail || []).includes(isbn)) throw new TypeError("Network connection lost.");
    if (api === "srchBooks") {
      const t = u.searchParams.get("title");
      const docs = t ? (scenario.books || {})[t] || [] : allBooks.filter(b => b.isbn13 === isbn).slice(0, 1);
      return reply({ docs: docs.map(b => ({ doc: { isbn13: b.isbn13, bookname: b.title, authors: b.author,
                                                     publisher: b.publisher, publication_year: b.year } })) });
    }
    if (api === "libSrchByBook") {
      if (u.searchParams.get("dtl_region")) {
        const held = Object.keys((scenario.libs || {})[isbn] || {});
        return reply({ libs: held.map(c => ({ lib: { libCode: c } })) });
      }
      const n = (scenario.nation || {})[isbn] || 0;
      return reply({ libs: Array.from({ length: n }, (_, i) => ({ lib: { libCode: String(900000 + i) } })) });
    }
    if (api === "bookExist") {
      const st = ((scenario.libs || {})[isbn] || {})[u.searchParams.get("libCode")];
      return reply({ result: st ? { hasBook: "Y", loanAvailable: st === "ok" ? "Y" : "N" } : { hasBook: "N", loanAvailable: "N" } });
    }
    return reply({ error: "unknown api" });
  };
}

// 원격 상담 비서에 JSON-RPC 한 건을 보낸다
export async function rpc(worker, env, body, headers = {}) {
  const r = await worker.fetch(new Request("https://relay.test/mcp", {
    method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body) }), env);
  const text = await r.text();
  return { status: r.status, body: text ? JSON.parse(text) : null, headers: Object.fromEntries(r.headers) };
}
export async function call(worker, env, name, args, id = 1) {
  const r = await rpc(worker, env, { jsonrpc: "2.0", id, method: "tools/call", params: { name, arguments: args } });
  const res = r.body.result;
  return { isError: res.isError, text: res.content[0].text, out: res.isError ? null : JSON.parse(res.content[0].text) };
}
