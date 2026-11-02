// worker.js 점검 — 정보나루를 흉내 낸 fetch로 네 경로를 돌려 본다(네트워크·키 불필요).
// 실행: node relay/test_worker.mjs
import worker, { naruKeys, keyErrorKind, heldKeys, _resetKeysForTest } from "./worker.js";
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
    const held = ["141321", "141065"].includes(code);          // 소장관 둘: 상동(대출 중)·꿈빛(대출 가능)
    body = { response: { result: { hasBook: held ? "Y" : "N", loanAvailable: code === "141065" ? "Y" : "N" } } };
  } else if (api === "srchBooks") {
    const t = u.searchParams.get("title") || "";
    body = { response: { docs: t.includes("채식")
      ? [{ doc: { isbn13: "9788936433598", bookname: "채식주의자", authors: "한강 지음", publisher: "창비", publication_year: "2007" } }]
      : t.includes("흔한")                                        // [10/19] 권차(vol) 칸이 있는 서지(모의)
      ? [{ doc: { isbn13: "9790000000103", bookname: "흔한남매", authors: "원작: 흔한남매", publisher: "미래엔", publication_year: "2019", vol: "1" } }] : [] } };
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
ok(r.status === 200 && r.body.libs["141065"] === "ok" && r.body.libs["141321"] === "busy" && r.body.libs["141248"] === "none" && r.body.calls === 16
   && !calls.some(u => u.includes("libSrchByBook") && u.includes("dtl_region")),
   "/holdings — 16관 bookExist를 한꺼번에(소장관 목록 조회 없이) · ok/busy/none 매핑");
ok(/^\d{4}-\d{2}-\d{2}$/.test(r.body.asof), "   asof 날짜(YYYY-MM-DD)");
r = await get("/search?q=채식주의자 있나요");
ok(r.status === 200 && r.body.docs.length === 1 && r.body.docs[0].isbn13 === "9788936433598", "/search?q= — 서지 1건(제목 부분일치)");
r = await get("/search?q=흔한남매");
ok(r.status === 200 && r.body.docs[0].vol === "1" && calls.some(u => String(u).includes("srchBooks") && String(u).includes("pageSize=10")) &&
   !("vol" in (await get("/search?q=채식주의자 있나요")).body.docs[0]),
   "[10/19] /search?q= — 상위 10건(pageSize=10) · 권차(vol)가 있으면 함께 주고 없으면 칸을 두지 않음");
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
   "매뉴얼의 http 주소로 부른다 — https가 막혀 있어도 같은 결과");
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
_resetKeysForTest();                                       // 위에서 한도 초과로 쉬게 한 키를 풀어 둔다(아래 시험이 같은 키를 씀)
// ③ 상류가 계속 막히면 외부 호출을 45회 안에서 멈추고, 실패 종류만 알린다(키·주소 없음)
let tries = 0;
globalThis.fetch = async () => { tries++; throw new TypeError("Network connection lost. https://data4library.kr/api/x?authKey=FAKE"); };
r = await get("/holdings?isbn=9791190090025");
globalThis.fetch = realFetch;
ok(r.status === 502 && tries > 0 && tries <= 45 && r.body.detail.length > 0
   && !JSON.stringify(r.body).includes("FAKE") && !JSON.stringify(r.body).includes("data4library"),
   `상류 장애 → 502 · 외부 호출 ${tries}회(45회 이하) · 키·주소 없음`);

// ── [11/2 오후] 정보나루 키 넷을 차례로(NARU_KEY → NARU_KEY2 → NARU_KEY3 → NARU_KEY4) ──
// 모의 정보나루: FAKE만 정상, QUOTA는 한도 초과, IDLE은 승인 전, ODD1·ODD2는 키와 상관없는 같은 오류, ODD3만 다른 오류
const keyMock = async (url) => {
  const k = new URL(url).searchParams.get("authKey");
  if (k === "FAKE") return realFetch(url);                  // 정상 키 — 처음 모의 정보나루(호출 기록은 그쪽이 남김)
  calls.push(url);
  const err = { QUOTA: "일일 호출 한도를 초과했습니다", IDLE: "API 활성화 상태가 아닙니다", ODD1: "잘못된 요청", ODD2: "잘못된 요청", ODD3: "알 수 없는 오류" }[k];
  if (err) return new Response(JSON.stringify({ response: { error: err } }), { status: 200 });
  return new Response("{}", { status: 403 });
};
ok(keyErrorKind("일일 호출 한도를 초과했습니다") === "quota" && keyErrorKind("API 활성화 상태가 아닙니다") === "key" &&
   keyErrorKind("인증키가 유효하지 않습니다") === "key" && keyErrorKind("요청 시간 초과") === null && keyErrorKind("잘못된 요청") === null,
   "키 오류 가르기 — 한도 초과는 quota, 승인 전·무효는 key, 「시간 초과」 같은 그 밖의 오류는 키 탓으로 보지 않음");
ok(JSON.stringify(naruKeys({ NARU_KEY: "A", NARU_KEY2: "", NARU_KEY3: "A", NARU_KEY4: "B" }).map(k => k.name)) === '["NARU_KEY","NARU_KEY4"]',
   "키 순서 NARU_KEY → NARU_KEY2 → NARU_KEY3 → NARU_KEY4 · 빈 칸과 같은 값은 한 번만");
// ① 첫 키가 한도 초과면 같은 호출을 다음 키로, 그날은 그 키를 건너뜀(이름만 알림)
_resetKeysForTest(); globalThis.fetch = keyMock;
let e2 = { NARU_KEY: "QUOTA", NARU_KEY2: "FAKE" }, kb = calls.length;
r = await get("/search?q=" + encodeURIComponent("채식주의자 첫째"), {}, e2);
let used = calls.slice(kb).map(u => new URL(u).searchParams.get("authKey"));
let r2 = await get("/search?q=" + encodeURIComponent("채식주의자 한강"), {}, e2);
let used2 = calls.slice(kb + used.length).map(u => new URL(u).searchParams.get("authKey"));
let hh = await get("/health", {}, e2);
ok(r.status === 200 && r.body.docs.length === 1 && r.body.key_name === "NARU_KEY2" && JSON.stringify(used) === '["QUOTA","FAKE"]' &&
   r2.status === 200 && used2.length > 0 && !used2.includes("QUOTA") &&
   JSON.stringify(hh.body.naru_keys) === '["NARU_KEY","NARU_KEY2"]' && hh.body.naru_held.NARU_KEY === "quota" &&
   !JSON.stringify([r.body, r2.body, hh.body]).includes("QUOTA") && !JSON.stringify(hh.body).includes("FAKE"),
   "첫 키가 한도 초과 → 같은 호출을 둘째 키로 · 그날은 첫 키를 건너뜀 · /health는 키 이름과 까닭만");
// ② 승인 전 키(NARU_KEY3)는 1시간 건너뛰고 다음 키(NARU_KEY4)로 — 승인되면 1시간 안에 다시 쓰임
_resetKeysForTest();
r = await get("/search?q=" + encodeURIComponent("채식주의자 둘째"), {}, { NARU_KEY3: "IDLE", NARU_KEY4: "FAKE" });
let held = heldKeys();
ok(r.status === 200 && r.body.key_name === "NARU_KEY4" && held.NARU_KEY3 === "key" && !heldKeys(Date.now() + 3601e3).NARU_KEY3,
   "승인 전 키 → 다음 키로 · 1시간만 건너뜀(승인되면 다시 배포 없이 쓰임)");
// ③ 두 키가 같은 오류(키와 상관없는 오류)면 멈추고 아무 키도 막지 않음 — 키 넷을 헛되이 쉬게 하지 않음
_resetKeysForTest(); kb = calls.length;
r = await get("/search?q=" + encodeURIComponent("채식주의자 셋째"), {}, { NARU_KEY: "ODD1", NARU_KEY2: "ODD2", NARU_KEY3: "FAKE" });
used = calls.slice(kb).map(u => new URL(u).searchParams.get("authKey"));
ok(r.status === 502 && JSON.stringify(used) === '["ODD1","ODD2"]' && Object.keys(heldKeys()).length === 0 && !JSON.stringify(r.body).includes("ODD"),
   "두 키가 같은 오류 → 셋째 키까지 가지 않고 502 · 어떤 키도 막지 않음");
// ④ 앞 키만 낯선 오류였고 다음 키가 되면 앞 키만 10분 쉼
_resetKeysForTest();
r = await get("/search?q=" + encodeURIComponent("채식주의자 넷째"), {}, { NARU_KEY: "ODD3", NARU_KEY2: "FAKE" });
held = heldKeys();
ok(r.status === 200 && r.body.key_name === "NARU_KEY2" && held.NARU_KEY === "other" && !heldKeys(Date.now() + 601e3).NARU_KEY,
   "앞 키만 낯선 오류 → 다음 키로 · 앞 키는 10분만 쉼");
// ⑤ 16관 조회: 첫 키가 막혔을 때 16번을 한꺼번에 막힌 키로 보내지 않음(한 관으로 키를 정한 뒤 나머지)
_resetKeysForTest(); kb = calls.length;
r = await get("/holdings?isbn=9791190090049", {}, { NARU_KEY: "QUOTA", NARU_KEY2: "FAKE" });
used = calls.slice(kb).map(u => new URL(u).searchParams.get("authKey"));
ok(r.status === 200 && r.body.libs["141065"] === "ok" && r.body.key_name === "NARU_KEY2" && used.filter(k => k === "QUOTA").length === 1 && used.length === 17,
   `16관 조회 — 막힌 첫 키는 1번만 부르고 둘째 키로 16번(외부 호출 ${used.length}번)`);
// ⑥ 넣어 둔 키가 모두 쉬는 중이면 정보나루를 부르지 않고 502
kb = calls.length;
r = await get("/search?q=" + encodeURIComponent("아몬드"), {}, { NARU_KEY: "QUOTA" });
ok(r.status === 502 && calls.length === kb && r.body.detail.includes("keys:held"),
   "모든 키가 쉬는 중 → 정보나루를 부르지 않고 502(keys:held)");
globalThis.fetch = realFetch; _resetKeysForTest();

console.log(`\n중계 점검 ${n}건 통과`);
