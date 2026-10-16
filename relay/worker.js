/* 책이지 정보나루 중계 — Cloudflare Workers 판 (무료 호스팅 · 1파일)
 * 시연 웹 → 이 중계 → 정보나루 Open API. 인증키는 Workers 「환경변수(Secret) NARU_KEY」에만 둔다.
 * 설계: server/docs/정보나루-중계-설계.md  (허용 출처 · 경로 화이트리스트 · 호출 상한 · 최소 가공 · 키 흔적 없음)
 *
 * 제공 경로(화이트리스트):
 *   GET /holdings?isbn=9788972756194   → 부천 16개관 소장·대출 상태 {코드: ok|busy|none}
 *   GET /search?q=나미야 잡화점의 기적   → 서지 검색 상위 5건 (제목 부분일치)   [v0.3.4 상담 비서]
 *   GET /search?isbn=9788972756194      → 서지 1건
 *   GET /nation?isbn=9788972756194      → 경기 광역 소장관 수(전국 예시)       [v0.3.4]
 *   GET /health                         → {ok:true}  (키 유무만 알려주고 값은 절대 내보내지 않음)
 *   POST /mcp                           → 원격 상담 비서(MCP Streamable HTTP) — relay/mcp.js      [10/16]
 *                                          claude.ai 커스텀 커넥터에 이 주소를 넣으면 설치 없이 상담 비서를 쓴다
 * 그 밖의 경로는 404.
 * 시연 웹(브라우저)은 Origin 검사, MCP 서버(relay 모드)는 Origin이 없어 통과 — 호출 상한으로 남용을 막는다. */

const ALLOW_ORIGINS = [
  "https://altarry-prog.github.io",   // 시연 웹(깃허브 페이지스)
  "http://localhost:8080", "http://127.0.0.1:8080",  // 로컬 점검용
];
// 원격 상담 비서(/mcp)는 claude.ai 쪽 출처도 받는다 — 커넥터는 보통 서버끼리 부르지만(출처 없음), 브라우저에서 부를 때를 대비
const MCP_ORIGINS = [...ALLOW_ORIGINS, "https://claude.ai", "https://www.claude.ai", "https://claude.com"];
// 부천시립도서관 16관 정보나루 코드 (시연 웹 index.html의 LIB 표와 같다)
const LIBS = ["141321","141065","141248","141583","141315","141652","141056","141559",
              "141651","141043","141603","141660","141584","141535","141115","141151"];
const REGION = "31";          // 경기
const DTL_REGION = "31050";   // 부천 (정보나루 세부지역 코드)
const RATE_LIMIT = 60;        // 한 IP가 10분 안에 부를 수 있는 횟수(상담 1건 = 2~3회)
const CACHE_SEC = 600;        // 같은 ISBN 재조회 캐시(초)

const mem = { hits: new Map(), cache: new Map() };
import { handleMcp } from "./mcp.js";

export default {
  async fetch(req, env) {
    env = { ...env, NARU_KEY: env.NARU_KEY || env.NARUKEY };   // 비밀 이름은 NARU_KEY(권장)·NARUKEY 둘 다 받는다
    const url = new URL(req.url);
    const origin = req.headers.get("Origin") || "";
    const cors = corsHeaders(origin);
    if (url.pathname === "/mcp") {                              // [10/16] 원격 상담 비서 — POST만(그 밖은 mcp.js가 405)
      const mc = MCP_ORIGINS.includes(origin) ? { "Access-Control-Allow-Origin": origin, "Vary": "Origin",
        "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Expose-Headers": "Mcp-Session-Id",
        "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization, Mcp-Session-Id, MCP-Protocol-Version",
        "Access-Control-Max-Age": "600" } : {};
      if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: mc });
      if (!env.NARU_KEY) return json({ error: "relay-not-configured" }, 503, mc);
      if (origin && !MCP_ORIGINS.includes(origin)) return json({ error: "origin" }, 403, {});
      const ip = req.headers.get("CF-Connecting-IP") || "0";
      const resp = await handleMcp(req, {
        relayCall: (path, p, ctx) => relayCall(path, p.isbn || "", p.q || "", env, ctx),
        allow: () => allow(ip),
        newCtx: () => newCtx(env),
      });
      for (const [k, v] of Object.entries(mc)) resp.headers.set(k, v);
      return resp;
    }
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (req.method !== "GET") return json({ error: "method" }, 405, cors);
    if (!env.NARU_KEY) return json({ error: "relay-not-configured" }, 503, cors);   // 키 미설정 시 기동 거부
    if (origin && !ALLOW_ORIGINS.includes(origin)) return json({ error: "origin" }, 403, cors);

    if (url.pathname === "/health") return json({ ok: true, keyed: true, region: DTL_REGION }, 200, cors);
    if (!["/holdings", "/search", "/nation"].includes(url.pathname)) return json({ error: "not-found" }, 404, cors);

    const ip = req.headers.get("CF-Connecting-IP") || "0";
    if (!allow(ip)) return json({ error: "rate-limit" }, 429, cors);

    const isbn = (url.searchParams.get("isbn") || "").replace(/\D/g, "");
    const q = (url.searchParams.get("q") || "").trim().slice(0, 80);
    if (url.pathname === "/search") {
      if (!isbn && q.length < 2) return json({ error: "query" }, 400, cors);
    } else if (!/^97[89]\d{10}$/.test(isbn)) return json({ error: "isbn" }, 400, cors);
    try {
      return json(await relayCall(url.pathname, isbn, q, env, newCtx(env)), 200, cors);
    } catch (e) {
      // 실패 종류만 알린다(예: "https:AbortError", "http:503", "naru:…") — 키·주소는 싣지 않는다
      return json({ error: "upstream", detail: (e && e.detail) || [] }, 502, cors);
    }
  },
};

// 요청 1건의 상류 호출 기록 — 횟수(상한 확인)·실패 종류·통한 주소. wait는 점검용(기다리는 한도 ms, 비우면 기본값)
function newCtx(env) { return { n: 0, fails: [], via: null, wait: Number(env.NARU_WAIT_MS) || 0 }; }

// 세 경로의 공통 처리 — 10분 캐시 → 정보나루. 중계 경로와 원격 상담 비서(mcp.js)가 같이 쓴다(캐시도 같이).
async function relayCall(path, isbn, q, env, ctx) {
  q = String(q || "").trim().slice(0, 80);
  if (path === "/search" ? (!isbn && q.length < 2) : !/^97[89]\d{10}$/.test(isbn)) throw new Error("input");
  const key = path === "/search" ? (isbn ? `s:${isbn}` : `q:${q}`) : `${path}:${isbn}`;
  const hit = mem.cache.get(key);
  if (hit && Date.now() - hit.t < CACHE_SEC * 1000) return { ...hit.v, cached: true };
  let v;
  if (path === "/holdings") v = await holdings(isbn, env.NARU_KEY, ctx);
  else if (path === "/search") v = await search(q, isbn, env.NARU_KEY, ctx);
  else if (path === "/nation") v = await nation(isbn, env.NARU_KEY, ctx);
  else throw new Error("path");
  v = { ...v, via: ctx.via };
  mem.cache.set(key, { t: Date.now(), v });
  return { ...v, cached: false };
}

function kstDate() {
  const now = new Date(Date.now() + 9 * 3600 * 1000);
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}-${String(now.getUTCDate()).padStart(2, "0")}`;
}

async function search(q, isbn, key, ctx) {
  // 서지 검색 — 제목 부분일치 상위 5건(대출 많은 순). 자료유형·신착 여부는 정보나루가 주지 않는다.
  const params = isbn ? { isbn13: isbn, pageSize: 1 } : { title: q, exactMatch: "false", pageSize: 5 };
  const r = await naru("srchBooks", params, key, ctx);
  const docs = (r.docs || []).map(x => x.doc || x).filter(d => d.isbn13).map(d => ({
    isbn13: String(d.isbn13), title: d.bookname, author: d.authors, publisher: d.publisher, year: d.publication_year }));
  return { query: isbn || q, docs, asof: kstDate(), basis: "정보나루 srchBooks" };
}

async function nation(isbn, key, ctx) {
  const r = await naru("libSrchByBook", { isbn, region: REGION, pageSize: 200 }, key, ctx);
  return { isbn, found_count: (r.libs || []).length, asof: kstDate(), basis: "정보나루 libSrchByBook(경기 광역 예시) · 전일 기준" };
}

// 정보나루 매뉴얼(v20260210)의 호출 주소는 http다. https를 먼저 시도하고, 안 되면 http로 넘어간다.
// 2026. 10. 16. 깃허브 서버 실측: https는 연결 거절·지연이 잦았고 http로 81회 모두 성공. 일시 장애는 잠깐 쉬고 한 번 더.
// 2026. 10. 16. 첫 배포 뒤 보강 — ① 주소마다 기다리는 한도(https 2.5초 · http 12초): 답 없이 멈춘 주소에 붙잡히지 않는다.
//   ② 한 번 통한 주소를 기억해 다음 호출부터 먼저 쓴다(같은 실행 공간 안에서). ③ 요청 1건의 외부 호출을 45회 안으로
//   (Cloudflare 무료 요금제 상한 50). ④ 정보나루가 오류 문구(호출 한도 초과·키 오류 등)를 주면 「없음」으로 바꾸지 않고
//   오류로 낸다 — 16관이 모두 미소장처럼 보이는 일을 막는다. ⑤ 실패하면 실패 종류만 남긴다(키·주소 없이).
const NARU_BASES = ["https://data4library.kr/api/", "http://data4library.kr/api/"];
const WAIT_MS = { https: 2500, http: 12000 };
const SUBREQ_CAP = 45;
let BASE_OK = null;
async function naru(api, params, key, ctx) {
  const q = new URLSearchParams({ ...params, authKey: key, format: "json" });
  const bases = BASE_OK ? [BASE_OK, ...NARU_BASES.filter(b => b !== BASE_OK)] : NARU_BASES;
  for (let attempt = 0; attempt < 2; attempt++) {
    if (attempt) await new Promise(res => setTimeout(res, 1500));
    for (const base of bases) {
      const tag = base.startsWith("https:") ? "https" : "http";
      if (ctx.n >= SUBREQ_CAP) { ctx.fails.push("budget"); throw upstreamError(ctx); }
      ctx.n++;
      const ctl = new AbortController();
      const timer = setTimeout(() => ctl.abort(), ctx.wait || WAIT_MS[tag]);
      let d;
      try {
        const r = await fetch(`${base}${api}?${q}`, { cf: { cacheTtl: 0 }, signal: ctl.signal });
        if (!r.ok) { ctx.fails.push(`${tag}:${r.status}`); continue; }
        try { d = await r.json(); }
        catch (e) { ctx.fails.push(`${tag}:${e && e.name === "SyntaxError" ? "not-json" : clean(e, key)}`); continue; }
      } catch (e) { ctx.fails.push(`${tag}:${clean(e, key)}`); continue; }
      finally { clearTimeout(timer); }
      const resp = (d && d.response) || d || {};
      if (resp.error) {                       // 키·한도 오류는 주소를 바꿔 다시 해도 같다 — 바로 멈춘다
        ctx.fails.push(`naru:${hide(String(resp.error), key).slice(0, 60)}`);
        throw upstreamError(ctx);
      }
      BASE_OK = base; ctx.via = tag;
      return resp;
    }
  }
  throw upstreamError(ctx);
}
function clean(e, key) {   // 실패 종류 — 이름과 짧은 설명만. 키가 실린 주소·키 값은 지운다
  const name = (e && e.name) || "Error";
  const msg = hide(String((e && e.message) || ""), key)
    .replace(/https?:\/\/\S+/g, "").replace(/authKey=\S*/gi, "").trim().slice(0, 50);
  return msg ? `${name}(${msg})` : name;
}
function hide(s, key) { return key ? s.split(key).join("***") : s; }
function upstreamError(ctx) { const e = new Error("upstream"); e.detail = ctx.fails.slice(-8); return e; }

async function holdings(isbn, key, ctx) {
  // 1) 부천 지역 소장관 목록 1회 → 2) 소장관마다 bookExist 1회 (server/connectors/naru.py holdings_local과 같은 절차)
  const r1 = await naru("libSrchByBook", { isbn, region: REGION, dtl_region: DTL_REGION, pageSize: 300 }, key, ctx);
  const have = new Set();
  for (const l of r1.libs || []) { const lib = l.lib || l; const c = String(lib.libCode || ""); if (LIBS.includes(c)) have.add(c); }
  const libs = {};
  for (const c of LIBS) libs[c] = "none";
  await Promise.all([...have].map(async c => {
    const r = (await naru("bookExist", { libCode: c, isbn13: isbn }, key, ctx)).result || {};
    if (r.hasBook === "Y") libs[c] = r.loanAvailable === "Y" ? "ok" : "busy";
  }));
  return { isbn, asof: kstDate(), basis: "정보나루 bookExist · 대출 상태는 조회일 전일 기준", libs, calls: 1 + have.size };
}

function allow(ip) {
  const now = Date.now(), win = 600 * 1000;
  const arr = (mem.hits.get(ip) || []).filter(t => now - t < win);
  if (arr.length >= RATE_LIMIT) return false;
  arr.push(now); mem.hits.set(ip, arr); return true;
}
function corsHeaders(origin) {
  const h = { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" };
  if (ALLOW_ORIGINS.includes(origin)) { h["Access-Control-Allow-Origin"] = origin; h["Vary"] = "Origin"; }
  return h;
}
function json(obj, status, headers) { return new Response(JSON.stringify(obj), { status, headers }); }
