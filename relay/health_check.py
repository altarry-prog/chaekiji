#!/usr/bin/env python3
"""운영 점검 — 심사위원이 여는 세 곳(시연 웹·중계·원격 상담 비서)이 지금 살아 있는지 확인한다.

- 정보나루를 부르지 않는다(호출 한도 0건). /health, /mcp 안내 화면, 초기화·도구 목록만 부른다.
- 아무것도 커밋하지 않는다. 결과는 깃허브 Actions의 초록(통과)·빨강(실패)과 요약 표로만 남는다.
- 배포된 것이 저장소와 같은지도 본다(시연 웹 첫 화면·캐시 번호, 원격 상담 비서 판 번호).

실행(저장소 맨 위에서): python3 relay/health_check.py
주소 바꾸기(시험용): CHAEKIJI_WEB, CHAEKIJI_RELAY_URL / 새벽 자료 허용 날수: CHAEKIJI_HEALTH_MAX_DAYS(기본 1)
"""
import datetime
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

WEB = os.environ.get("CHAEKIJI_WEB", "https://altarry-prog.github.io/chaekiji").rstrip("/")
RELAY = os.environ.get("CHAEKIJI_RELAY_URL", "https://chaekiji-relay.altarry2.workers.dev").rstrip("/")
MAX_DAYS = int(os.environ.get("CHAEKIJI_HEALTH_MAX_DAYS", "1"))
FROZEN_FROM, FROZEN_UNTIL = datetime.date(2026, 11, 8), datetime.date(2026, 11, 26)   # [10/19] 심사 기간 고정 자료(naru.snapshot_ok와 같은 값) — 결선 뒤 지움
UA = "chaekiji-health/1.0 (+https://github.com/altarry-prog/chaekiji)"   # 파이썬 기본 이름은 Cloudflare가 403(1010)으로 막는다
ROOT = pathlib.Path(__file__).resolve().parent.parent
KST = datetime.timezone(datetime.timedelta(hours=9))                     # 깃허브 서버는 UTC — 날짜는 한국 날짜로


def call(url, method="GET", headers=None, body=None, timeout=20):
    """(상태 코드, 본문). 연결이 끊기거나 5xx면 5초 뒤 한 번 더 — 일시적인 끊김에 빨강이 뜨지 않게."""
    h = {"User-Agent": UA}
    h.update(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    last = "?"
    for attempt in range(2):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h, method=method), timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            if e.code < 500 or attempt == 1:
                return e.code, text
            last = f"HTTP {e.code}"
        except Exception as e:                                           # 끊김·시간 초과
            last = f"{type(e).__name__}: {e}"
        time.sleep(5)
    return 0, last


def code(st, body):
    """상태 코드를 사람이 읽게 — 연결이 안 되면 까닭을 붙인다."""
    return f"연결 안 됨({body[:80]})" if st == 0 else f"{st}"


def repo_text(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def web_cache():
    st, body = call(f"{WEB}/sw.js")
    live = re.search(r"const CACHE = '([^']+)'", body)
    repo = re.search(r"const CACHE = '([^']+)'", repo_text("sw.js"))
    live_v, repo_v = (live.group(1) if live else "?"), (repo.group(1) if repo else "?")
    return st == 200 and live_v == repo_v and live_v != "?", f"{code(st, body)} · 배포 {live_v} · 저장소 {repo_v}"


def web_index():
    st, body = call(f"{WEB}/")
    same = body == repo_text("index.html")
    ver = re.search(r"v1\.\d+\.\d+", body)
    return st == 200 and same, f"{code(st, body)} · 저장소와 {'같음' if same else '다름'} · {ver.group(0) if ver else '판 표시 없음'}"


def web_daily():
    st, body = call(f"{WEB}/data/holdings-today.json")
    if st != 200:
        return False, code(st, body)
    j = json.loads(body)
    asof = datetime.date.fromisoformat(j["asof"])
    today = datetime.datetime.now(KST).date()
    age = (today - asof).days
    frozen = FROZEN_FROM <= asof <= today <= FROZEN_UNTIL               # 동결 뒤 11. 8. 자료는 결선까지 정상
    ok = (0 <= age <= MAX_DAYS or frozen) and not j.get("partial")
    return ok, f"{st} · 조회일 {j['asof']}({age}일 전{' · 심사 기간 고정 자료' if frozen and age > MAX_DAYS else ''}) · 호출 {j.get('calls')}회{' · 일부만 받음' if j.get('partial') else ''}"


def relay_health():
    st, body = call(f"{RELAY}/health")
    if st != 200:
        return False, code(st, body)
    j = json.loads(body)
    return j.get("ok") is True and j.get("keyed") is True, f"{st} · ok={j.get('ok')} · 키 {'있음' if j.get('keyed') else '없음'}"


def mcp_page():
    st, body = call(f"{RELAY}/mcp", headers={"Accept": "text/html"})
    return st == 200 and "커넥터에 넣는 주소" in body, code(st, body)


def mcp_get():
    st, body = call(f"{RELAY}/mcp", headers={"Accept": "text/event-stream"})
    return st == 405, f"{code(st, body)}(규격상 405가 맞음)"


def mcp_tools():
    H = {"Accept": "application/json, text/event-stream"}
    st, body = call(f"{RELAY}/mcp", "POST", H, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "chaekiji-health", "version": "1.0"}}})
    if st != 200:
        return False, f"초기화 {code(st, body)}"
    live_v = json.loads(body)["result"]["serverInfo"]["version"]
    m = re.search(r'SERVER_VERSION = "([^"]+)"', repo_text("relay/mcp_data.js"))
    repo_v = (m.group(1) + "-remote") if m else "?"
    st2, _ = call(f"{RELAY}/mcp", "POST", H, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    st3, body3 = call(f"{RELAY}/mcp", "POST", H, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t["name"] for t in json.loads(body3)["result"]["tools"]] if st3 == 200 else []
    need = {"consult_request", "search_item", "check_availability"}
    ok = st2 == 202 and need <= set(names) and live_v == repo_v
    return ok, f"판 {live_v}(저장소 {repo_v}) · 알림 {st2} · 도구 {len(names)}종"


CHECKS = [
    ("시연 웹 — 배포된 캐시 번호가 저장소와 같음", web_cache),
    ("시연 웹 — 첫 화면이 저장소와 같음", web_index),
    (f"시연 웹 — 새벽 자료가 {MAX_DAYS}일 이내", web_daily),
    ("중계 — 상태 확인(/health)", relay_health),
    ("원격 상담 비서 — 인터넷 창으로 열면 안내 화면", mcp_page),
    ("원격 상담 비서 — 프로그램의 GET은 405", mcp_get),
    ("원격 상담 비서 — 초기화·도구 목록·판 번호", mcp_tools),
]


def main():
    now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    rows = []
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:                                           # 응답 모양이 다르면 실패로 적는다
            ok, detail = False, f"{type(e).__name__}: {e}"
        rows.append((name, bool(ok), detail))
        print(("✓ " if ok else "✗ ") + name + " — " + detail)
    passed = sum(1 for _, ok, _ in rows if ok)
    line = f"운영 점검 {now} KST — {passed}/{len(rows)} 통과 (정보나루 호출 0건)"
    print("\n" + line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### {line}\n\n| 확인 | 결과 | 내용 |\n|---|---|---|\n")
            for name, ok, detail in rows:
                f.write(f"| {name} | {'통과' if ok else '**실패**'} | {detail} |\n")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
