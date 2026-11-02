// Solar 상담 창(POST /ask, relay/ask.js) 점검 — 업스테이지와 정보나루를 흉내 낸 fetch로 돌린다(네트워크·키 불필요).
// 실행: node relay/test_ask.mjs
import worker from "./worker.js";
import { _resetAskForTest, askAllow, guessLang, looksPersonal, ASK_PER_IP, ASK_PER_DAY, NARU_CAP } from "./ask.js";
import { mockFetch } from "./test_naru_mock.mjs";
import { readFileSync } from "node:fs";

const sc = JSON.parse(readFileSync(new URL("./test_mcp_scenarios.json", import.meta.url), "utf-8"));
const today = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
const log = [];
const naru = mockFetch(sc, { ...sc.snapshot, asof: today }, log);
const UP = "https://api.upstage.ai/v1/chat/completions";
let script = [];                 // 모의 Solar가 차례로 돌려줄 답(객체 · 함수(요청 본문) · Response)
const seen = [];                 // 모의 Solar가 받은 요청
globalThis.fetch = async (url, init = {}) => {
  if (String(url) === UP) {
    const body = JSON.parse(init.body);
    seen.push({ body, auth: (init.headers || {}).Authorization });
    let step = script.shift();
    if (typeof step === "function") step = step(body);
    if (!step) return new Response(JSON.stringify({ error: "no script" }), { status: 500 });
    if (step instanceof Response) return step;
    return new Response(JSON.stringify({ model: "solar-pro4-260806", choices: [{ message: step }],
                                         usage: { prompt_tokens: 3000, completion_tokens: 250 } }), { status: 200 });
  }
  return naru(url, init);
};
const env = { NARU_KEY: "FAKE", UPSTAGE_API_KEY: "UPFAKE" };
const ORIGIN = "https://altarry-prog.github.io";
let ipn = 0;
const ask = async (body, { origin = ORIGIN, e = env, ip, method = "POST" } = {}) => {
  const headers = { "Content-Type": "application/json", "CF-Connecting-IP": ip || `10.0.0.${++ipn}` };
  if (origin) headers.Origin = origin;
  const r = await worker.fetch(new Request("https://relay.test/ask", { method, headers,
    body: method === "POST" ? (typeof body === "string" ? body : JSON.stringify(body)) : undefined }), e);
  const text = await r.text();
  return { status: r.status, body: text ? JSON.parse(text) : null, h: Object.fromEntries(r.headers), text };
};
const toolCall = (args, id = "call_1") => ({ role: "assistant", content: null,
  tool_calls: [{ id, type: "function", function: { name: "consult_request", arguments: JSON.stringify(args) } }] });
const say = text => ({ role: "assistant", content: text });
let n = 0; const ok = (c, m) => { if (!c) { console.error("  ✗ " + m); process.exit(1); } n++; console.log("  ✓ " + m); };

// 1. 규약·보호 장치(모델을 부르지 않음)
let raw = await worker.fetch(new Request("https://relay.test/ask", { method: "OPTIONS", headers: { Origin: ORIGIN } }), env);
ok(raw.status === 204 && raw.headers.get("Access-Control-Allow-Origin") === ORIGIN && raw.headers.get("Access-Control-Allow-Methods").includes("POST"),
   "OPTIONS(사전 확인) → 204 · 시연 웹 출처만 허용");
let r = await ask(null, { method: "GET" });
ok(r.status === 405 && r.h.allow === "POST", "GET /ask → 405(POST만)");
r = await ask({ text: "나미야 잡화점의 기적" }, { e: { NARU_KEY: "FAKE" } });
ok(r.status === 503 && r.body.error === "ask-not-configured" && seen.length === 0, "Solar 키가 없으면 503 · 모델을 부르지 않음");
r = await ask({ text: "나미야 잡화점의 기적" }, { origin: "" });
const r2 = await ask({ text: "나미야 잡화점의 기적" }, { origin: "https://evil.example" });
ok(r.status === 403 && r2.status === 403 && !r2.h["access-control-allow-origin"] && seen.length === 0, "출처 없음·허용 밖 출처 → 403(화면에서만 부름)");
r = await ask("{not json");
const e1 = await ask({ text: "   " }), e2 = await ask({ text: "가".repeat(301) }), e3 = await ask({ text: "나미야 잡화점의 기적", pickup: "서울" });
ok(r.status === 400 && e1.body.error === "text" && e2.body.error === "text" && e2.body.message.includes("300") && e3.body.error === "pickup" && seen.length === 0,
   "JSON 아님·빈 글·300자 넘음·목록 밖 받을 도서관 → 400 · 모델을 부르지 않음");
for (const t of ["나미야 잡화점의 기적, 010-1234-5678로 연락 주세요", "회원번호 2231 소년이 온다", "a@b.kr 로 알려 주세요"]) {
  r = await ask({ text: t });
  ok(r.status === 400 && r.body.error === "personal-info" && seen.length === 0, `개인정보로 보이는 글 → 400 · 모델을 부르지 않음(「${t.slice(0, 14)}…」)`);
}
ok(!looksPersonal("ISBN 9788972756194 책 있나요") && !looksPersonal("978-89-7275-619-4 있어요?") && !looksPersonal("1984 조지 오웰") &&
   !looksPersonal("82년생 김지영 상동에서") && looksPersonal("12345678 회원") && looksPersonal("02-123-4567"),
   "개인정보 거름 — ISBN·제목 속 숫자는 통과, 8자리 넘는 번호·전화번호는 막음");
ok(guessLang("나미야 잡화점의 기적") === "ko" && guessLang("Do you have Human Acts by Han Kang?") === "en" &&
   guessLang("Tôi muốn mượn sách của Han Kang.") === "vi" && guessLang("我想借《解忧杂货店》") === "zh" &&
   guessLang("『ナミヤ雑貨店の奇蹟』を借りたいです") === "ja" && guessLang("Human Acts 있어요?") === "ko",
   "언어 짐작(「자동」) — 한글이 있으면 한국어, 가나 → 일본어, 한자 → 중국어, 베트남 글자 → 베트남어, 그 밖 로마자 → 영어");

// 2. 보통 흐름: 모델이 도구를 한 번 부르고 답한다
seen.length = 0; log.length = 0;
script = [
  toolCall({ utterance: "나미야 잡화점의 기적", pickup: "꿈빛", lang: "en", member: { overdue: true }, user: "tok" }),
  body => {
    const t = body.messages[body.messages.length - 1];
    const o = JSON.parse(t.content);
    return t.role === "tool" && t.tool_call_id === "call_1" && o.pickup === "역곡" && o.lang === "ko" && !/회원 조건: 사서 입력/.test(o.desk_memo)
      ? say("① 판정: 관내 상호대차\n② 안내문: …\n③ 접수 메모: …") : say("도구 결과가 기대와 다름");
  },
];
r = await ask({ text: "나미야 잡화점의 기적 빌리고 싶어요", pickup: "역곡", lang: "auto" });
const b = r.body;
ok(r.status === 200 && b.ok && b.answer.startsWith("① 판정: 관내 상호대차") && b.tool_calls.length === 1 && b.tool_calls[0].utterance === "나미야 잡화점의 기적",
   "보통 흐름 — 모델이 consult_request를 한 번 부르고 답함");
ok(b.tool.route === "ill" && b.tool.book.isbn13 === "9788972756194" && b.tool.asof === today && b.tool.official_link.includes("9788972756194") &&
   b.tool.notice.includes("역곡도서관에는 대출 중이지만") && b.tool.desk_memo.startsWith("도서: "),
   "   도구가 정한 판정(갈래·책·조회일·누리집 주소·안내문·접수 메모)을 답과 따로 돌려줌");
ok(b.pickup === "역곡" && b.lang === "ko" && b.lang_guessed === true && b.model === "solar-pro4-260806" && b.usage.model_calls === 2 &&
   b.usage.prompt_tokens === 6000 && b.data_calls <= 1 && log.every(u => !u.includes("data4library")),
   "   받을 도서관·언어(짐작) · 실제 모델 이름 · 토큰 · 시연 도서는 새벽 자료로(정보나루 호출 0)");
const q0 = seen[0].body;
ok(q0.model === "solar-pro4" && q0.temperature === 0 && q0.tools.length === 1 && q0.tools[0].function.name === "consult_request" &&
   q0.messages[0].role === "system" && q0.messages[0].content.includes("받을 도서관은 「역곡」, 이용자 언어는 「ko」") &&
   !q0.messages[0].content.includes("{pickup}") && q0.messages[1].content === "나미야 잡화점의 기적 빌리고 싶어요" && !("tool_choice" in q0),
   "   모델에 가는 것 — 실측과 같은 지시문(받을 도서관·언어 채움) · 도구 consult_request 하나 · 온도 0");
ok(seen.every(s => s.auth === "Bearer UPFAKE") && !r.text.includes("UPFAKE") && !r.text.includes("FAKE"),
   "   키는 업스테이지 머리글에만 · 응답에 키 없음");

// 3. 되물음: 도구를 부르지 않고 답한다
seen.length = 0;
script = [say("어느 책인지 저자나 대략의 내용을 조금 더 알려 주시겠어요?")];
r = await ask({ text: "한강 책 빌리고 싶어요" });
ok(r.status === 200 && r.body.tool === null && r.body.tool_calls.length === 0 && r.body.answer.includes("알려 주시겠어요") && seen.length === 1,
   "되물음 — 도구 없이 답하면 판정 상자 없음(모델 1번)");

// 4. 외국어 + 다시 부르기: 못 찾으면 한국어판 제목으로 한 번 더 → 한도에 닿으면 도구 없이 마지막 답
seen.length = 0;
script = [
  toolCall({ utterance: "The Vegetarian" }, "c1"),
  toolCall({ utterance: "채식주의자" }, "c2"),
  body => body.tool_choice === "none" && body.messages[body.messages.length - 1].content.startsWith("도구 호출 한도에 닿았습니다")
    ? say("① Verdict: available at Sangdong ...") : say("한도 처리 다름"),
];
r = await ask({ text: "Do you have The Vegetarian by Han Kang? Sangdong please.", pickup: "상동", lang: "auto" });
ok(r.status === 200 && r.body.lang === "en" && r.body.tool_calls.map(c => c.route).join() === "unknown,visit" && r.body.tool.route === "visit" &&
   r.body.tool.book.isbn13 === "9788936433598" && r.body.answer.startsWith("① Verdict") && seen.length === 3 &&
   seen[0].body.messages[0].content.includes("이용자 언어는 「en」"),
   "외국어(영어 짐작) — 못 찾음 → 한국어판 제목으로 다시 → 도구 2번 한도 뒤 도구 없이 마지막 답(실측 호스트와 같은 말)");

// 5. 한 답에 도구 호출 3개 → 2개만 돌리고 셋째는 한도 알림, 모든 호출에 결과를 붙인다
seen.length = 0;
script = [
  { role: "assistant", content: null, tool_calls: ["c1", "c2", "c3"].map((id, i) => ({ id, type: "function",
    function: { name: i === 2 ? "check_availability" : "consult_request", arguments: JSON.stringify({ utterance: "채식주의자" }) } })) },
  body => {
    const tm = body.messages.filter(m => m.role === "tool");
    return say(tm.map(m => m.tool_call_id).join() === "c1,c2,c3" && tm[2].content.includes("없는 도구") ? "ok" : "어긋남");
  },
];
r = await ask({ text: "채식주의자 있어요?" });
ok(r.status === 200 && r.body.answer === "ok" && r.body.tool_calls.length === 2, "한 답에 호출 여럿 — consult_request만 2번까지, 없는 도구는 오류로 알림");

// 6. 업스테이지 오류: 401은 바로 502, 429는 한 번 쉬고 다시
seen.length = 0;
script = [new Response(JSON.stringify({ error: { message: "invalid api key UPFAKE" } }), { status: 401 })];
r = await ask({ text: "나미야 잡화점의 기적" });
ok(r.status === 502 && r.body.error === "model" && r.body.detail.includes("http:401") && !r.text.includes("UPFAKE") && seen.length === 1,
   "업스테이지 401 → 502 · 실패 종류만(키·업스테이지 글 없음)");
seen.length = 0;
script = [new Response("{}", { status: 429 }), say("다시 해서 답함")];
r = await ask({ text: "나미야 잡화점의 기적" });
ok(r.status === 200 && r.body.answer === "다시 해서 답함" && seen.length === 2 && r.body.usage.model_calls === 2, "업스테이지 429 → 잠깐 쉬고 한 번 더");
seen.length = 0;
script = [toolCall({ utterance: "채식주의자" }, "c1"), toolCall({ utterance: "채식주의자" }, "c2"),
          new Response("{}", { status: 400 }), body => ("tools" in body || "tool_choice" in body) ? say("도구가 남음") : say("도구 없이 답함")];
r = await ask({ text: "채식주의자" });
ok(r.status === 200 && r.body.answer === "도구 없이 답함" && seen.length === 4 && r.body.usage.model_calls === 4,
   "마지막 답에서 tool_choice를 받지 않으면(400) 도구 없이 다시 · 모델 호출 4번 안");

// 7. 외부 호출 한도: 도구 2번이 모두 정보나루로 가도 요청 1건이 50번(Cloudflare 무료 요금제) 안
seen.length = 0; log.length = 0;
script = [toolCall({ utterance: "작별하지 않는다" }, "c1"), toolCall({ utterance: "백년의 고독" }, "c2"), say("끝")];
r = await ask({ text: "작별하지 않는다, 백년의 고독" });
const total = seen.length + log.length;
ok(r.status === 200 && r.body.data_calls <= NARU_CAP && total <= 50 && log.some(u => u.includes("data4library")),
   `외부 호출 한도 — 정보나루·새벽 자료 ${log.length}번 + 모델 ${seen.length}번 = ${total}번(50번 안, 자료 몫 ${NARU_CAP}번)`);

// 8. 한 IP 10분 6번 · 실행 공간 하루 300번
_resetAskForTest(); seen.length = 0;
script = Array.from({ length: ASK_PER_IP }, () => say("답"));
let st = [];
for (let i = 0; i <= ASK_PER_IP; i++) st.push((await ask({ text: "나미야 잡화점의 기적" }, { ip: "10.9.9.9" })).status);
r = await ask({ text: "나미야 잡화점의 기적" }, { ip: "10.9.9.9" });
ok(st.slice(0, ASK_PER_IP).every(s => s === 200) && st[ASK_PER_IP] === 429 && r.body.error === "rate-limit" && seen.length === ASK_PER_IP,
   `한 IP 10분 ${ASK_PER_IP}번 → 그다음은 429(모델을 부르지 않음)`);
_resetAskForTest();
let why = null;
for (let i = 0; i < ASK_PER_DAY; i++) why = askAllow(`10.1.${i >> 8}.${i & 255}`) || why;
ok(why === null && askAllow("10.2.0.1") === "day-limit", `하루 ${ASK_PER_DAY}번 뒤에는 day-limit`);
_resetAskForTest();

// 9. /health는 Solar 키가 있는지만 알린다(값 없음)
const h1 = await (await worker.fetch(new Request("https://relay.test/health"), env)).json();
const h2 = await (await worker.fetch(new Request("https://relay.test/health"), { NARU_KEY: "FAKE" })).json();
// 상담 창 전용 정보나루 키(NARU_KEY_ASK)가 있으면 상담 창은 그 키로만 조회한다(모의 정보나루는 FAKE만 받음)
_resetAskForTest(); log.length = 0;
script = [toolCall({ utterance: "파친코" }), say("끝")];
const sep = await ask({ text: "파친코 있어요?" }, { e: { NARU_KEY: "OTHER", NARU_KEY_ASK: "FAKE", UPSTAGE_API_KEY: "UPFAKE" } });
const h3 = await (await worker.fetch(new Request("https://relay.test/health"), { NARU_KEY: "OTHER", NARU_KEY_ASK: "FAKE" })).json();
const naruLog = log.filter(u => u.includes("data4library"));
ok(h1.ask === true && h2.ask === false && !JSON.stringify(h1).includes("UPFAKE") && h1.ask_naru_key === false && h3.ask_naru_key === true &&
   sep.status === 200 && sep.body.tool && sep.body.tool.book && naruLog.length > 0 && naruLog.every(u => u.includes("authKey=FAKE")) && !sep.text.includes("FAKE"),
   "/health — Solar 키·상담 창 전용 정보나루 키 유무만 · 전용 키(NARU_KEY_ASK)가 있으면 상담 창은 그 키로만 조회");

console.log(`\nSolar 상담 창 점검 ${n}건 통과`);
