/* 책이지 Solar 상담 창 — 화면 쪽. 중계(relay/ask.js)의 POST /ask를 부르고, 모델의 답과 도구가 정한 판정을 나란히 보여 준다.
 * 묻는 글은 화면에 남기지 않는다(새로 고치면 사라짐). 키는 화면에 없다(중계의 Cloudflare 비밀값). */
(function () {
  "use strict";
  var RELAY = "https://chaekiji-relay.altarry2.workers.dev";
  var LIBS = ["상동", "꿈빛", "꿈여울", "도당", "동화", "별빛마루", "북부", "송내", "수주", "심곡", "역곡", "역곡밝은", "오정", "원미", "책마루", "한울빛"];
  var POINTS = ["상동역 칙칙폭폭", "숲속", "꿈꾸는새싹", "약대신나는가족", "시정담벼락", "신중동역 칙칙폭폭", "소사칙칙폭폭", "해밀"];
  var LANG_NAME = { ko: "한국어", en: "영어", vi: "베트남어", zh: "중국어", ja: "일본어" };
  // 예시는 11. 2. Solar 실측(같은 지시문·같은 도구, 문의 24건 × 3회)에서 세 번 모두 책을 찾았거나(1~4) 세 번 모두 되물은(5) 문의다.
  // [13:50] 「한강 책 빌리고 싶어요」는 실측(새벽 자료만 쓰는 방식)에서는 되물었지만, 실제 중계에서는 정보나루 검색이 부제에 「한강」이 든 책을 골라
  //   되묻지 않았다(작가 이름만 말하면 한 권을 고르는 도구 쪽 한계, README 3절). 그래서 되묻는 예시를 바꿨다.
  var EXAMPLES = [
    { t: "서울역 노숙자가 편의점에서 야간 알바하는 소설 있죠? 역곡에서 받고 싶어요", p: "역곡", tag: "줄거리로" },
    { t: "나미야 잡하점의 기적 빌릴수있나요", p: "상동", tag: "글자 틀림" },
    { t: "Do you have Human Acts by Han Kang? I'd like to pick it up at Sangdong library.", p: "상동", tag: "영어" },
    { t: "Thư viện có cuốn \"Điều kỳ diệu của tiệm tạp hóa Namiya\" không? Tôi muốn nhận ở thư viện Yeokgok.", p: "역곡", tag: "베트남어" },
    { t: "요즘 많이 읽는 소설 하나 빌려 주세요", p: "상동", tag: "모호한 말" }
  ];
  var $ = function (id) { return document.getElementById(id); };
  var form = $("f"), ta = $("t"), sel = $("p"), lang = $("l"), go = $("go"), out = $("out"), cnt = $("cnt");

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function opt(v, label) { var o = document.createElement("option"); o.value = v; o.textContent = label || v; return o; }
  function day(s) { var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || ""); return m ? m[1] + ". " + (+m[2]) + ". " + (+m[3]) + "." : ""; }

  var g1 = document.createElement("optgroup"); g1.label = "시립도서관";
  LIBS.forEach(function (n) { g1.appendChild(opt(n, n + "도서관")); });
  var g2 = document.createElement("optgroup"); g2.label = "작은도서관(받을 곳)";
  POINTS.forEach(function (n) { g2.appendChild(opt(n)); });
  sel.appendChild(g1); sel.appendChild(g2); sel.value = "상동";

  var ex = $("ex");
  EXAMPLES.forEach(function (e) {
    var b = document.createElement("button");
    b.type = "button";
    b.innerHTML = esc(e.t.length > 34 ? e.t.slice(0, 33) + "…" : e.t) + " <small>(" + esc(e.tag) + ")</small>";
    b.title = e.t;
    b.addEventListener("click", function () { ta.value = e.t; sel.value = e.p; lang.value = "auto"; count(); go.focus(); });
    ex.appendChild(b);
  });
  function count() { cnt.textContent = String(ta.value.length); }
  ta.addEventListener("input", count);

  // 답이 이용자 언어로 쓰였는지 글자 종류로 본다(중계 ask.js guessLang과 같은 기준, 주소는 빼고 셈). 번역의 정확성은 보지 않는다
  function inLang(text, lang) {
    var t = String(text || "").replace(/https?:\/\/\S+/g, " ");
    if (lang === "en") return (t.match(/\b[A-Za-z]{3,}\b/g) || []).length >= 8;
    if (lang === "vi") return /[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]/i.test(t);
    if (lang === "ja") return /[\u3040-\u30ff]/.test(t);
    if (lang === "zh") return (t.match(/[\u4e00-\u9fff]/g) || []).length >= 10;
    return true;
  }

  // 모델의 답 — 글자 그대로 보이고, 도구가 준 누리집 주소와 똑같은 주소만 누를 수 있게 한다(모델이 지어낸 주소는 글로만)
  function answerHtml(text, link) {
    var h = esc(text);
    if (link) h = h.split(esc(link)).join('<a href="' + esc(link) + '" target="_blank" rel="noopener">' + esc(link) + "</a>");
    return h;
  }

  function render(d) {
    var t = d.tool, html = "";
    html += '<article class="card ans"><h2>Solar Pro 4의 답 <small>AI가 쓴 글</small></h2>';
    html += d.answer ? '<p class="txt">' + answerHtml(d.answer, t && t.official_link) + "</p>"
                     : '<p class="note warn">AI가 답 글을 쓰지 못했습니다. 아래 도구 판정을 보시거나 다시 물어 주세요.</p>';
    if (d.answer && d.lang !== "ko" && !inLang(d.answer, d.lang))
      html += '<p class="note warn">AI 답이 이용자 언어(' + esc(LANG_NAME[d.lang] || d.lang) + ')로 쓰이지 않았습니다. 지시문만으로는 번역이 고르지 않아(실측), 도구가 번역 문장을 함께 주는 방식을 다음 과제로 두었습니다.</p>';
    if (t && t.official_link && d.answer && d.answer.indexOf(t.official_link) < 0)
      html += '<p class="note warn">AI 답에 누리집 주소가 그대로 옮겨지지 않았습니다. 아래 상자의 주소가 도구가 정한 것입니다.</p>';
    html += "</article>";

    if (t) {
      var b = t.book || {};
      html += '<article class="card tool"><h2>책이지 도구가 정한 판정 <small>consult_request · 원격 판과 같은 판정</small></h2>';
      html += '<p style="margin:0"><span class="badge">' + esc(t.route_label || t.route) + "</span></p><dl>";
      if (t.book) {
        html += "<dt>책</dt><dd>『" + esc(b.title) + "』" + (b.author ? " " + esc(b.author) : "") +
                (b.isbn13 ? '<br><small style="color:var(--sub)">' + esc([b.publisher, b.year].filter(Boolean).join(" ")) + " · ISBN " + esc(b.isbn13) + "</small>" : "") + "</dd>";
      } else if (t.candidate_books && t.candidate_books.length) {
        html += "<dt>후보</dt><dd>" + t.candidate_books.map(function (c) { return "『" + esc(c.title) + "』 " + esc(c.author || ""); }).join("<br>") + "</dd>";
      }
      html += "<dt>받을 곳</dt><dd>" + esc(t.pickup) + "</dd>";
      if (t.book && (t.available_at.length || t.loaned_at.length)) {
        html += "<dt>대출 가능</dt><dd>" + (t.available_at.length ? esc(t.available_at.join(", ")) : "없음") + "</dd>";
        if (t.loaned_at.length) html += "<dt>대출 중</dt><dd>" + esc(t.loaned_at.join(", ")) + "</dd>";
      }
      if (t.asof && t.route !== "check" && t.route !== "unknown") html += "<dt>기준</dt><dd>정보나루 " + esc(day(t.asof)) + " 조회, 전일 기준</dd>";
      html += "</dl>";
      if (t.official_link) html += '<a class="link" href="' + esc(t.official_link) + '" target="_blank" rel="noopener">공식 누리집에서 이 책 보기 ↗</a>';
      if (t.notice) html += "<details><summary>도구의 안내문(한국어 원문)</summary><p>" + esc(t.notice) + "</p></details>";
      if (t.desk_memo) html += "<details><summary>접수 메모(사서용)</summary><pre>" + esc(t.desk_memo) + "</pre></details>";
      html += "</article>";
    } else {
      html += '<article class="card tool"><h2>책이지 도구가 정한 판정</h2><p style="margin:0">이번에는 AI가 도구를 부르지 않았습니다(어느 책인지 되물은 경우 등). 책 제목이나 저자를 더 적어 다시 물어 주세요.</p></article>';
    }
    var calls = (d.tool_calls || []).map(function (c) { return "「" + c.utterance + "」"; }).join(", ");
    html += '<p class="meta">모델 ' + esc(d.model) + " · 도구 호출 " + (d.tool_calls || []).length + "번" + (calls ? "(" + esc(calls) + ")" : "") +
            " · " + (d.ms / 1000).toFixed(1) + "초 · 언어 " + esc(LANG_NAME[d.lang] || d.lang) + (d.lang_guessed ? "(쓴 글자로 짐작)" : "") +
            (d.recorded ? " · <b>기록됨</b>" : "") + "</p>";
    out.innerHTML = html;
  }

  function fail(msg) { out.innerHTML = '<p class="note err" style="margin-top:0">' + esc(msg) + "</p>"; showOut(); }
  // 좁은 화면(한 줄로 쌓일 때)에서는 답이 묻기 칸 아래에 나오므로 그쪽으로 내려 준다. 넓은 화면은 오른쪽에 바로 보인다
  function showOut() {
    if (!window.matchMedia || !window.matchMedia("(max-width: 959px)").matches) return;
    var still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    try { out.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "start" }); } catch (e) { out.scrollIntoView(); }
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var text = ta.value.trim();
    if (!text) { fail("물을 말을 적어 주세요."); ta.focus(); return; }
    go.disabled = true;
    out.innerHTML = '<div class="card"><p class="wait" style="margin:0"><span class="dot" aria-hidden="true"></span>묻는 중입니다. 보통 5~20초 걸립니다.</p></div>';
    showOut();
    var ctl = ("AbortController" in window) ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); }, 90000);
    fetch(RELAY + "/ask", { method: "POST", headers: Object.assign({ "Content-Type": "application/json" }, recHeaders()), signal: ctl ? ctl.signal : undefined,
                            body: JSON.stringify({ text: text, pickup: sel.value, lang: lang.value }) })
      .then(function (r) { return r.json().catch(function () { return { error: "http", message: "중계가 알 수 없는 답을 주었습니다(" + r.status + ")." }; }); })
      .then(function (d) {
        if (d && d.ok) render(d);
        else fail((d && d.message) || "지금은 답을 만들지 못했습니다. 잠시 뒤에 다시 물어 주세요.");
      })
      .catch(function (e) {
        fail(e && e.name === "AbortError" ? "90초 안에 답이 오지 않았습니다. 잠시 뒤에 다시 물어 주세요." : "책이지 중계에 닿지 못했습니다. 인터넷 연결을 확인해 주세요.");
      })
      .then(function () { clearTimeout(timer); go.disabled = false; });
  });

  // ── 담당자 기록 모드(11. 2.) — 기록 암호는 이 브라우저에만 둔다(서버로는 머리글로만 보냄). 글은 중계의 비공개 저장 공간에 90일 ──
  var REC_KEY = "chaekiji-ask-rec", recTok = "";
  try { recTok = localStorage.getItem(REC_KEY) || ""; } catch (e) { recTok = ""; }
  function recHeaders() { return recTok ? { "X-Record-Token": recTok } : {}; }
  function recGet(path) {
    return fetch(RELAY + path, { headers: recHeaders() })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { return { status: r.status, d: d }; }); });
  }
  var rs = $("recstate"), rin = $("recin"), rctl = $("recctl"), rinfo = $("recinfo"), rmsg = $("recmsg"), rtok = $("rectok");
  function recMsg(text, bad) { rmsg.hidden = !text; rmsg.className = "note " + (bad ? "err" : "warn"); rmsg.textContent = text || ""; }
  function recUI() {
    var on = !!recTok;
    rs.textContent = on ? "켜짐" : "꺼짐"; rs.className = "pill" + (on ? " on" : "");
    rin.hidden = on; rctl.hidden = !on;
    rinfo.textContent = on ? "이 브라우저에서 묻는 것은 문장·답·판정까지 기록됩니다." : "";
  }
  recUI();
  $("recon").addEventListener("click", function () {
    var tok = rtok.value.trim();
    if (tok.length < 12) { recMsg("기록 암호는 12자 이상입니다.", true); return; }
    recTok = tok;
    recGet("/ask/records?limit=1").then(function (x) {
      if (x.status === 200) {
        try { localStorage.setItem(REC_KEY, tok); } catch (e) { /* 저장이 막힌 브라우저는 이 창에서만 켜짐 */ }
        rtok.value = ""; recUI(); recMsg("기록 모드를 켰습니다. 지금부터 묻는 것은 기록됩니다.", false);
      } else { recTok = ""; recUI(); recMsg((x.d && x.d.message) || "기록 암호를 확인하지 못했습니다.", true); }
    }).catch(function () { recTok = ""; recUI(); recMsg("책이지 중계에 닿지 못했습니다.", true); });
  });
  $("recoff").addEventListener("click", function () {
    recTok = ""; try { localStorage.removeItem(REC_KEY); } catch (e) {}
    recUI(); recMsg("기록 모드를 껐습니다. 이미 기록된 것은 그대로 남습니다.", false);
  });
  function csvCell(v) { var s = Array.isArray(v) ? v.join(", ") : (v == null ? "" : String(v)); return '"' + s.replace(/"/g, '""') + '"'; }
  var COLS = [["t", "시각"], ["text", "이용자의 말"], ["pickup", "받을 도서관"], ["lang", "언어"], ["ok", "결과"], ["route_label", "판정(도구)"],
              ["book_title", "책"], ["book_author", "저자"], ["isbn13", "ISBN"], ["asof", "조회일"], ["available_at", "대출 가능 관"],
              ["answer", "AI 답"], ["tool_calls", "모델이 도구에 넘긴 말"], ["sec", "걸린 시간(초)"], ["model", "모델"], ["in_tok", "입력 토큰"],
              ["out_tok", "출력 토큰"], ["data_calls", "자료 조회 수"], ["official_link", "누리집 주소"], ["alpas", "알파스 확인(직접 적기)"],
              ["same", "같음/다름"], ["why", "다르면 까닭"]];
  $("recdl").addEventListener("click", function () {
    var all = [], btn = this; btn.disabled = true; recMsg("기록을 모으는 중입니다…", false);
    function next(cursor) {
      return recGet("/ask/records" + (cursor ? "?cursor=" + encodeURIComponent(cursor) : "")).then(function (x) {
        if (x.status !== 200) throw new Error((x.d && x.d.message) || "기록을 받지 못했습니다.");
        all = all.concat(x.d.records || []);
        return x.d.cursor ? next(x.d.cursor) : null;
      });
    }
    next(null).then(function () {
      var rows = [COLS.map(function (c) { return csvCell(c[1]); }).join(",")];
      all.forEach(function (r) {
        var u = r.usage || {};
        var v = { sec: r.ms ? (r.ms / 1000).toFixed(1) : "", in_tok: u.prompt_tokens || "", out_tok: u.completion_tokens || "",
                  ok: r.ok ? "답함" : ("오류 " + (r.error || "")), alpas: "", same: "", why: "" };
        rows.push(COLS.map(function (c) { return csvCell(c[0] in v ? v[c[0]] : r[c[0]]); }).join(","));
      });
      var blob = new Blob(["﻿" + rows.join("\r\n")], { type: "text/csv;charset=utf-8" });
      var a = document.createElement("a"), d = new Date();
      a.href = URL.createObjectURL(blob);
      a.download = "chaekiji-ask-records_" + d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0") + ".csv";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
      recMsg("기록 " + all.length + "건을 내려받았습니다(엑셀에서 열 수 있는 CSV).", false);
    }).catch(function (e) { recMsg(e.message || "기록을 받지 못했습니다.", true); })
      .then(function () { btn.disabled = false; });
  });
  var RLABEL = { visit: "바로 이용", ill: "관내 상호대차", reserve: "예약 권장", sea: "책바다 안내", unknown: "도서 미확정", check: "소장 확인 불가", none: "도구 안 부름", error: "오류" };
  $("recstats").addEventListener("click", function () {
    recGet("/ask/stats").then(function (x) {
      if (x.status !== 200) { recMsg((x.d && x.d.message) || "건수를 받지 못했습니다.", true); return; }
      var days = Object.keys(x.d.days || {}).sort().reverse().slice(0, 14);
      var html = "<b>모든 이용 " + x.d.total + "건</b>(글 없이 센 것, 최근 14일까지 표시)<ul class=\"stat\">" + days.map(function (k) {
        var d = x.d.days[k], parts = Object.keys(d.routes).map(function (rt) { return (RLABEL[rt] || rt) + " " + d.routes[rt]; });
        return "<li>" + (+k.slice(5, 7)) + ". " + (+k.slice(8, 10)) + ". " + d.total + "건(기록 " + d.recorded + " · 점검 " + d.check + ") · " + esc(parts.join(" · ")) + "</li>";
      }).join("") + "</ul>";
      rmsg.hidden = false; rmsg.className = "note warn"; rmsg.innerHTML = html;
    }).catch(function () { recMsg("책이지 중계에 닿지 못했습니다.", true); });
  });
})();
