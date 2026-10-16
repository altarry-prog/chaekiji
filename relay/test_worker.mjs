// worker.js 점검 — 정보나루를 흉내 낸 fetch로 네 경로를 돌려 본다(네트워크·키 불필요).
// 실행: node relay/test_worker.mjs
import worker from "./worker.js";
const calls = [];
globalThis.fetch = async (url) => {
  calls.push(url);
  const u = new URL(url);
  if (u.searchParams.get("authKey") !== "FAKE") return new Response("{}", { status: 403 });
  const api = u.pathname.split("/").pop();
  let body;
  if (api === "libSrchByBook") {
    const libs = u.searchParams.get("dtl_region") ? [{ lib: { libCode: "141321" } }, { lib: { libCode: "141065" } }, { lib: { libCode: "999999" } }]
                                                 : Array.from({ length: 7 }, (_, i) => ({ lib: { libCode: String(100000 + i) } }));
    body = { response: { libs } };
  } else if (api === "bookExist") {
    const code = u.searchParams.get("libCode");
    body = { response: { result: { hasBook: "Y", loanAvailable: code === "141065" ? "Y" : "N" } } };
  } else if (api === "srchBooks") {
    body = { response: { docs: u.searchParams.get("title")?.includes("채식")
      ? [{ doc: { isbn13: "9788936433598", bookname: "채식주의자", authors: "한강 지음", publisher: "창비", publication_year: "2007" } }] : [] } };
  } else body = { response: { error: "unknown api" } };
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
};
const env = { NARU_KEY: "FAKE" };
const get = async (path, headers = {}, e = env) => {
  const r = await worker.fetch(new Request("https://relay.test" + path, { headers }), e);
  return { status: r.status, body: await r.json(), h: Object.fromEntries(r.headers) };
};
let n = 0; const ok = (c, m) => { if (!c) { console.error("  ✗ " + m); process.exit(1); } n++; console.log("  ✓ " + m); };

let r = await get("/health");
ok(r.status === 200 && r.body.ok === true && !JSON.stringify(r.body).includes("FAKE"), "/health — ok, 키 값 없음");
r = await get("/holdings?isbn=9788972756194");
ok(r.status === 200 && r.body.libs["141065"] === "ok" && r.body.libs["141321"] === "busy" && r.body.libs["141248"] === "none" && r.body.calls === 3,
   "/holdings — 소장관만 bookExist(1+2회) · ok/busy/none 매핑");
ok(/^\d{4}-\d{2}-\d{2}$/.test(r.body.asof), "   asof 날짜(YYYY-MM-DD)");
r = await get("/search?q=채식주의자 있나요");
ok(r.status === 200 && r.body.docs.length === 1 && r.body.docs[0].isbn13 === "9788936433598", "/search?q= — 서지 1건(제목 부분일치)");
r = await get("/search?isbn=9788936433598");
ok(r.status === 200 && Array.isArray(r.body.docs), "/search?isbn= — 서지 조회 경로");
r = await get("/nation?isbn=9788972756194");
ok(r.status === 200 && r.body.found_count === 7, "/nation — 광역 소장관 수");
r = await get("/anything");
ok(r.status === 404, "화이트리스트 밖 경로 404");
r = await get("/holdings?isbn=123");
ok(r.status === 400, "ISBN 형식 오류 400");
r = await get("/search?q=a");
ok(r.status === 400, "검색어 1글자 400");
r = await get("/health", { Origin: "https://evil.example" });
ok(r.status === 403, "허용 밖 Origin 403");
r = await get("/health", { Origin: "https://altarry-prog.github.io" });
ok(r.status === 200 && r.h["access-control-allow-origin"] === "https://altarry-prog.github.io", "허용 Origin — CORS 헤더");
const noKey = await worker.fetch(new Request("https://relay.test/health"), {});
ok(noKey.status === 503, "키 미설정 503");
r = await get("/holdings?isbn=9788972756194");
ok(r.body.cached === true, "같은 ISBN 재조회 — 캐시");
ok(!calls.some(u => !u.includes("authKey=FAKE")), "모든 상류 호출에 키가 실림(URL에만)");
// 10/16 실측 반영: https가 막히면 매뉴얼의 http 주소로 넘어간다(다른 ISBN이라 캐시 없이 새로 조회)
const realFetch = globalThis.fetch;
globalThis.fetch = async (url, init) => { if (String(url).startsWith("https://data4library.kr")) throw new TypeError("connection refused"); return realFetch(url, init); };
const before = calls.length;
r = await get("/holdings?isbn=9791161571188");
globalThis.fetch = realFetch;
ok(r.status === 200 && r.body.libs["141065"] === "ok" && calls.slice(before).length > 0 && calls.slice(before).every(u => u.startsWith("http://data4library.kr/api/")),
   "https가 막히면 http(매뉴얼 주소)로 넘어가 같은 결과");
ok(r.body.via === "http", "   통한 주소 종류를 응답에 남김(via: http)");
// 10/16 첫 배포 뒤 보강 ① 기억해 둔 주소(지금은 http)가 답 없이 멈추면, 기다리는 한도 뒤 다른 주소로 넘어간다
globalThis.fetch = (url, init) => String(url).startsWith("http://data4library.kr")
  ? new Promise((_, rej) => init.signal.addEventListener("abort", () => rej(new DOMException("The operation was aborted", "AbortError"))))
  : realFetch(url, init);
let t0 = Date.now();
r = await get("/holdings?isbn=9791190090032", {}, { ...env, NARU_WAIT_MS: "60" });
globalThis.fetch = realFetch;
ok(r.status === 200 && r.body.via === "https" && r.body.libs["141065"] === "ok" && Date.now() - t0 < 3000,
   "멈춘 주소는 한도(점검 60ms) 뒤 끊고 다른 주소로 — 같은 결과");
// ② 정보나루가 오류 문구(호출 한도 초과 등)를 주면 16관 「없음」으로 바꾸지 않고 502 — 키는 싣지 않는다
globalThis.fetch = async (url) => { calls.push(url); return new Response(JSON.stringify({ response: { error: "일일 호출 한도 초과 FAKE" } }), { status: 200 }); };
r = await get("/holdings?isbn=9791190090018");
ok(r.status === 502 && r.body.error === "upstream" && !r.body.libs && r.body.detail.some(x => x.startsWith("naru:")) && !JSON.stringify(r.body).includes("FAKE"),
   "정보나루 오류 문구 → 502(「없음」으로 바꾸지 않음) · 실패 종류만 · 키 없음");
// ③ 상류가 계속 막히면 외부 호출을 45회 안에서 멈추고, 실패 종류만 알린다(키·주소 없음)
let tries = 0;
globalThis.fetch = async () => { tries++; throw new TypeError("Network connection lost. https://data4library.kr/api/x?authKey=FAKE"); };
r = await get("/holdings?isbn=9791190090025");
globalThis.fetch = realFetch;
ok(r.status === 502 && tries > 0 && tries <= 45 && r.body.detail.length > 0
   && !JSON.stringify(r.body).includes("FAKE") && !JSON.stringify(r.body).includes("data4library"),
   `상류 장애 → 502 · 외부 호출 ${tries}회(45회 이하) · 키·주소 없음`);
console.log(`\n중계 점검 ${n}건 통과`);
