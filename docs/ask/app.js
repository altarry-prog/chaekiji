/* 책이지 Solar 상담 창 — 화면 쪽. 중계(relay/ask.js)의 POST /ask를 부르고, 모델의 답과 도구가 정한 판정을 나란히 보여 준다.
 * 묻는 글은 화면에 남기지 않는다(새로 고치면 사라짐). 키는 화면에 없다(중계의 Cloudflare 비밀값). */
(function () {
  "use strict";
  var RELAY = "https://chaekiji-relay.altarry2.workers.dev";
  var LIBS = ["상동", "꿈빛", "꿈여울", "도당", "동화", "별빛마루", "북부", "송내", "수주", "심곡", "역곡", "역곡밝은", "오정", "원미", "책마루", "한울빛"];
  var POINTS = ["상동역 칙칙폭폭", "숲속", "꿈꾸는새싹", "약대신나는가족", "시정담벼락", "신중동역 칙칙폭폭", "소사칙칙폭폭", "해밀"];
  var LANG_NAME = { ko: "한국어", en: "영어", vi: "베트남어", zh: "중국어", ja: "일본어" };
  var EXAMPLES = [
    { t: "한강 작가가 광주 이야기 쓴 책 있잖아요, 역곡에서 받을 수 있어요?", p: "역곡", tag: "내용·저자로" },
    { t: "나미야 잡화점의 기적 빌리고 싶어요", p: "상동", tag: "제목으로" },
    { t: "Do you have Human Acts by Han Kang? I'd like to pick it up at Sangdong library.", p: "상동", tag: "영어" },
    { t: "Tôi muốn mượn cuốn \"Cửa hàng tiện lợi bất tiện\".", p: "상동", tag: "베트남어" },
    { t: "한강 책 빌리고 싶어요", p: "상동", tag: "모호한 말" }
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
            " · " + (d.ms / 1000).toFixed(1) + "초 · 언어 " + esc(LANG_NAME[d.lang] || d.lang) + (d.lang_guessed ? "(쓴 글자로 짐작)" : "") + "</p>";
    out.innerHTML = html;
  }

  function fail(msg) { out.innerHTML = '<p class="note err">' + esc(msg) + "</p>"; }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var text = ta.value.trim();
    if (!text) { fail("물을 말을 적어 주세요."); ta.focus(); return; }
    go.disabled = true;
    out.innerHTML = '<p class="wait"><span class="dot" aria-hidden="true"></span>묻는 중입니다. 보통 5~20초 걸립니다.</p>';
    var ctl = ("AbortController" in window) ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); }, 90000);
    fetch(RELAY + "/ask", { method: "POST", headers: { "Content-Type": "application/json" }, signal: ctl ? ctl.signal : undefined,
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
})();
