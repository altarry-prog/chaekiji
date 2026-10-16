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
 * 그 밖의 경로는 404.
 * 시연 웹(브라우저)은 Origin 검사, MCP 서버(relay 모드)는 Origin이 없어 통과 — 호출 상한으로 남용을 막는다. */

const ALLOW_ORIGINS = [
  "https://altarry-prog.github.io",   // 시연 웹(깃허브 페이지스)
  "http://localhost:8080", "http://127.0.0.1:8080",  // 로컬 점검용
];
// 부천시립도서관 16관 정보나루 코드 (시연 웹 index.html의 LIB 표와 같다)
const LIBS = ["141321","141065","141248","141583","141315","141652","141056","141559",
              "141651","141043","141603","141660","141584","141535","141115","141151"];
const REGION = "31";          // 경기
const DTL_REGION = "31050";   // 부천 (정보나루 세부지역 코드)
const RATE_LIMIT = 60;        // 한 IP가 10분 안에 부를 수 있는 횟수(상담 1건 = 2~3회)
const CACHE_SEC = 600;        // 같은 ISBN 재조회 캐시(초)

const mem = { hits: new Map(), cache: new Map() };

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const origin = req.headers.get("Origin") || "";
    const cors = corsHeaders(origin);
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
    let key;
    if (url.pathname === "/search") {
      if (!isbn && q.length < 2) return json({ error: "query" }, 400, cors);
      key = isbn ? `s:${isbn}` : `q:${q}`;
    } else {
      if (!/^97[89]\d{10}$/.test(isbn)) return json({ error: "isbn" }, 400, cors);
      key = `${url.pathname}:${isbn}`;
    }
    const hit = mem.cache.get(key);
    if (hit && Date.now() - hit.t < CACHE_SEC * 1000) return json({ ...hit.v, cached: true }, 200, cors);

    try {
      let v;
      if (url.pathname === "/holdings") v = await holdings(isbn, env.NARU_KEY);
      else if (url.pathname === "/search") v = await search(q, isbn, env.NARU_KEY);
      else v = await nation(isbn, env.NARU_KEY);
      mem.cache.set(key, { t: Date.now(), v });
      return json({ ...v, cached: false }, 200, cors);
    } catch (e) {
      return json({ error: "upstream" }, 502, cors);   // 오류 문구에 키·주소를 싣지 않는다
    }
  },
};

function kstDate() {
  const now = new Date(Date.now() + 9 * 3600 * 1000);
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}-${String(now.getUTCDate()).padStart(2, "0")}`;
}

async function search(q, isbn, key) {
  // 서지 검색 — 제목 부분일치 상위 5건(대출 많은 순). 자료유형·신착 여부는 정보나루가 주지 않는다.
  const params = isbn ? { isbn13: isbn, pageSize: 1 } : { title: q, exactMatch: "false", pageSize: 5 };
  const r = await naru("srchBooks", params, key);
  const docs = (r.docs || []).map(x => x.doc || x).filter(d => d.isbn13).map(d => ({
    isbn13: String(d.isbn13), title: d.bookname, author: d.authors, publisher: d.publisher, year: d.publication_year }));
  return { query: isbn || q, docs, asof: kstDate(), basis: "정보나루 srchBooks" };
}

async function nation(isbn, key) {
  const r = await naru("libSrchByBook", { isbn, region: REGION, pageSize: 200 }, key);
  return { isbn, found_count: (r.libs || []).length, asof: kstDate(), basis: "정보나루 libSrchByBook(경기 광역 예시) · 전일 기준" };
}

// 정보나루 매뉴얼(v20260210)의 호출 주소는 http다. https를 먼저 시도하고, 안 되면 http로 넘어간다.
// 2026. 10. 16. 깃허브 서버 실측: https는 연결 거절·지연이 잦았고 http로 81회 모두 성공. 일시 장애는 잠깐 쉬고 한 번 더.
const NARU_BASES = ["https://data4library.kr/api/", "http://data4library.kr/api/"];
async function naru(api, params, key) {
  const q = new URLSearchParams({ ...params, authKey: key, format: "json" });
  let last;
  for (let attempt = 0; attempt < 2; attempt++) {
    if (attempt) await new Promise(res => setTimeout(res, 1500));
    for (const base of NARU_BASES) {
      try {
        const r = await fetch(`${base}${api}?${q}`, { cf: { cacheTtl: 0 } });
        if (!r.ok) { last = new Error("http " + r.status); continue; }
        const d = await r.json();
        return d.response || d;
      } catch (e) { last = e; }
    }
  }
  throw last || new Error("naru");
}

async function holdings(isbn, key) {
  // 1) 부천 지역 소장관 목록 1회 → 2) 소장관마다 bookExist 1회 (server/connectors/naru.py holdings_local과 같은 절차)
  const r1 = await naru("libSrchByBook", { isbn, region: REGION, dtl_region: DTL_REGION, pageSize: 300 }, key);
  const have = new Set();
  for (const l of r1.libs || []) { const lib = l.lib || l; const c = String(lib.libCode || ""); if (LIBS.includes(c)) have.add(c); }
  const libs = {};
  for (const c of LIBS) libs[c] = "none";
  await Promise.all([...have].map(async c => {
    const r = (await naru("bookExist", { libCode: c, isbn13: isbn }, key)).result || {};
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
