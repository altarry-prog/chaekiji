/* 책이지 Solar 상담 창 — 중계(worker.js)의 POST /ask. [2026. 11. 2.]
 *
 * 클로드 계정 없이 상담 비서를 시험한다. 업스테이지 Solar Pro 4가 이용자의 말을 알아듣고,
 * 판정은 원격 판과 같은 consult_request(relay/mcp.js)가 한다. 화면은 docs/ask/ (깃허브 페이지).
 *
 * 11. 1.~2. Solar 실측과 같은 것: 지시문(server/prompts/상담비서-지시문.md에 받을 도서관·언어를 채운 것),
 *   모델에 보이는 도구(consult_request 하나), 받을 도서관·언어는 화면이 정한 값으로 고정하고 회원 칸은 빼는 규칙
 *   (server/hosts/ollama_host.py와 같음), 온도 0, 도구 한도에 닿았을 때 하는 말.
 * 다른 것: 판정 자료가 원격 판과 같다(그날 새벽 자료에 있으면 그것, 없으면 정보나루를 그 자리에서). 실측은 시연 도서 5종만 썼다.
 *   도구 호출은 2번까지(실측 호스트는 6번까지) — 요청 1건의 외부 호출이 Cloudflare 무료 요금제 한도(50) 안에 들도록.
 * 지키는 것: 키는 Cloudflare 비밀값(UPSTAGE_API_KEY)에만 둔다. 묻는 글은 답을 만들려고 업스테이지에 보내지만
 *   중계는 저장하지 않고 기록에도 남기지 않는다. 전화번호·회원번호처럼 보이는 숫자가 있으면 모델을 부르지 않는다.
 *   한 IP 10분 6번, 한 실행 공간 하루 300번. 외부 호출은 모델 4번 + 매일 갱신 자료·정보나루 42번 안. */
import { CFG, TOOLS, PROMPT_BODY } from "./mcp_data.js";
import { consultRequest } from "./mcp.js";

export const ASK_MODEL = "solar-pro4";
const UPSTAGE_URL = "https://api.upstage.ai/v1/chat/completions";
const MAX_TEXT = 300;
const MAX_MODEL_CALLS = 4;          // 모델 부르기(다시 시도 포함)
const MAX_TOOL_CALLS = 2;           // consult_request
export const NARU_CAP = 42;         // 매일 갱신 자료 + 정보나루(요청 1건)
const MODEL_WAIT_MS = 25000;
export const ASK_PER_IP = 6;        // 10분
export const ASK_PER_DAY = 300;     // 실행 공간 하나 기준(Cloudflare가 여러 곳에서 돌리면 합은 더 클 수 있다)
export const LANGS = ["ko", "en", "vi", "zh", "ja"];
const LIMIT_SENTENCE = "도구 호출 한도에 닿았습니다. 지금까지의 결과로 최종 답을 주세요.";   // ollama_host.py와 같은 말

const TOOL_DEFS = TOOLS.filter(t => t.name === "consult_request").map(t => ({
  type: "function", function: { name: t.name, description: t.description, parameters: t.inputSchema } }));
const PICKUPS = [...Object.keys(CFG.libraries), ...(CFG.pickup_points || [])];

export function systemPrompt(pickup, lang) {                    // mcp.js promptText와 같은 채움
  return PROMPT_BODY.split("{pickup}").join(pickup).split("{lang}").join(lang).trim();
}

// 이용자가 쓴 글자로 언어를 짐작한다(화면에서 「자동」을 골랐을 때). 한글이 있으면 한국어.
export function guessLang(t) {
  const s = String(t || "");
  if (/[가-힣]/.test(s)) return "ko";
  if (/[぀-ヿ]/.test(s)) return "ja";
  if (/[一-鿿]/.test(s)) return "zh";
  if (/[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]/i.test(s)) return "vi";
  if (/[a-z]/i.test(s)) return "en";
  return "ko";
}

// 개인정보로 보이는 글 — 있으면 모델을 부르지 않는다. ISBN(978·979로 시작하는 13자리)은 책 번호라 통과.
const PERSONAL = [
  /01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}/,                      // 휴대전화
  /(?:^|\D)0\d{1,2}[-\s.)]\s?\d{3,4}[-\s.]\d{4}/,              // 지역 번호 전화
  /\d{6}\s?-\s?[1-8]\d{6}/,                                    // 주민등록번호 꼴
  /[\w.+-]+@[\w-]+\.[\w.-]+/,                                  // 전자우편
  /(?:회원|카드|이용자)\s*번호/,                                 // 회원번호·카드번호라고 밝힌 것
];
export function looksPersonal(text) {
  const t = String(text || "").replace(/97[89](?:[-\s]?\d){10}/g, " ");
  if (PERSONAL.some(r => r.test(t))) return true;
  return /\d{8,}/.test(t.replace(/(\d)[-\s](?=\d)/g, "$1"));     // 8자리 넘는 번호(회원번호·카드번호 꼴)
}

const askMem = { hits: new Map(), day: "", n: 0 };
export function askAllow(ip, now = Date.now()) {
  const day = new Date(now + 9 * 3600e3).toISOString().slice(0, 10);
  if (askMem.day !== day) { askMem.day = day; askMem.n = 0; askMem.hits.clear(); }
  if (askMem.n >= ASK_PER_DAY) return "day-limit";
  const win = 600e3, arr = (askMem.hits.get(ip) || []).filter(t => now - t < win);
  if (arr.length >= ASK_PER_IP) return "rate-limit";
  arr.push(now); askMem.hits.set(ip, arr); askMem.n++;
  return null;
}
export function _resetAskForTest() { askMem.hits.clear(); askMem.day = ""; askMem.n = 0; }

class AskError extends Error { constructor(code, detail) { super(code); this.code = code; this.detail = detail || []; } }
const sleep = ms => new Promise(r => setTimeout(r, ms));

// 업스테이지 한 번(오픈AI 모양). 키는 머리글에만 싣고 오류 글에는 남기지 않는다.
async function solar(env, messages, mode, budget) {
  const body = { model: ASK_MODEL, messages, temperature: 0 };
  if (mode !== "plain") body.tools = TOOL_DEFS;
  if (mode === "final") body.tool_choice = "none";
  let last = "no-call";
  for (let attempt = 0; attempt < 2; attempt++) {
    if (budget.model >= MAX_MODEL_CALLS) throw new AskError("model", [last, "budget"]);
    budget.model++;
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), MODEL_WAIT_MS);
    const t0 = Date.now();
    let r;
    try {
      r = await fetch(UPSTAGE_URL, { method: "POST", signal: ctl.signal, body: JSON.stringify(body),
        headers: { Authorization: `Bearer ${env.UPSTAGE_API_KEY}`, "Content-Type": "application/json" } });
    } catch (e) {
      last = (e && e.name) || "Error";
      if (last === "AbortError") throw new AskError("model", ["timeout"]);
      continue;                                              // 연결이 끊기면 한 번 더
    } finally { clearTimeout(timer); budget.model_ms += Date.now() - t0; }
    if (r.status === 429 || r.status >= 500) { last = `http:${r.status}`; if (!attempt) await sleep(1500); continue; }   // 몰리면 잠깐 쉬고 한 번 더
    if (r.status === 400 && mode === "final") return solar(env, messages, "plain", budget);   // tool_choice를 받지 않으면 도구 없이
    if (!r.ok) throw new AskError("model", [`http:${r.status}`]);
    let d;
    try { d = await r.json(); } catch (e) { throw new AskError("model", ["not-json"]); }
    const msg = ((d.choices || [])[0] || {}).message;
    if (!msg) throw new AskError("model", ["no-message"]);
    const u = d.usage || {};
    budget.prompt_tokens += Number(u.prompt_tokens) || 0;
    budget.completion_tokens += Number(u.completion_tokens) || 0;
    if (d.model) budget.served = String(d.model);
    return msg;
  }
  throw new AskError("model", [last]);
}

function parseArgs(a) {
  if (a && typeof a === "object") return { ...a };
  try { const o = JSON.parse(a || "{}"); return o && typeof o === "object" ? o : { utterance: String(a) }; }
  catch (e) { return { utterance: String(a) }; }
}

// 화면에 돌려줄 도구 판정 요점(모델의 답과 나란히 보여 준다)
function toolBrief(o) {
  const b = o.book || {};
  return { route: o.route, route_label: o.route_label, pickup: o.pickup,
           book: o.book ? { title: b.title, author: b.author, publisher: b.publisher, year: b.year, isbn13: b.isbn13 } : null,
           asof: (o.availability || {}).asof || null, available_at: (o.availability || {}).available_at || [],
           loaned_at: (o.availability || {}).loaned_at || [], official_link: o.official_link || null,
           notice: o.notice || "", desk_memo: o.desk_memo || "",
           candidate_books: (o.candidate_books || []).slice(0, 3).map(x => ({ title: x.title, author: x.author, publisher: x.publisher, year: x.year })) };
}

export async function askConsult({ text, pickup, lang }, env, deps) {
  const t0 = Date.now();
  const messages = [{ role: "system", content: systemPrompt(pickup, lang) }, { role: "user", content: text }];
  const ctx = deps.newCtx(); ctx.cap = NARU_CAP;
  const budget = { model: 0, model_ms: 0, prompt_tokens: 0, completion_tokens: 0, served: ASK_MODEL };
  const calls = [];
  let last = null, answer = "", toolMs = 0;
  for (let round = 0; round < 3; round++) {
    const final = calls.length >= MAX_TOOL_CALLS || round === 2;
    if (final && round > 0) messages.push({ role: "user", content: LIMIT_SENTENCE });
    const msg = await solar(env, messages, final ? "final" : "tools", budget);
    const tcs = final ? [] : (msg.tool_calls || []).filter(tc => tc && tc.function && tc.function.name);
    if (!tcs.length) { answer = String(msg.content || "").trim(); break; }
    messages.push({ role: "assistant", content: msg.content || null, tool_calls: tcs.map((tc, i) => ({
      id: tc.id || `call_${round}_${i}`, type: "function",
      function: { name: tc.function.name, arguments: typeof tc.function.arguments === "string" ? tc.function.arguments : JSON.stringify(tc.function.arguments || {}) } })) });
    for (const [i, tc] of tcs.entries()) {
      let content;
      if (tc.function.name !== "consult_request") {
        content = JSON.stringify({ error: `없는 도구: ${tc.function.name}`, available: ["consult_request"] });
      } else if (calls.length >= MAX_TOOL_CALLS) {
        content = JSON.stringify({ error: LIMIT_SENTENCE });
      } else {
        const args = parseArgs(tc.function.arguments);
        args.pickup = pickup; args.lang = lang;                // 받을 도서관·언어는 화면이 정한 값(호스트와 같은 규칙)
        delete args.user; delete args.member;                  // 회원 토큰·회원 조건은 받지 않는다
        const s0 = Date.now();
        try {
          const out = await consultRequest(args, deps, ctx);
          last = out; content = JSON.stringify(out, null, 1);
          calls.push({ utterance: String(args.utterance || ""), route: out.route });
        } catch (e) {
          content = `${(e && e.kind) || "Error"}: ${e && e.message}`;
          calls.push({ utterance: String(args.utterance || ""), error: true });
        }
        toolMs += Date.now() - s0;
      }
      messages.push({ role: "tool", tool_call_id: tc.id || `call_${round}_${i}`, content });
    }
  }
  return { ok: true, answer, tool: last ? toolBrief(last) : null, tool_calls: calls.map(c => ({ utterance: c.utterance, route: c.route || null, error: !!c.error })),
           model: budget.served, pickup, lang, ms: Date.now() - t0, model_ms: budget.model_ms, tool_ms: toolMs,
           usage: { prompt_tokens: budget.prompt_tokens, completion_tokens: budget.completion_tokens, model_calls: budget.model },
           data_calls: ctx.n };
}

// POST /ask — 본문 {text, pickup, lang(ko|en|vi|zh|ja|auto)}
export async function handleAsk(req, env, ip, deps, headers) {
  const out = (obj, status) => new Response(JSON.stringify(obj), { status, headers });
  let body;
  try { body = JSON.parse(await req.text()); } catch (e) { return out({ error: "json" }, 400); }
  const text = String((body && body.text) || "").replace(/\s+/g, " ").trim();
  if (!text) return out({ error: "text", message: "물을 말을 적어 주세요." }, 400);
  if (text.length > MAX_TEXT) return out({ error: "text", message: `${MAX_TEXT}자 안으로 줄여 주세요.` }, 400);
  if (looksPersonal(text)) return out({ error: "personal-info", message: "전화번호·회원번호처럼 보이는 글이 있어 묻지 않았습니다. 책 이름과 받을 도서관만 적어 주세요." }, 400);
  const pickup = String((body && body.pickup) || CFG.home_library).trim();
  if (!PICKUPS.includes(pickup)) return out({ error: "pickup", message: "받을 도서관을 목록에서 골라 주세요." }, 400);
  const want = String((body && body.lang) || "auto");
  const lang = LANGS.includes(want) ? want : guessLang(text);
  const why = askAllow(ip);
  if (why) return out({ error: why, message: why === "day-limit" ? "오늘 시험 한도에 닿았습니다. 내일 다시 써 주세요." : "잠시 뒤에 다시 물어 주세요(10분에 6번까지)." }, 429);
  try {
    const r = await askConsult({ text, pickup, lang }, env, deps);
    return out({ ...r, lang_guessed: !LANGS.includes(want) }, 200);
  } catch (e) {
    const code = e instanceof AskError ? e.code : "error";
    return out({ error: code, detail: (e && e.detail) || [], message: "지금은 답을 만들지 못했습니다. 잠시 뒤에 다시 물어 주세요." }, 502);
  }
}
