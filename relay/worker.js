/* 책이지 정보나루 중계 — Cloudflare Workers 판 (무료 호스팅 · 1파일)
 * 시연 웹 → 이 중계 → 정보나루 Open API. 인증키는 Workers 「환경변수(Secret)」에만 둔다.
 * [11/2 오후] 키 넷을 차례로 쓴다: NARU_KEY(깃허브 NARUKEY) → NARU_KEY2 → NARU_KEY3 → NARU_KEY4.
 *   앞 키가 한도 초과·승인 전·무효로 막히면 같은 호출을 다음 키로 다시 한다(아래 naruKeys·naru 참고).
 * 설계: server/docs/정보나루-중계-설계.md  (허용 출처 · 경로 화이트리스트 · 호출 상한 · 최소 가공 · 키 흔적 없음)
 *
 * 제공 경로(화이트리스트):
 *   GET /holdings?isbn=9788972756194   → 부천 16개관 소장·대출 상태 {코드: ok|busy|none}
 *   GET /search?q=나미야 잡화점의 기적   → 서지 검색 상위 10건 (제목 부분일치 · 권차) [v0.3.4 상담 비서 · 10/19 10건]
 *   GET /search?isbn=9788972756194      → 서지 1건
 *   GET /nation?isbn=9788972756194      → 경기 광역 소장관 수(전국 예시)       [v0.3.4]
 *   GET /health                         → {ok:true}  (키 유무만 알려주고 값은 절대 내보내지 않음)
 *   POST /mcp                           → 원격 상담 비서(MCP Streamable HTTP) — relay/mcp.js      [10/16]
 *                                          claude.ai 커스텀 커넥터에 이 주소를 넣으면 설치 없이 상담 비서를 쓴다
 *   POST /ask                           → Solar 상담 창(클로드 계정 없이) — relay/ask.js           [11/2]
 *                                          Solar Pro 4가 말을 알아듣고 판정은 /mcp와 같은 consult_request. 화면은 docs/ask/
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
import { handleAsk, handleRecords, handleStats } from "./ask.js";

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
      if (!naruKeys(env).length) return json({ error: "relay-not-configured" }, 503, mc);
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
    if (url.pathname === "/ask" || url.pathname === "/ask/records" || url.pathname === "/ask/stats") {   // [11/2] Solar 상담 창 — 시연 웹과 같은 출처의 화면에서만(출처 없는 호출도 막음)
      const ac = ALLOW_ORIGINS.includes(origin) ? { "Access-Control-Allow-Origin": origin, "Vary": "Origin",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type, X-Record-Token, X-Chaekiji-Check",
        "Access-Control-Max-Age": "600" } : {};
      const H = { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...ac };
      if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: ac });
      if (url.pathname !== "/ask") {                            // 담당자 기록 내려받기·건수(GET, 기록 암호 필요)
        if (req.method !== "GET") return json({ error: "method" }, 405, { ...H, Allow: "GET" });
        if (!ALLOW_ORIGINS.includes(origin)) return json({ error: "origin" }, 403, H);
        const ip = req.headers.get("CF-Connecting-IP") || "0";
        return url.pathname === "/ask/records" ? handleRecords(req, env, ip, H) : handleStats(req, env, ip, H);
      }
      if (req.method !== "POST") return json({ error: "method" }, 405, { ...H, Allow: "POST" });
      if (!naruKeys(env).length || !env.UPSTAGE_API_KEY) return json({ error: "ask-not-configured" }, 503, H);
      if (!ALLOW_ORIGINS.includes(origin)) return json({ error: "origin" }, 403, H);
      const ip = req.headers.get("CF-Connecting-IP") || "0";
      // [11/2 오후] 상담 창도 시연 웹·원격 판과 같은 키 순서(NARU_KEY → NARU_KEY2 → NARU_KEY3 → NARU_KEY4)로 조회한다.
      //   앞 키가 막히면 다음 키로 넘어가므로 쓰임별 전용 키(옛 NARU_KEY_ASK)는 더 쓰지 않는다
      return handleAsk(req, env, ip, {
        relayCall: (path, p, ctx) => relayCall(path, p.isbn || "", p.q || "", env, ctx),
        allow: () => true,                                     // /ask는 따로 센다(ask.js askAllow)
        newCtx: () => newCtx(env),
      }, H);
    }
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (req.method !== "GET") return json({ error: "method" }, 405, cors);
    if (!naruKeys(env).length) return json({ error: "relay-not-configured" }, 503, cors);   // 키 미설정 시 기동 거부
    if (origin && !ALLOW_ORIGINS.includes(origin)) return json({ error: "origin" }, 403, cors);

    // 키는 이름만 알린다(값은 절대 내보내지 않음): 넣어 둔 키 이름과, 이 실행 공간에서 지금 건너뛰는 키와 까닭
    if (url.pathname === "/health") return json({ ok: true, keyed: true, naru_keys: naruKeys(env).map(k => k.name), naru_held: heldKeys(),
      ask: !!env.UPSTAGE_API_KEY, records: !!(env.ASK_RECORDS && env.ASK_RECORD_TOKEN), region: DTL_REGION, colo: (req.cf && req.cf.colo) || null }, 200, cors);
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
function newCtx(env) { return { n: 0, fails: [], via: null, wait: Number(env.NARU_WAIT_MS) || 0, times: [] }; }

// 세 경로의 공통 처리 — 10분 캐시 → 정보나루. 중계 경로와 원격 상담 비서(mcp.js)가 같이 쓴다(캐시도 같이).
async function relayCall(path, isbn, q, env, ctx) {
  q = String(q || "").trim().slice(0, 80);
  if (path === "/search" ? (!isbn && q.length < 2) : !/^97[89]\d{10}$/.test(isbn)) throw new Error("input");
  const key = path === "/search" ? (isbn ? `s:${isbn}` : `q:${q}`) : `${path}:${isbn}`;
  const hit = mem.cache.get(key);
  if (hit && Date.now() - hit.t < CACHE_SEC * 1000) return { ...hit.v, cached: true };
  let v;
  const keys = naruKeys(env);
  if (path === "/holdings") v = await holdings(isbn, keys, ctx);
  else if (path === "/search") v = await search(q, isbn, keys, ctx);
  else if (path === "/nation") v = await nation(isbn, keys, ctx);
  else throw new Error("path");
  v = { ...v, via: ctx.via, key_name: ctx.keyName || null };   // 어느 키로 받았는지 이름만(값 아님)
  mem.cache.set(key, { t: Date.now(), v });
  return { ...v, cached: false };
}

function kstDate() {
  const now = new Date(Date.now() + 9 * 3600 * 1000);
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}-${String(now.getUTCDate()).padStart(2, "0")}`;
}

async function search(q, isbn, keys, ctx) {
  // 서지 검색 — 제목 부분일치 상위 10건(대출 많은 순, [10/19] 5 → 10 · 권차 vol 함께). 자료유형·신착 여부는 정보나루가 주지 않는다.
  const params = isbn ? { isbn13: isbn, pageSize: 1 } : { title: q, exactMatch: "false", pageSize: 10 };
  const r = await naru("srchBooks", params, keys, ctx);
  const docs = (r.docs || []).map(x => x.doc || x).filter(d => d.isbn13).map(d => ({
    isbn13: String(d.isbn13), title: d.bookname, author: d.authors, publisher: d.publisher, year: d.publication_year,
    ...(d.vol ? { vol: String(d.vol) } : {}) }));
  return { query: isbn || q, docs, asof: kstDate(), basis: "정보나루 srchBooks" };
}

async function nation(isbn, keys, ctx) {
  const r = await naru("libSrchByBook", { isbn, region: REGION, pageSize: 200 }, keys, ctx);
  return { isbn, found_count: (r.libs || []).length, asof: kstDate(), basis: "정보나루 libSrchByBook(경기 광역 예시) · 하루 전 기준" };
}

// 정보나루 매뉴얼(v20260210)의 호출 주소는 http다. https를 먼저 시도하고, 안 되면 http로 넘어간다.
// 2026. 10. 16. 깃허브 서버 실측: https는 연결 거절·지연이 잦았고 http로 81회 모두 성공. 일시 장애는 잠깐 쉬고 한 번 더.
// 2026. 10. 16. 첫 배포 뒤 보강 — ① 주소마다 기다리는 한도(https 2.5초 · http 12초): 답 없이 멈춘 주소에 붙잡히지 않는다.
//   ② 한 번 통한 주소를 기억해 다음 호출부터 먼저 쓴다(같은 실행 공간 안에서). ③ 요청 1건의 외부 호출을 45회 안으로
//   (Cloudflare 무료 요금제 상한 50). ④ 정보나루가 오류 문구(호출 한도 초과·키 오류 등)를 주면 「없음」으로 바꾸지 않고
//   오류로 낸다 — 16관이 모두 미소장처럼 보이는 일을 막는다. ⑤ 실패하면 실패 종류만 남긴다(키·주소 없이).
// [10/16 바꿈] 매뉴얼의 http 주소를 먼저 부른다. Cloudflare에서 https는 대부분 연결되지 않아(첫 배포 기록: /holdings·/nation via http),
//   처음 부를 때마다 https를 2.5초 기다리고 http로 넘어가곤 했다. 키는 어차피 http로 갔으므로 노출 정도는 같고 기다림만 준다.
const NARU_BASES = ["http://data4library.kr/api/", "https://data4library.kr/api/"];
const WAIT_MS = { https: 2500, http: 12000 };
const SUBREQ_CAP = 45;
let BASE_OK = null;

// ── [11/2 오후] 정보나루 키 넷을 차례로 쓰기(담당자 15:52 「NARUKEY, NARU_KEY2, NARU_KEY3, NARU_KEY4 차례로 다 활용」) ──
// 키마다 하루 500번(호출 서버 IP 미등록)이라, 앞 키가 막히면 같은 호출을 다음 키로 다시 한다.
//   · 오류 문구에 「한도·횟수·건수」가 있으면 그날 자정(한국 시각)까지, 「활성·승인·인증키·유효」가 있으면 1시간 그 키를 건너뛴다
//     (승인 전 키가 승인되면 1시간 안에 저절로 다시 쓰인다 — 다시 배포할 필요 없음)
//   · 그 밖의 오류는 다음 키로 한 번 더 해 보고, 다음 키도 같은 문구면 키 문제가 아니라고 보고 멈춘다(키 넷을 헛되이 막지 않게).
//     다음 키가 되면 앞 키만 10분 쉬게 한다
//   · 기억은 같은 실행 공간(isolate) 안에서만 한다(저장 공간 호출을 늘리지 않으려고). 키 값은 어디에도 남기지 않고 이름만 쓴다
export const KEY_NAMES = ["NARU_KEY", "NARU_KEY2", "NARU_KEY3", "NARU_KEY4"];
const keyHold = new Map();                       // 키 이름 → { until(ms), why: quota|key|other }
const LAST_GOOD = { name: null, t: 0 };          // 마지막으로 통한 키(16관 조회를 한꺼번에 보내도 되는지 볼 때)
export function naruKeys(env) {                  // 넣어 둔 키를 순서대로(빈 칸·같은 값은 뺌)
  const seen = new Set(), out = [];
  for (const name of KEY_NAMES) {
    const k = String((env && env[name]) || "").trim();
    if (!k || seen.has(k)) continue;
    seen.add(k); out.push({ name, key: k });
  }
  return out;
}
export function keyErrorKind(msg) {
  const m = String(msg || "");
  if (/한도|횟수|건수|사용량|이용량|limit|exceed|quota/i.test(m)) return "quota";
  if (/활성|승인|인증키|인증 키|유효하지|등록되지|미등록|권한|invalid|unauthor|forbidden|key/i.test(m)) return "key";
  return null;
}
function nextKstMidnight(now) { return (Math.floor((now + 9 * 3600e3) / 86400e3) + 1) * 86400e3 - 9 * 3600e3; }
function holdKey(name, why, now = Date.now()) {
  keyHold.set(name, { until: why === "quota" ? nextKstMidnight(now) : now + (why === "key" ? 3600e3 : 600e3), why });
}
function isHeld(name, now = Date.now()) { const h = keyHold.get(name); return !!(h && h.until > now); }
export function heldKeys(now = Date.now()) {     // /health용 — 이름과 까닭만
  const out = {};
  for (const [name, h] of keyHold) if (h.until > now) out[name] = h.why;
  return out;
}
export function _resetKeysForTest() { keyHold.clear(); LAST_GOOD.name = null; LAST_GOOD.t = 0; BASE_OK = null; }

async function naru(api, params, keys, ctx) {
  const list = (keys || []).filter(k => !isHeld(k.name));
  if (!list.length) { ctx.fails.push("keys:held"); throw upstreamError(ctx); }      // 넣어 둔 키가 모두 쉬는 중
  let prev = null;                               // 앞 키의 오류 { name, msg, kind }
  for (const k of list) {
    if (isHeld(k.name)) continue;                // 동시에 돈 다른 호출이 방금 막아 둔 키
    const r = await naruOnce(api, params, k.key, ctx);
    if (r.resp) {
      if (prev && !prev.kind) holdKey(prev.name, "other");
      LAST_GOOD.name = k.name; LAST_GOOD.t = Date.now(); ctx.keyName = k.name;
      return r.resp;
    }
    const kind = keyErrorKind(r.err);
    ctx.fails.push(`naru:${k.name}:${kind || hide(r.err, k.key).slice(0, 40)}`);
    if (kind) holdKey(k.name, kind);
    else if (prev && !prev.kind && prev.msg === r.err) throw upstreamError(ctx);    // 두 키가 같은 오류 — 키 문제가 아니다
    prev = { name: k.name, msg: r.err, kind };
  }
  throw upstreamError(ctx);
}

// 키 하나로 한 번 부르기 — 주소(http·https)를 바꿔 가며. 정보나루가 오류 문구를 주면 { err }로 돌려 키를 바꿀지 위에서 정한다
async function naruOnce(api, params, key, ctx) {
  const q = new URLSearchParams({ ...params, authKey: key, format: "json" });
  const bases = BASE_OK ? [BASE_OK, ...NARU_BASES.filter(b => b !== BASE_OK)] : NARU_BASES;
  for (let attempt = 0; attempt < 2; attempt++) {
    if (attempt) await new Promise(res => setTimeout(res, 1500));
    for (const base of bases) {
      const tag = base.startsWith("https:") ? "https" : "http";
      if (ctx.n >= (ctx.cap || SUBREQ_CAP)) { ctx.fails.push("budget"); throw upstreamError(ctx); }   // [11/2] /ask는 모델 호출 몫을 남겨 42
      ctx.n++;
      const ctl = new AbortController();
      const timer = setTimeout(() => ctl.abort(), ctx.wait || WAIT_MS[tag]);
      const s0 = Date.now();
      let d;
      try {
        const r = await fetch(`${base}${api}?${q}`, { cf: { cacheTtl: 0 }, signal: ctl.signal });
        if (!r.ok) { ctx.fails.push(`${tag}:${r.status}`); continue; }
        try { d = await r.json(); }
        catch (e) { ctx.fails.push(`${tag}:${e && e.name === "SyntaxError" ? "not-json" : clean(e, key)}`); continue; }
      } catch (e) { ctx.fails.push(`${tag}:${clean(e, key)}`); continue; }
      finally { clearTimeout(timer); }
      const resp = (d && d.response) || d || {};
      if (resp.error) return { err: String(resp.error) };   // 키·한도 오류는 주소를 바꿔 다시 해도 같다 — 키를 바꿀지는 naru가 정한다
      BASE_OK = base; ctx.via = tag;
      if (ctx.times) ctx.times.push(Date.now() - s0);      // 호출 한 번의 시간(ms) — 느린 곳을 찾으려고(키·주소 없음)
      return { resp };
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

async function holdings(isbn, keys, ctx) {
  // 16관 bookExist를 한꺼번에 부른다 — 왕복 한 번.
  // [10/16 바꿈] 처음에는 「부천 지역 소장관 목록(libSrchByBook) 1회 → 소장관마다 bookExist」였다(파이썬 판·매일 갱신과 같은 절차).
  //   실측(문의 15건)에서 목록 밖 책이 가운데값 14.9초였고, 소장관 목록 조회가 그중 가장 느렸다.
  //   많이 찾는 책은 소장관이 13~16곳이라 호출 수는 거의 같고(16회), 기다림은 한 번으로 준다.
  const t0 = Date.now();
  const libs = {};
  for (const c of LIBS) libs[c] = "none";
  const one = async c => {
    const r = (await naru("bookExist", { libCode: c, isbn13: isbn }, keys, ctx)).result || {};
    if (r.hasBook === "Y") libs[c] = r.loanAvailable === "Y" ? "ok" : "busy";
  };
  // [11/2 오후] 첫 키가 30분 안에 통한 적이 없으면 한 관을 먼저 불러 쓸 키를 정한 뒤 나머지를 한꺼번에 보낸다
  //   (막힌 키로 16번을 한꺼번에 보내면 호출 상한 45번을 헛되이 쓰게 되어서)
  const first = (keys || []).find(k => !isHeld(k.name));
  if (first && LAST_GOOD.name === first.name && Date.now() - LAST_GOOD.t < 30 * 60e3) await Promise.all(LIBS.map(one));
  else { await one(LIBS[0]); await Promise.all(LIBS.slice(1).map(one)); }
  const ts = [...(ctx.times || [])].sort((a, b) => a - b);
  return { isbn, asof: kstDate(), basis: "정보나루 bookExist · 대출 상태는 조회일 하루 전 기준", libs, calls: LIBS.length,
           upstream_ms: Date.now() - t0, call_ms_median: ts.length ? ts[Math.floor(ts.length / 2)] : null, call_ms_max: ts.length ? ts[ts.length - 1] : null };
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
