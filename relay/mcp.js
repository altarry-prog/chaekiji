/* 책이지 원격 상담 비서 — MCP(Streamable HTTP) 판. 중계(worker.js)의 /mcp 경로.
 *
 * claude.ai 「사용자 지정 → 커넥터 → 커스텀 커넥터 추가」에 https://chaekiji-relay.altarry2.workers.dev/mcp 를 넣으면
 * 파이썬·설치 없이 인터넷 창에서 상담 비서를 쓴다(행정망 PC 포함 — 커넥터는 Anthropic 쪽 서버가 부른다).
 *
 * 무엇과 같은가: 파이썬 참조 서버(server/)를 relay 모드로 띄운 것과 같은 판정·같은 안내문을 낸다.
 *   찾기 → 관내 소장·대출(오늘 새벽 매일 갱신 자료 → 없으면 정보나루를 그 자리에서) → 규정 판정 → 안내문 → 접수 메모.
 *   relay/test_mcp_parity.py가 두 판을 같은 입력으로 돌려 맞춰 본다. 설정·픽스처·지시문은 relay/mcp_data.js(자동 생성).
 * 무엇이 다른가: 읽기·판정만 — consult_request · search_item · check_availability 셋. 접수·회원 토큰·위임은 없다
 *   (개인정보를 받지 않는다). 상태를 저장하지 않는다(세션 없음).
 * 전송: MCP Streamable HTTP — POST /mcp 에 JSON-RPC, 응답은 application/json. 알림만 오면 202. GET·DELETE는 405
 *       (사람이 인터넷 창으로 열 때 — Accept에 text/html, text/event-stream 없음 — 만 안내 화면). */
import { CFG, CATALOG, HOLD, PROMPT_BODY, TOOLS, PROMPTS, SERVER_VERSION } from "./mcp_data.js";

const PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"];     // 앞이 최신
export const SNAPSHOT_URL = "https://altarry-prog.github.io/chaekiji/data/holdings-today.json";
const FIX_ASOF = "2026-08-18";
const SNAPSHOT_MAX_DAYS = 2;
// [10/19] 심사 기간 고정 자료 — 동결 뒤 새벽 갱신이 멈추므로 동결일 이후 자료는 11. 26.까지 신선한 것으로 본다(naru.snapshot_ok와 같은 규칙). 결선 뒤 지움
// [10/27] 동결을 10. 30. 18시로 앞당김(담당자 결정) → 10. 30. 이후 자료
const FROZEN_FROM = "2026-10-30", FROZEN_UNTIL = "2026-11-26";
const SNAP_CACHE_MS = 10 * 60 * 1000;
const ROUTE_LABEL = { visit: "바로 이용(수령관 서가에 있음)", ill: "관내 상호대차", reserve: "예약 권장(관내 소장분 전부 대출 중)",
                      sea: "책바다(전국 상호대차) 안내", unknown: "도서 미확정", check: "소장 확인 불가(창구에서 조회)" };
const MEMBER_RULE_KEYS = ["권", "연체", "중복"];                 // 회원 정보가 있어야 판정되는 규정(한도 3종·연체·중복)

const state = { snap: null, snapAt: 0, bib: new Map() };       // 같은 실행 공간 안에서만 쓰는 기억(10분)

// ── 파이썬과 같은 결과를 내기 위한 작은 도구들 ────────────────────────────────
const words = s => String(s).split(/\s+/).filter(Boolean);
const norm = s => words(s).join("").toLowerCase();                                   // naru._norm
const replaceAll = (s, a, b) => s.split(a).join(b);
const pyTruthy = o => !!o && (typeof o !== "object" || Object.keys(o).length > 0);   // 빈 dict는 거짓
const pyQuote = s => encodeURIComponent(s).replace(/[!'()*]/g, c => "%" + c.charCodeAt(0).toString(16).toUpperCase());
const nn = v => (v === undefined ? null : v);
function kstDay(offsetDays = 0) {
  const d = new Date(Date.now() + 9 * 3600e3 + offsetDays * 864e5);
  return d.toISOString().slice(0, 10);
}
function illTerms(pickup, eta, hold, point = false) {          // tools._ill_terms — [10/18] 도착·보관·미수령 문장(값과 문장은 설정에서)
  if (point)                                                    // 작은도서관 받을 곳 — 도착일·보관 기한은 창구 확인
    return `관내 상호대차로 신청하시면 ${pickup}도서관에서 받으실 수 있고 비용은 없습니다. ` +
           `작은도서관으로 받으시면 도착일과 보관 기한은 창구에서 확인해 드립니다.` +
           (CFG.no_pickup_block_days ? ` 기한이 지나면 자동 반납되고 ${CFG.no_pickup_block_days}일 동안 상호대차를 신청할 수 없습니다.` : "");
  let out = CFG.ill_eta_text
    ? `관내 상호대차로 신청하시면 ${CFG.ill_eta_text} ${pickup}도서관에 도착하며 비용은 없습니다. `
    : `관내 상호대차로 신청하시면 ${eta}일 안에 ${pickup}도서관에서 받으실 수 있고 비용은 없습니다. `;
  out += CFG.hold_includes_arrival_day ? `도착한 날을 포함해 ${hold}일 안에 찾아가 주세요.` : `도착 후 ${hold}일 안에 찾아가 주세요.`;
  if (CFG.no_pickup_block_days) out += ` 기한이 지나면 자동 반납되고 ${CFG.no_pickup_block_days}일 동안 상호대차를 신청할 수 없습니다.`;
  return out;
}
function eun(word) {                                          // tools._eun — 받침에 따라 은/는
  if (!word) return "은(는)";
  const ch = [...word].pop();
  if (ch >= "가" && ch <= "힣") return (ch.codePointAt(0) - 0xac00) % 28 ? "은" : "는";
  return "은(는)";
}
const REQ_PHRASES = ["빌리고 싶어요", "빌리고 싶은데요", "빌리고 싶습니다", "빌릴 수 있어요", "빌릴 수 있나요", "빌릴 수 있을까요",
  "빌릴수있어요", "빌릴수있나요", "찾아 주세요", "찾아주세요", "찾아줘", "찾아 줘", "있나요", "있어요", "있을까요",
  "있습니까", "보고 싶어요", "읽고 싶어요", "대출 되나요", "대출되나요", "대출할 수 있나요", "신청해 주세요",
  "신청해주세요", "신청할게요", "부탁해요", "부탁드려요", "부탁합니다", "주세요", "가져다 줄 수 있어요",
  "가져다줄 수 있어요", "상호대차", "그 왜", "그거", "라는 책", "이라는 책", "하는 책", "인가 하는",
  // [10/18] 공개 모델 실측에서 문장째 넘어온 말끝(「채식주의자 상호대차 되나요?」 → 다른 책을 찾음)
  "되나요", "될까요", "가능한가요", "가능할까요", "가능해요", "가능한지", "가능 여부",
  "받을게요", "받을래요", "받고 싶어요", "받을 수 있나요", "받을 수 있어요", "받을 수 있을까요",
  "가져다줄 수 있나요", "가져다 줄 수 있나요", "가져다주세요", "가져다 주세요",
  // [10/19] AI 대조 시험에서 검색어에 남은 말(「양귀자 모순 빌리고 싶은데 …」 → 못 찾음)·직원 안내서 예시의 전해 말하기
  "빌리고 싶은데", "빌리고 싶대요", "빌리고 싶다고", "빌리려고 하는데요", "빌리려고 하는데", "빌리려고 해요", "빌리려고요",
  "받는대요", "받고 싶대요", "찾는데요", "찾고 있어요"];
const PHRASES_BY_LEN = [...REQ_PHRASES].sort((a, b) => b.length - a.length);   // 안정 정렬 — 파이썬 sorted와 같은 순서
const JOSA_LIB = "(?:으로|로|에서|에|까지)";
const reEsc = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
function dropPlaces(t, places) {                               // naru._drop_places — 「○○도서관(으로·에서 …)」은 어디서든, 「○○에서·으로」는 맨 끝일 때만
  if (!places.length) return t;
  const alts = [...places].sort((a, b) => b.length - a.length).map(reEsc).join("|");
  const libWord = new RegExp(`^(?:${alts})도서관${JOSA_LIB}?$`), libTail = new RegExp(`^도서관${JOSA_LIB}?$`);
  const toks = t.split(" "), out = [];
  for (let i = 0; i < toks.length; i++) {
    const w = toks[i];
    if (libWord.test(w)) continue;
    if (places.includes(w) && i + 1 < toks.length && libTail.test(toks[i + 1])) { i++; continue; }
    out.push(w);
  }
  if (out.length > 1 && new RegExp(`^(?:${alts})(?:으로|로|에서|까지)$`).test(out[out.length - 1])) out.pop();
  return out.join(" ");
}
function dropPoints(t, points) {                               // naru._drop_points — [10/19] 작은도서관 받을 곳(두 낱말 이름 포함)
  if (!points.length) return t;                                //   「○○(작은)도서관(으로·에서 …)」은 어디서든, 「○○에서·으로」는 맨 끝일 때만
  const alts = [...points].sort((a, b) => b.length - a.length).map(p => words(p).map(reEsc).join(" ?")).join("|");
  t = (" " + t + " ").replace(new RegExp(`(?<= )(?:${alts}) ?(?:작은도서관|도서관)${JOSA_LIB}?(?= )`, "g"), " ");
  t = words(t).join(" ");
  const m = new RegExp(`(?:^| )(?:${alts})(?:으로|로|에서|까지)$`).exec(t);
  if (m && m.index > 0) t = t.slice(0, m.index);
  return words(t).join(" ");
}
export function cleanTitle(utterance) {                        // naru.clean_title
  let t = " " + words(utterance).join(" ") + " ";
  for (const ph of PHRASES_BY_LEN) if (t.includes(ph)) t = replaceAll(replaceAll(t, " " + ph + " ", " "), ph, " ");
  t = t.replace(/[?.!,]/g, " ");
  t = words(t).join(" ");
  t = dropPlaces(t, Object.keys(CFG.libraries));               // [10/18] 수령관 말을 검색어에서 뺀다(파이썬 naru.PLACES와 같은 이름·순서)
  t = dropPoints(t, CFG.pickup_points || []);                  // [10/19] 작은도서관 받을 곳 이름도(파이썬 naru.POINTS)
  if (t.endsWith(" 책")) t = t.slice(0, -2).trimEnd();
  for (const suf of ["이라고", "라고", "이란", "란", "은", "는", "을", "를", "이", "가"]) {
    if ([...t].length > 3 && t.endsWith(suf) && !t.endsWith(" " + suf)) { t = t.slice(0, -suf.length).trimEnd(); break; }
  }
  return t || String(utterance);
}

// ── 매일 갱신 자료(시연 웹과 같은 파일) ─────────────────────────────────────
async function snapshot(ctx) {
  if (state.snapAt && Date.now() - state.snapAt < SNAP_CACHE_MS) return state.snap;
  let snap = null;
  if (ctx.n < 44) {
    ctx.n++;
    const ctl = new AbortController(); const tm = setTimeout(() => ctl.abort(), 3000);
    try {
      const r = await fetch(SNAPSHOT_URL, { signal: ctl.signal, cf: { cacheTtl: 300 } });
      if (r.ok) snap = await r.json();
    } catch (e) { snap = null; } finally { clearTimeout(tm); }
  }
  state.snap = snap; state.snapAt = Date.now();
  return snap;
}
export function snapshotOk(asof, today) {                      // naru.snapshot_ok — 평소 2일 이내, 또는 심사 기간 고정 자료
  if (!/^\d{4}-\d{2}-\d{2}$/.test(asof || "") || !/^\d{4}-\d{2}-\d{2}$/.test(today || "")) return false;
  const days = Math.round((Date.parse(today + "T00:00:00Z") - Date.parse(asof + "T00:00:00Z")) / 864e5);
  if (days >= 0 && days <= SNAPSHOT_MAX_DAYS) return true;
  return FROZEN_FROM <= asof && asof <= today && today <= FROZEN_UNTIL;
}
function snapshotFresh(snap) {
  if (!snap || !pyTruthy(snap.holdings)) return false;
  return snapshotOk(snap.asof, kstDay());
}

// ── 찾기(naru.search relay 모드) ──────────────────────────────────────────
function fixtureSearch(utterance) {
  const q = norm(utterance);
  let best = null;
  for (const b of CATALOG) {
    let score = 0;
    for (const k of b.keys) { const nk = norm(k); if (q.includes(nk) && nk.length > score) score = nk.length; }
    if (score && (best === null || score > best[0])) best = [score, b];
  }
  if (!best) return { found: false, reason: "픽스처에 없는 도서(모의 모드 한계) — live 모드에서는 전국 서지 검색" };
  const b = best[1];
  return { found: true, isbn13: b.isbn13, title: b.title, author: b.author, publisher: b.publisher, year: b.year,
           candidates: [b.isbn13], confidence: 0.97, evidence: "정보나루 srchBooks(모의 픽스처 · 실측 서지)" };
}
async function relaySearchDocs(params, deps, ctx) {             // naru._relay_search
  const r = await deps.relayCall("/search", params, ctx);
  const docs = r.docs || [];
  for (const x of docs) if (x.isbn13) state.bib.set(x.isbn13, { ...x, type: "일반", new_arrival: false,
    basis: "정보나루 srchBooks(중계) — 자료유형·신착은 미제공(판정 보류)" });
  return docs;
}
// ── [10/19] 서지 고르기(naru.pick_doc) — 검색 결과 첫 번째(대출 많은 순)를 그대로 쓰지 않고 문의와 견줘 고른다 ──────────
// AI 대조 시험(10/19)에서 「해리 포터와 마법사의 돌」 → 「혼혈 왕자」, 「구름빵 백희나」 → 중문판, 「불편한 편의점 2」 → 1권을 고른 일.
// 점수: 본서명 일치 100 · 문의가 서명에 다 들어 있음 80 · 낱말이 서명·저자에 나뉘어 다 들어 있음 70 · 본서명이 문의 안에 있음 60
//       + 저자 일치 10 · 권차 일치 15(다른 권이거나 몇 권인지 모르면 고르지 않음) · 한국어 문의에 외국어 판 -60 · 검색어에서 뺀 낱말이 안 맞음 -50
//       60점 아래면 고르지 않고 후보를 보이며 되묻는다(틀린 책으로 판정하지 않는다).
const VOL_EXPLICIT = /^(.*?)\s*(?:제\s*)?(\d{1,3})\s*권$/, VOL_TRAIL = /^(.*\D)\s+(\d{1,2})$/;
export function splitVolume(t) {                               // naru.split_volume — 「흔한남매 1권」 → [흔한남매, 1, 권 명시]
  let m = VOL_EXPLICIT.exec(t);
  if (m && m[1].trim()) return [m[1].trim(), String(parseInt(m[2], 10)), true];
  m = VOL_TRAIL.exec(t);
  if (m && [...m[1].trim()].length >= 2) return [m[1].trim(), String(parseInt(m[2], 10)), false];
  return [t, null, false];
}
const keepCh = ch => (ch >= "0" && ch <= "9") || (ch >= "a" && ch <= "z") || (ch >= "가" && ch <= "힣") || (ch >= "ㄱ" && ch <= "ㅣ") ||
                     (ch >= "一" && ch <= "鿿") || (ch >= "぀" && ch <= "ヿ");
const tnorm = s => [...String(s ?? "").toLowerCase()].filter(keepCh).join("");          // naru._tnorm
const hasHangul = s => [...String(s ?? "")].some(ch => ch >= "가" && ch <= "힣");
function mainTitle(title) {                                    // naru._main_title — 부서명(:) · 대등서명(=) · 앞뒤 괄호 설명을 뗀 본서명
  let t = String(title ?? "").split(/[:：]/)[0].split(" =")[0];
  t = t.replace(/^\s*\([^)]*\)\s*/, "").replace(/\s*\([^)]*\)\s*$/, "");
  return t.trim();
}
const ROLE_WORDS = new Set(["지은이", "지음", "저자", "저", "글", "그림", "글·그림", "원작", "옮김", "옮긴이", "역", "편", "엮음",
                            "공저", "공역", "감수", "기획", "편저", "편역"]);
function firstAuthor(a) {                                      // naru._first_author — 첫 저자 이름만(역할 낱말 뺌)
  const first = String(a ?? "").split(/[;,|]/)[0];
  return tnorm(first.split(/[\s:()]+/).filter(w => w && !ROLE_WORDS.has(w)).join(""));
}
const sameAuthor = (a, b) => !a || !b || a.includes(b) || b.includes(a);
const GENERIC_SUB = ["소설", "에세이", "시집", "산문", "장편", "단편", "연작", "개정", "큰글자", "특별판", "한정판", "양장", "리커버"];
function coreTitle(title, author) {                            // naru._core_title — 본서명 + (작품을 가르는 부서명만). 「장편소설」·저자 이름 같은 부서명은 뺀다
  const raw = String(title ?? ""), i = raw.search(/[:：]/);
  const sub = i < 0 ? "" : raw.slice(i + 1), subn = tnorm(sub), fa = firstAuthor(author);
  const generic = !subn || GENERIC_SUB.some(w => sub.includes(w)) || (!!fa && subn.includes(fa));
  return tnorm(mainTitle(raw)) + (generic ? "" : subn);
}
const FOREIGN_MARK = ["중문판", "영문판", "일문판", "원서"];
function scoreDoc(doc, qFull, qBase, vol, dropped) {           // naru._score_doc
  const qn = tnorm(vol ? qBase : qFull), tn = tnorm(mainTitle(doc.title)), fn = tnorm(doc.title), an = tnorm(doc.author);
  if (!tn || !qn) return 0;
  let s = 0;
  if (tn === qn) s = 100;
  else if (fn.includes(qn)) s = 80;
  else {
    const toks = words(vol ? qBase : qFull).map(tnorm).filter(x => [...x].length >= 2);
    const inT = toks.filter(x => fn.includes(x)), inA = toks.filter(x => !fn.includes(x) && an.includes(x));
    if (toks.length && inT.length && inT.length + inA.length === toks.length) s = 70;
    else if ([...tn].length >= 2 && qn.includes(tn)) s = 60;
  }
  if (!s) return 0;
  const hints = words(qFull).concat(dropped).map(tnorm).filter(x => [...x].length >= 2);
  if (hints.some(x => an.includes(x))) s += 10;
  if (dropped.map(tnorm).filter(x => x).some(x => !fn.includes(x) && !an.includes(x))) s -= 50;
  if (vol) {
    const dv = String(doc.vol ?? "").replace(/\D/g, "").replace(/^0+/, "");
    const nums = (mainTitle(doc.title).match(/\d+/g) || []).map(x => x.replace(/^0+/, ""));
    if (dv ? dv !== vol : !nums.includes(vol)) return 0;       // 다른 권이거나 몇 권인지 모르면 고르지 않는다(되묻기)
    s += 15;
  }
  if (hasHangul(qFull)) {
    const t = String(doc.title ?? "");
    const cjk = [...t].filter(ch => ch >= "一" && ch <= "鿿").length;
    if (cjk >= 2 || FOREIGN_MARK.some(mk => t.includes(mk)) || !hasHangul(t)) s -= 60;
  }
  return s;
}
function volLabel(v) {                                       // naru._vol_label — 「2」·「제2권」 → 「2권」
  const dg = String(v ?? "").replace(/\D/g, "").replace(/^0+/, "");
  return dg ? `${dg}권` : String(v ?? "").trim();
}
const bookOf = d => ({ isbn13: d.isbn13, title: nn(d.title), author: nn(d.author), publisher: nn(d.publisher), year: nn(d.year),   // naru._book_of — [10/19 밤] 권차가 있으면 함께
                       ...(d.vol ? { vol: String(d.vol) } : {}) });
async function searchItem(utterance, deps, ctx) {
  const title = cleanTitle(utterance);
  const [base, vol, explicit] = splitVolume(title);
  if (!vol) {                                                  // [10/19] 권차를 말하면 시연 도서(1권) 픽스처로 바로 가지 않는다
    const fx = fixtureSearch(utterance);
    if (fx.found) { fx.evidence = "정보나루 srchBooks(실측 서지 픽스처) · 소장·대출 상태는 중계로 오늘 조회"; return fx; }
  }
  const toks = words(title);
  const plan = vol ? (explicit ? [[base, []]] : [[title, []], [base, []]])
                   : [[title, []]].concat(toks.length >= 2 ? [[toks.slice(0, -1).join(" "), toks.slice(-1)], [toks.slice(1).join(" "), toks.slice(0, 1)]] : []);
  const seen = new Set(), pool = [];
  let best = null, sawDocs = false;
  for (let i = 0; i < plan.length; i++) {
    const [q, dropped] = plan[i];
    if ([...tnorm(q)].length < 2 || seen.has(q)) continue;
    seen.add(q);
    let docs;
    try { docs = await relaySearchDocs({ q }, deps, ctx); }
    catch (e) {                                                // [v0.3.5] 「책이 없다」가 아니라 「찾지 못했다(연결 안 됨)」
      if (i === 0) return { found: false, reason: `중계 응답 없음 — 픽스처 5종에도 없는 도서(검색어 「${title}」)`, candidates: [], unavailable: true };
      break;
    }
    docs.forEach((d, j) => { if (d.isbn13 && !pool.some(p => p.d.isbn13 === d.isbn13)) pool.push({ d, q, j, dropped }); });
    if (docs.length) sawDocs = true;
    for (const p of pool) {
      if (p.q !== q) continue;
      const sc = scoreDoc(p.d, title, base, vol, p.dropped);
      if (sc >= 60 && (!best || sc > best.sc)) best = { ...p, sc };
    }
    if (best && !(vol && !explicit && i === 0)) break;         // 권차가 낱말 끝 숫자일 때만 두 검색을 함께 견준다
  }
  if (best) {
    const d = best.d, ct = coreTitle(d.title, d.author), fa = firstAuthor(d.author);
    const others = [], seenA = [fa];
    for (const p of pool) {
      const o = p.d;
      if (o.isbn13 === d.isbn13 || coreTitle(o.title, o.author) !== ct) continue;
      const oa = firstAuthor(o.author);
      if (seenA.some(a => sameAuthor(a, oa))) continue;
      seenA.push(oa); others.push(bookOf(o));
      if (others.length >= 3) break;
    }
    const docsQ = pool.filter(p => p.q === best.q).map(p => p.d.isbn13);
    const res = { found: true, isbn13: d.isbn13, title: nn(d.title), author: nn(d.author), publisher: nn(d.publisher), year: nn(d.year),
                  ...(d.vol ? { vol: String(d.vol) } : {}), candidates: docsQ, query: best.q, confidence: 0.85,
                  evidence: "정보나루 srchBooks(중계 · 전국 서지 · 제목 부분일치)" +
                            (best.q !== title || best.j > 0 ? ` · 검색어 「${best.q}」 결과 ${best.j + 1}번째를 문의와 맞춰 고름` : "") };
    if (others.length) res.same_title_others = others;
    const eds = [];                                            // [10/19] 같은 작품의 다른 판(같은 핵심 서명 · 같은 첫 저자 · 문의와도 맞음) — naru.pick_search와 같게
    for (const p of pool) {
      const o = p.d;
      if (o.isbn13 === d.isbn13 || coreTitle(o.title, o.author) !== ct) continue;
      const oa = firstAuthor(o.author);
      if (!(fa && oa && (fa.includes(oa) || oa.includes(fa)))) continue;
      if (scoreDoc(o, title, base, vol, p.dropped) < 60) continue;
      eds.push(bookOf(o));
      if (eds.length >= 2) break;
    }
    if (eds.length) res.same_work_editions = eds;
    return res;
  }
  if (sawDocs) {
    const cands = pool.slice(0, 3).map(p => bookOf(p.d));
    return { found: false, reason: `정보나루 서지 검색에서 문의와 맞는 책을 고르지 못함(검색어 「${title}」) — 저자·권차·출판사를 더 알려 주세요`,
             candidates: cands.map(b => b.isbn13), candidate_books: cands, query: title };
  }
  return { found: false, reason: `정보나루 서지 검색 결과 없음(검색어 「${title}」) — 제목·저자를 더 알려 주세요`, candidates: [], query: title };
}
async function bibinfo(isbn13, deps, ctx) {                    // naru.bibinfo relay 모드
  const b = CATALOG.find(x => x.isbn13 === isbn13);
  if (b) return b;
  if (state.bib.has(isbn13)) return state.bib.get(isbn13);
  try { await relaySearchDocs({ isbn: isbn13 }, deps, ctx); } catch (e) { /* 서지 미확인 */ }
  return state.bib.get(isbn13) || {};
}

// ── 관내 소장·대출(naru.holdings_local relay 모드) ─────────────────────────
const LIBS = CFG.libraries;
const countHeld = out => Object.values(out).filter(v => v !== "none").length;
async function holdingsLocal(isbn13, deps, ctx) {
  const snap = await snapshot(ctx);
  if (snapshotFresh(snap) && snap.holdings[isbn13]) {         // 오늘 새벽 자료에 있으면 그것으로(정보나루 호출·한도 절약)
    const h = snap.holdings[isbn13];
    const out = Object.fromEntries(Object.keys(LIBS).map(n => [n, h[n] || "none"]));
    return { out, meta: { basis: `관내: 정보나루 bookExist(매일 갱신 · ${snap.asof} 조회 · 전일 기준)`, asof: snap.asof,
                          holding_count: countHeld(out), calls: 0, cached: true } };
  }
  try {
    const r = await deps.relayCall("/holdings", { isbn: isbn13 }, ctx);
    const libs = r.libs || {};
    const out = Object.fromEntries(Object.entries(LIBS).map(([n, code]) => [n, libs[String(code)] || "none"]));
    const asof = r.asof || kstDay();
    return { out, meta: { basis: `관내: 정보나루 bookExist(중계 · ${asof} 조회 · 전일 기준)`, asof,
                          holding_count: countHeld(out), calls: nn(r.calls), cached: !!r.cached } };
  } catch (e) {                                              // 정보나루가 안 되면 8/18 실측 픽스처로 — 근거 문구에 그대로 적는다
    if (!Object.prototype.hasOwnProperty.call(HOLD.holdings || {}, isbn13) || (HOLD._examples || []).includes(isbn13)) {   // [v0.3.5] 실측 픽스처가 없으면 「확인 불가」(naru._unknown)
      const out = Object.fromEntries(Object.keys(LIBS).map(n => [n, "unknown"]));
      return { out, meta: { basis: "관내: 정보나루 조회 실패(중계 응답 없음) — 소장·대출 상태 확인 불가", asof: kstDay(),
                            holding_count: null, calls: 0, cached: false, unavailable: true } };
    }
    const h = (HOLD.holdings || {})[isbn13] || {};
    const out = Object.fromEntries(Object.keys(LIBS).map(n => [n, h[n] || "none"]));
    const ex = (HOLD._examples || []).includes(isbn13);
    const basis = (ex ? "관내: 예시 데이터(관내에 없는 책의 흐름을 보이는 장면 — 이 책의 실제 소장과 다를 수 있음)"
                      : "관내: 정보나루 bookExist(2026. 8. 18. 실측 픽스처 · 전일 기준)") + " · 중계 응답 없음 → 픽스처로 복귀";
    return { out, meta: { basis, asof: FIX_ASOF, holding_count: countHeld(out), calls: 0, cached: false, example: ex } };
  }
}
function fixtureNation(isbn13) {
  const n = (HOLD.nation || {})[isbn13];
  return { basis: `전일(${kstDay(-1)}) 기준 · 정보나루`, found_count: (n || {}).count || 0, note: (n || {}).note || "전국 조회(모의)" };
}
async function nationRemote(isbn13, deps, ctx) {              // naru.availability_nation relay 모드
  const snap = await snapshot(ctx);
  if (snapshotFresh(snap) && Object.prototype.hasOwnProperty.call(snap.nation || {}, isbn13)) {
    const n = snap.nation[isbn13];
    if (n !== null && n !== undefined)
      return { basis: `전일 기준 · 정보나루(매일 갱신 · ${snap.asof} 조회)`, found_count: n.count ?? 0, note: "경기 광역 예시", asof: snap.asof };
  }
  try {
    const r = await deps.relayCall("/nation", { isbn: isbn13 }, ctx);
    return { basis: `전일 기준 · 정보나루(중계 · ${r.asof || kstDay()} 조회)`, found_count: r.found_count ?? 0, note: "경기 광역 예시", asof: nn(r.asof) };
  } catch (e) {
    const out = fixtureNation(isbn13); out.note += " · 중계 응답 없음 → 픽스처로 복귀"; return out;
  }
}
function pickupName(p) {                                       // tools._pickup_name — 「꿈빛도서관」·「부천시립 꿈빛도서관」도 「꿈빛」으로(모르면 그대로)
  let s = words(p).join("");
  for (const pre of [CFG.city + "시립", CFG.city + "시"]) if (s.startsWith(pre) && s.length > pre.length) { s = s.slice(pre.length); break; }
  const has = k => Object.prototype.hasOwnProperty.call(CFG.libraries, k);
  if (has(s)) return s;
  for (const suf of ["도서관", "관"]) if (s.endsWith(suf) && has(s.slice(0, -suf.length))) return s.slice(0, -suf.length);
  const pts = Object.fromEntries((CFG.pickup_points || []).map(x => [words(x).join(""), x]));   // [10/18] 작은도서관 받을 곳
  for (const cand of [s, s.endsWith("작은도서관") ? s.slice(0, -5) : "", s.endsWith("도서관") ? s.slice(0, -3) : ""])
    if (cand && Object.prototype.hasOwnProperty.call(pts, cand)) return pts[cand];
  return String(p);
}
async function checkAvailability(isbn13, deps, ctx) {          // tools.check_availability(LOCAL_SOURCE=naru)
  const home = CFG.home_library;
  const { out: rt, meta } = await holdingsLocal(isbn13, deps, ctx);
  const ok = Object.keys(rt).filter(l => rt[l] === "ok").sort();
  const busy = Object.keys(rt).filter(l => rt[l] === "busy").sort();
  const res = { city: CFG.city, home_library: home, home_status: rt[home] || "none", available_at: ok, loaned_at: busy,
                basis: meta.basis || "관내: 정보나루(전일 기준)", holding_count: nn(meta.holding_count), naru_calls: nn(meta.calls) };
  if (meta.unavailable) { res.status_unknown = true; return { res, rt, meta }; }   // [v0.3.5] 관내를 모르면 전국으로 넘기지 않는다
  if (!ok.length) res.nation = await nationRemote(isbn13, deps, ctx);
  return { res, rt, meta };
}

// ── 규정(policy.check)과 회원 없는 판정(tools._guest_policy) ────────────────
function policyCheck(rules, member, onShelf, pickup, item, isbn13) {
  const checks = [];
  const rule = (name, passed, detail) => checks.push({ rule: name, pass: !!passed, detail });
  if (rules.block_if_pickup_on_shelf ?? true)
    rule("수령관 동일도서 비치 시 신청 불가", !onShelf, onShelf ? "수령관 서가에 비치 중" : "수령관 소장본 서가에 없음(대출중 또는 미소장)");
  rule(`상호대차 1인 ${rules.ill_limit}권`, member.ill_count < rules.ill_limit, `현재 ${member.ill_count}/${rules.ill_limit}권`);
  rule(`통합 대출 ${rules.total_limit}권`, member.total_loans < rules.total_limit, `현재 ${member.total_loans}/${rules.total_limit}권`);
  const at = (member.loans_at || {})[pickup] || 0;
  rule(`도서관별 ${rules.per_lib_limit}권(직접+상호대차)`, at < rules.per_lib_limit, `${pickup} 현재 ${at}/${rules.per_lib_limit}권`);
  if (rules.block_if_overdue ?? true) {
    const od = member.overdue_count || 0, sus = !!member.suspended;
    rule("연체·정지 회원 신청 불가", od === 0 && !sus, (od || sus) ? ("연체 " + od + "건" + (sus ? " · 이용 정지 중" : "")) : "연체·정지 없음");
  }
  const excl = rules.excluded_types || [];
  const exna = !!rules.exclude_new_arrival;
  if (pyTruthy(item)) {
    const t = item.type ?? "일반", na = !!item.new_arrival;
    const badType = excl.includes(t), badNew = exna && na;
    const detail = badType ? ("자료 유형 " + t + " — 제외 대상") : (badNew ? "신착 자료 — 신착 제외 기간" : `유형 ${t} · 신착 아님`);
    rule("상호대차 제외 자료 아님", !(badType || badNew), detail);
  } else rule("상호대차 제외 자료 아님", true, "서지 미확인 — 제외 판정 보류(통과 처리)");
  const act = member.active_isbns || [];
  const dup = !!isbn13 && act.includes(isbn13);
  rule("동일 도서 중복 신청 없음", !dup, dup ? "이미 진행 중인 신청 있음" : "진행 중 신청 없음");
  return { allowed: checks.every(c => c.pass), checks };
}
function guestPolicy(onShelf, pickup, item, isbn13) {
  const guest = { ill_count: 0, total_loans: 0, loans_at: {}, overdue_count: 0, suspended: false, active_isbns: [] };
  const v = policyCheck(CFG.rules, guest, onShelf, pickup, item, isbn13);
  const pending = [];
  for (const c of v.checks) {
    if (MEMBER_RULE_KEYS.some(k => c.rule.includes(k))) { c.pass = null; c.detail = "회원 확인 필요 — 창구에서 도서관리시스템으로 확인"; pending.push(c.rule); }
  }
  const decided = v.checks.filter(c => c.pass !== null);
  return { allowed_so_far: decided.every(c => c.pass), checks: v.checks, pending,
           basis: "회원 토큰 없이 판정 — 비치·제외자료 규정만 확정, 한도·연체·중복은 창구 확인" };
}
function officialLink(title, isbn13, byTitle = false) {         // tools._official_link — [10/18] ISBN 기본, 소장 확인 불가는 제목 검색
  const tmpl = String((byTitle && CFG.official_search_url_title) || CFG.official_search_url || "").trim();
  if (!tmpl) return null;
  return tmpl.split("{title}").join(pyQuote(title)).split("{isbn13}").join(pyQuote(isbn13));
}

// ── 상담 묶음(tools.consult_request, 회원 토큰 없이) ───────────────────────
class ToolError extends Error { constructor(kind, msg) { super(msg); this.kind = kind; } }
export async function consultRequest(args, deps, ctx) {
  const utterance = args.utterance;
  if (typeof utterance !== "string" || !utterance.trim()) throw new ToolError("TypeError", "utterance(이용자의 말 또는 책 제목)가 필요합니다");
  if (args.user) throw new ToolError("ValueError", "원격 상담 비서는 회원 토큰을 받지 않습니다(개인정보 보호) — 회원 규정은 창구에서 확인합니다");
  const pickup = pickupName(args.pickup || CFG.home_library);
  const lang = args.lang || "ko";
  const points = CFG.pickup_points || [];
  const isPoint = points.includes(pickup) && !Object.prototype.hasOwnProperty.call(LIBS, pickup);   // [10/18] 작은도서관 받을 곳
  if (!Object.prototype.hasOwnProperty.call(LIBS, pickup) && !isPoint)
    throw new ToolError("ValueError", `수령관 「${pickup}」은(는) 설정에 없는 도서관입니다: ${[...Object.keys(LIBS), ...points].join(", ")}`);
  const eta = CFG.ill_eta_days ?? "2~3", hold = CFG.hold_days ?? 3;
  const found = await searchItem(utterance, deps, ctx);
  const base = { utterance, pickup, lang, mode: "relay",
                 disclaimer: "대출 가능 여부는 정보나루 조회일 전일 기준이며, 최종 확인과 접수는 창구에서 합니다." };
  if (!found.found && found.unavailable) {                    // [v0.3.5] 정보나루에 닿지 못해 찾지 못함 — 되묻지 말고 창구 조회
    return { ...base, found: false, route: "check", route_label: ROUTE_LABEL.check, book: null, reason: nn(found.reason), candidates: [],
             notice: "지금 정보나루에 연결되지 않아 책을 찾지 못했습니다. 창구에서 도서관리시스템으로 찾아 드리겠습니다.",
             desk_memo: `[조회 불가] 문의 「${utterance}」 — 정보나루 연결 안 됨, 창구에서 도서관리시스템으로 조회` };
  }
  if (!found.found) {
    const out = { ...base, found: false, route: "unknown", route_label: ROUTE_LABEL.unknown, book: null, reason: nn(found.reason),
                  candidates: found.candidates || [],
                  notice: "말씀하신 책을 아직 찾지 못했습니다. 저자나 출판사, 대략의 내용을 조금 더 알려 주시겠어요?",
                  desk_memo: `[미확정] 문의 「${utterance}」 — 서지 재확인 필요` };
    if (found.candidate_books) {                               // [10/19] 검색은 됐지만 문의와 맞는 책을 못 고름 — 후보를 보여 주고 되묻는다
      out.candidate_books = found.candidate_books;
      out.desk_memo += "\n검색 후보: " + found.candidate_books.map(b => `${String(b.title || "").trim()}${b.vol ? ` [${volLabel(b.vol)}]` : ""}` +
                                                                 `(${b.author || ""}, ${b.publisher || ""} ${b.year || ""})`).join(" / ");
    }
    return out;
  }
  const isbn = found.isbn13, title = found.title || isbn;
  const { res: avail, rt, meta } = await checkAvailability(isbn, deps, ctx);
  const unknown = !!avail.status_unknown;                     // [v0.3.5] 정보나루 조회 실패 + 픽스처에도 없는 책
  const atPickup = unknown ? "unknown" : isPoint ? "point" : avail.available_at.includes(pickup) ? "ok" : avail.loaned_at.includes(pickup) ? "busy" : "none";
  const othersOk = avail.available_at.filter(l => l !== pickup);
  const nation = nn(avail.nation);
  let route, fromLib;
  if (unknown) [route, fromLib] = ["check", null];
  else if (atPickup === "ok") [route, fromLib] = ["visit", pickup];
  else if (othersOk.length) [route, fromLib] = ["ill", othersOk[0]];
  else if (avail.loaned_at.length || atPickup === "busy") [route, fromLib] = ["reserve", null];
  else [route, fromLib] = ["sea", null];
  const item = await bibinfo(isbn, deps, ctx);
  const pol = guestPolicy(rt[pickup] === "ok", pickup, item, isbn);
  if (unknown) {                                              // 수령관 비치 여부도 모르므로 비치 규정까지 창구 확인으로
    for (const c of pol.checks) {
      if (c.rule.includes("비치") && c.pass !== null) {
        c.pass = null; c.detail = "소장·대출 상태 확인 불가 — 창구에서 도서관리시스템으로 확인"; pol.pending.push(c.rule);
      }
    }
    pol.allowed_so_far = pol.checks.filter(c => c.pass !== null).every(c => c.pass);
  }
  if (isPoint) {                                              // [10/18] 작은도서관 서가 비치 여부는 정보나루에 없다
    for (const c of pol.checks) {
      if (c.rule.includes("비치") && c.pass !== null) {
        c.pass = null; c.detail = "작은도서관 서가 비치 여부는 정보나루에 없어 창구에서 확인"; pol.pending.push(c.rule);
      }
    }
    pol.allowed_so_far = pol.checks.filter(c => c.pass !== null).every(c => c.pass);
  }
  if (!pyTruthy(item) || String(item.basis || "").includes("미제공")) {   // 자료 유형·신착을 모르면 제외 자료 규정도 창구 확인(tools._unverified_item)
    for (const c of pol.checks) {
      if (c.rule === "상호대차 제외 자료 아님" && c.pass !== null) {
        c.pass = null; c.detail = "자료 유형·신착 여부는 정보나루에 없어 창구에서 확인"; pol.pending.push(c.rule);
      }
    }
    pol.allowed_so_far = pol.checks.filter(c => c.pass !== null).every(c => c.pass);
  }
  const asof = meta.asof || FIX_ASOF;
  const [y, m, d] = asof.split("-"); const asofK = `${y}. ${parseInt(m, 10)}. ${parseInt(d, 10)}.`;
  const nOk = avail.available_at.length, nBusy = avail.loaned_at.length;
  const disp = found.vol ? `${mainTitle(title)} ${volLabel(found.vol)}` : String(title).trim();   // [10/19] 권차가 있으면 「흔한남매 1권」처럼 밝힌다 · 정보나루 서명 끝 빈칸은 뗀다(「은(는)」 방지)
  const t_ = `『${disp}』${eun(disp)}`;
  let notice;
  if (route === "visit") {
    notice = `${t_} 지금 ${pickup}도서관 서가에 있어 바로 대출하실 수 있습니다. ` +
             `받으실 도서관에 있는 자료는 상호대차 신청 대상이 아니니 방문해 주세요.`;
  } else if (route === "ill" && isPoint) {                     // [10/18] 작은도서관에서 받기 — 그곳 소장 여부는 말하지 않는다(모름)
    notice = `${t_} ${fromLib}도서관 등 ${CFG.city}시립도서관 ${nOk}곳에 대출 가능 상태입니다. ` + illTerms(pickup, eta, hold, true);
  } else if (route === "ill") {
    const where = atPickup === "busy" ? "대출 중이" : "없";
    notice = `${t_} ${pickup}도서관에는 ${where}지만 ${fromLib}도서관 등 ${CFG.city}시립도서관 ${nOk}곳에 대출 가능 상태입니다. ` +
             illTerms(pickup, eta, hold);
  } else if (route === "reserve") {
    notice = `${t_} ${CFG.city}시립도서관 ${nBusy}곳이 소장하고 있지만 지금은 모두 대출 중입니다. ` +
             (CFG.reserve_converts_to_ill ? "먼저 예약해 두시면, 책이 반납될 때 상호대차로 바꿔 신청할 수 있습니다"
                                          : "상호대차 대신 예약을 권해 드립니다") +
             "(책바다는 관내에 없는 자료가 대상입니다).";
  } else if (route === "check") {
    notice = `${t_} 지금 ${CFG.city}시립도서관의 소장·대출 상태를 확인하지 못했습니다(정보나루 조회가 되지 않았습니다). ` +
             `창구에서 도서관리시스템으로 확인해 드리겠습니다.`;
  } else {
    const cnt = (nation || {}).found_count;
    notice = `${t_} ${CFG.city}시립도서관 ${Object.keys(LIBS).length}곳에 소장되어 있지 않습니다. 전국 상호대차(책바다)로 신청하실 수 있으며 ` +
             `왕복 택배비가 듭니다.` + (cnt ? ` 정보나루 기준 다른 지역 ${cnt}곳 소장입니다.` : "");
  }
  const example = (HOLD._examples || []).includes(isbn) && !!meta.example;
  if (route !== "check")                                      // 조회한 자료가 없으면 날짜를 찍지 않는다
    notice += example ? " (예시 데이터 — 이 책의 실제 소장·대출과 다를 수 있습니다)" : ` (대출 상태는 정보나루 ${asofK} 조회, 전일 기준)`;
  if (pol.pending.length) notice += " 회원 한도·연체 여부는 창구에서 확인해 드립니다.";
  const others = found.same_title_others || [];                // [10/19] 같은 제목·다른 저자의 책이 함께 검색됨 — 고른 책을 밝히고 확인을 청한다
  if (others.length)
    notice += ` 같은 제목의 다른 책도 있습니다(${others.map(b => `${b.author || ""} · ${b.publisher || ""} ${b.year || ""}`).join(" / ")}) — ` +
              `찾으시는 책의 저자가 다르면 알려 주세요.`;
  const alt = [];                                              // [10/19] 판본 보정 — 고른 판이 관내에 없을 때 같은 작품의 다른 판 하나가 관내에 있으면 알린다. 갈래는 그대로(tools.consult_request와 같게)
  if (route === "sea") {                                     // 하나만 본다 — Cloudflare 무료 요금제는 요청당 외부 호출 50회 한도(검색 ≤3 + 관내 16 + 전국 1 + 다른 판 16)
    for (const b of (found.same_work_editions || []).slice(0, 1)) {
      const { out: rt2, meta: m2 } = await holdingsLocal(b.isbn13, deps, ctx);
      if (m2.unavailable || (m2.asof || FIX_ASOF) !== asof) continue;   // 조회가 안 됐거나 조회일이 다르면 섞지 않는다
      const ok2 = Object.keys(rt2).filter(l => rt2[l] === "ok").sort(), busy2 = Object.keys(rt2).filter(l => rt2[l] === "busy").sort();
      if (ok2.length || busy2.length)
        alt.push({ ...b, available_at: ok2, loaned_at: busy2, official_link: officialLink(b.title || b.isbn13, b.isbn13) });
    }
  }
  if (alt.length) {
    const altWhere = b => {
      const ed = [b.publisher || "", b.year ? `${b.year}년` : ""].filter(x => x).join(" ") || `ISBN ${b.isbn13}`;
      if (b.available_at.includes(pickup)) return `${ed} 판은 ${pickup}도서관 서가에 있습니다`;
      if (b.available_at.length) return `${ed} 판은 ${b.available_at[0]}도서관 등 ${b.available_at.length}곳에 대출 가능합니다`;
      return `${ed} 판은 ${b.loaned_at.length}곳이 소장하고 있지만 모두 대출 중입니다`;
    };
    const lk = alt[0].official_link;
    notice += " 같은 책의 다른 판은 관내에 있습니다: " + alt.map(altWhere).join("; ") +
              ". 판이 달라도 괜찮으시면 그 판으로 이용하실 수 있습니다" + (lk ? `(그 판의 공식 누리집 화면: ${lk}).` : ".");
  }
  const bad = pol.checks.filter(c => c.pass === false && !(route === "visit" && c.rule.includes("비치")));
  if (bad.length) notice += " 다만 " + bad.map(c => `${c.rule}(${c.detail})`).join("; ") + " — 이 조건을 먼저 확인해야 합니다.";
  const link = ["visit", "ill", "reserve", "check"].includes(route) ? officialLink(title, isbn, route === "check") : null;
  if (link) {
    const tail = { visit: "이 책 보기", ill: "이 책 보기·신청(로그인 뒤 「상호대차 신청」 — 접수는 이용자가 직접)",
                   reserve: "이 책 보기·예약(로그인 뒤 「예약」)", check: "이 책의 소장·대출 상태 보기" }[route];
    notice += ` 공식 누리집에서 ${tail}: ${link}`;
  }
  const memo = [
    `도서: ${String(title).trim()}${found.vol ? ` [${volLabel(found.vol)}]` : ""} (${found.author || ""}) ISBN ${isbn}` + (others.length ? ` · 같은 제목 다른 책 ${others.length}건 — 저자 확인` : ""),
    `갈래: ${ROUTE_LABEL[route]}` + (fromLib ? ` · 소장관 ${fromLib}` : ""),
    isPoint ? `수령관: ${pickup}도서관 (작은도서관 — 서가 비치·도착일·보관 기한은 창구 확인)`
            : `수령관: ${pickup} (현재 ${atPickup === "ok" ? "서가 비치" : atPickup === "busy" ? "대출 중" : unknown ? "확인 불가" : "미소장"})`,
    unknown ? "대출 가능 관: 확인 불가 / 대출 중: 확인 불가"
            : `대출 가능 관: ${avail.available_at.join(", ") || "없음"} / 대출 중: ${avail.loaned_at.join(", ") || "없음"}`,
    `근거: ${avail.basis}`,
    `규정: ${pol.checks.filter(c => c.pass === true).length}건 통과 · ${pol.checks.filter(c => c.pass === false).length}건 불가 · ${pol.pending.length}건 창구 확인`,
    "접수: 창구에서 도서관리시스템 입력(이 도구는 접수하지 않음)",
  ];
  for (const b of alt)                                         // [10/19] 판본 보정 — 다른 판의 관내 소장(접수 전 판 확인)
    memo.splice(memo.length - 1, 0, `다른 판 관내: ${b.publisher || ""} ${b.year || ""} ISBN ${b.isbn13} — ` +
                                    `대출 가능 ${b.available_at.join(", ") || "없음"} / 대출 중 ${b.loaned_at.join(", ") || "없음"}`);
  return { ...base, found: true, route, route_label: ROUTE_LABEL[route], from_lib: fromLib,
           book: { isbn13: isbn, title, author: nn(found.author), publisher: nn(found.publisher), year: nn(found.year), evidence: nn(found.evidence),
                   ...(found.vol ? { vol: found.vol } : {}) },
           availability: { at_pickup: atPickup, available_at: avail.available_at, loaned_at: avail.loaned_at, nation, basis: avail.basis, asof },
           policy: pol, notice, official_link: link, translate_to: lang === "ko" ? null : lang,
           desk_memo: memo.join("\n"), next_tool: null, ...(others.length ? { same_title_others: others } : {}),
           ...(alt.length ? { other_editions: alt } : {}) };
}

const IMPL = {
  consult_request: (a, deps, ctx) => consultRequest(a, deps, ctx),
  search_item: async (a, deps, ctx) => {
    if (typeof a.utterance !== "string" || !a.utterance.trim()) throw new ToolError("TypeError", "utterance가 필요합니다");
    return searchItem(a.utterance, deps, ctx);
  },
  check_availability: async (a, deps, ctx) => {
    const isbn = String(a.isbn13 || "").replace(/\D/g, "");
    if (!/^97[89]\d{10}$/.test(isbn)) throw new ToolError("ValueError", "isbn13(13자리 ISBN)이 필요합니다");
    return (await checkAvailability(isbn, deps, ctx)).res;
  },
};

// ── MCP 상자(JSON-RPC over HTTP) ─────────────────────────────────────────
export const INSTRUCTIONS = "책이지 원격 상담 비서(부천시립도서관 상호대차 판정 · 시연·검증용 — 접수 기능 없음).\n" +
  PROMPT_BODY.split("{pickup}").join(CFG.home_library + "(사서가 다른 도서관을 말하면 그 도서관)")
             .split("{lang}").join("ko(이용자가 다른 언어를 쓰면 그 언어 코드)").trim();
const TOOL_LIST = TOOLS.map(t => ({ ...t, annotations: { title: t.name === "consult_request" ? "상호대차 상담(판정·안내문)" :
  t.name === "search_item" ? "도서 찾기" : "소장·대출 상태", readOnlyHint: true, openWorldHint: true } }));

function rpcResult(id, result) { return { jsonrpc: "2.0", id, result }; }
function rpcError(id, code, message) { return { jsonrpc: "2.0", id: id ?? null, error: { code, message } }; }
function promptText(args) {
  return PROMPT_BODY.split("{pickup}").join(args.pickup || CFG.home_library).split("{lang}").join(args.lang || "ko").trim();
}

async function handleOne(m, deps) {
  if (!m || typeof m !== "object" || Array.isArray(m) || m.jsonrpc !== "2.0") return rpcError(null, -32600, "Invalid Request");
  const isNotice = !Object.prototype.hasOwnProperty.call(m, "id");
  if (typeof m.method !== "string") return isNotice ? null : rpcError(m.id, -32600, "Invalid Request");   // 클라이언트의 응답 등
  if (isNotice) return null;                                   // notifications/initialized · cancelled 등 — 답하지 않는다
  const p = m.params || {};
  switch (m.method) {
    case "initialize": {
      const v = PROTOCOLS.includes(p.protocolVersion) ? p.protocolVersion : PROTOCOLS[0];
      return rpcResult(m.id, { protocolVersion: v, capabilities: { tools: { listChanged: false }, prompts: { listChanged: false } },
        serverInfo: { name: "chaekiji-consult", title: "책이지 상담 비서(원격)", version: SERVER_VERSION + "-remote" }, instructions: INSTRUCTIONS });
    }
    case "ping": return rpcResult(m.id, {});
    case "tools/list": return rpcResult(m.id, { tools: TOOL_LIST });
    case "prompts/list": return rpcResult(m.id, { prompts: PROMPTS });
    case "prompts/get": {
      if (p.name !== "consult") return rpcError(m.id, -32602, `unknown prompt: ${p.name}`);
      return rpcResult(m.id, { description: PROMPTS[0].description,
        messages: [{ role: "user", content: { type: "text", text: promptText(p.arguments || {}) } }] });
    }
    case "tools/call": {
      const fn = IMPL[p.name];
      if (!fn) return rpcError(m.id, -32602, `unknown tool: ${p.name}`);
      if (!deps.allow()) return rpcResult(m.id, { content: [{ type: "text", text: "호출 한도 초과(10분에 60회) — 잠시 뒤 다시 시도해 주세요" }], isError: true });
      const ctx = deps.newCtx();
      try {
        const out = await fn(p.arguments || {}, deps, ctx);
        return rpcResult(m.id, { content: [{ type: "text", text: JSON.stringify(out, null, 1) }], isError: false });
      } catch (e) {
        const kind = e instanceof ToolError ? e.kind : "Error";
        return rpcResult(m.id, { content: [{ type: "text", text: `${kind}: ${e && e.message}` }], isError: true });
      }
    }
    default: return rpcError(m.id, -32601, `method not found: ${m.method}`);
  }
}

// [10/17] 사람이 인터넷 창으로 이 주소를 열면 오류 대신 안내 화면. MCP 클라이언트의 GET(Accept에 text/event-stream)은 규격대로 405.
function guidePage(req) {
  const esc = t => String(t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const addr = esc(new URL(req.url).origin + "/mcp");
  return `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>책이지 원격 상담 비서 — 커넥터 주소</title><style>
body{margin:0;background:#f4f7f5;color:#1d2421;font:16px/1.65 system-ui,-apple-system,"Malgun Gothic","Apple SD Gothic Neo",sans-serif;word-break:keep-all}
main{max-width:640px;margin:0 auto;padding:28px 18px 40px}h1{font-size:22px;line-height:1.35;margin:0 0 12px;color:#11463a}
.box{background:#fff;border:1px solid #d5dfda;border-radius:12px;padding:16px 18px;margin:16px 0}ol{margin:0;padding-left:22px}li{margin:6px 0}
code{background:#eef3f0;border-radius:4px;padding:1px 5px;font-size:.95em;overflow-wrap:anywhere}.n{color:#55615b;font-size:14px}a{color:#0b5c8a}
</style></head><body><main>
<h1>이 주소는 claude.ai 커넥터에 넣는 주소입니다</h1>
<p>인터넷 창으로 열면 이 안내만 보이는 것이 정상입니다. AI 프로그램(MCP 클라이언트)이 이 주소로 질문을 보내면, 책이지 상담 비서가 부천시립도서관 상호대차 판정과 안내문을 돌려줍니다.</p>
<div class="box"><b>붙이는 법</b><ol>
<li>claude.ai → 사용자 정의 → 커넥터 → 「+ 추가」 → 「커스텀 커넥터 추가」</li>
<li>이름 「책이지 상담 비서」, 주소 <code>${addr}</code> → 「계속」 → 인증 방식 「로그인 없음」 → 「추가」</li>
<li>새 대화의 「+」 → 커넥터에서 켜고, 이용자의 말을 그대로 입력(예: 나미야 잡화점의 기적 빌리고 싶어요, 상동에서 받을게요)</li>
</ol></div>
<p class="n">시연·검증용입니다. 접수는 하지 않으며, 대출 상태는 정보나루 조회일 전일 기준입니다. 무료 요금제는 커스텀 커넥터를 1개까지 쓸 수 있습니다.</p>
<p class="n">시민용 시연 웹 <a href="https://altarry-prog.github.io/chaekiji/">altarry-prog.github.io/chaekiji</a> · 소스 <a href="https://github.com/altarry-prog/chaekiji">github.com/altarry-prog/chaekiji</a></p>
</main></body></html>`;
}

export async function handleMcp(req, deps) {
  const H = { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" };
  const accept = req.headers.get("Accept") || "";
  if (req.method === "GET" && accept.includes("text/html") && !accept.includes("text/event-stream"))
    return new Response(guidePage(req), { status: 200, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });
  if (req.method !== "POST") return new Response(JSON.stringify(rpcError(null, -32000, "POST만 받습니다(Streamable HTTP · 이어 받기 없음)")),
                                                  { status: 405, headers: { ...H, Allow: "POST" } });
  let body;
  try { body = JSON.parse(await req.text()); }
  catch (e) { return new Response(JSON.stringify(rpcError(null, -32700, "Parse error")), { status: 400, headers: H }); }
  if (Array.isArray(body) && !body.length) return new Response(JSON.stringify(rpcError(null, -32600, "Invalid Request")), { status: 400, headers: H });
  const msgs = Array.isArray(body) ? body : [body];
  const out = [];
  for (const m of msgs) { const r = await handleOne(m, deps); if (r) out.push(r); }
  if (!out.length) return new Response(null, { status: 202, headers: { "Cache-Control": "no-store" } });
  return new Response(JSON.stringify(Array.isArray(body) ? out : out[0]), { status: 200, headers: H });
}

export function _resetForTest() { state.snap = null; state.snapAt = 0; state.bib.clear(); }   // 시험 전용(배포 동작과 무관)
