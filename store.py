# -*- coding: utf-8 -*-
"""[v0.3.1 실험실] 신청·위임 이력의 영속 저장 계층 — 시험 구현.
v0.3까지 위임장·신청·회원 현황(모의)은 메모리에만 있어 서버를 끄면 사라졌다.
CHAEKIJI_STORE=파일경로 를 주면 SQLite(파이썬 표준 라이브러리, 외부 패키지 없음)에 저장하고,
서버를 다시 켜면 그대로 복원한다. 환경변수가 없으면 v0.3과 똑같이 메모리에만 둔다.

저장 대상(전부 모의 데이터): 위임장(mandates) · 위임 일련번호 · 신청(requests) · 회원 현황(members — 한도 계산용 모의값)
하지 않는 것(운영 전환 과제, docs/이력저장-감사기록-설계.md): 암호화, 접근 통제, 보존 기간·파기, 동시 접근, 운영 DB 스키마."""
import os, json, sqlite3, datetime

PATH = os.environ.get("CHAEKIJI_STORE")

def enabled() -> bool:
    return bool(PATH)

def _conn():
    c = sqlite3.connect(PATH)
    c.execute("CREATE TABLE IF NOT EXISTS mandates (mandate_id TEXT PRIMARY KEY, user TEXT, active INTEGER, body TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS requests (no TEXT PRIMARY KEY, member TEXT, status TEXT, body TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS members (member_id TEXT PRIMARY KEY, body TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
    return c

def save(mandates: dict, mseq: list, requests: dict, members: dict):
    """상태가 바뀔 때마다 전체를 덮어쓴다(수십 건 규모의 시험 구현 — 운영은 행 단위 트랜잭션)."""
    if not PATH: return
    with _conn() as c:
        for mid, m in mandates.items():
            c.execute("INSERT OR REPLACE INTO mandates VALUES (?,?,?,?)",
                      (mid, m["user"], 1 if m["active"] else 0, json.dumps(m, ensure_ascii=False)))
        for no, r in requests.items():
            c.execute("INSERT OR REPLACE INTO requests VALUES (?,?,?,?)",
                      (no, r["member"], r["status"], json.dumps(r, ensure_ascii=False)))
        for mid, m in members.items():
            c.execute("INSERT OR REPLACE INTO members VALUES (?,?)", (mid, json.dumps(m, ensure_ascii=False)))
        c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", ("mseq", str(mseq[0])))
        c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
                  ("saved_at", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

def load():
    """저장된 상태를 돌려준다. 파일이 없거나 비어 있으면 None."""
    if not PATH or not os.path.exists(PATH): return None
    with _conn() as c:
        mandates = {row[0]: json.loads(row[1]) for row in c.execute("SELECT mandate_id, body FROM mandates")}
        requests = {row[0]: json.loads(row[1]) for row in c.execute("SELECT no, body FROM requests")}
        members  = {row[0]: json.loads(row[1]) for row in c.execute("SELECT member_id, body FROM members")}
        mseq = c.execute("SELECT v FROM meta WHERE k='mseq'").fetchone()
    if not (mandates or requests or members): return None
    return {"mandates": mandates, "requests": requests, "members": members,
            "mseq": int(mseq[0]) if mseq else 0}

def describe() -> str:
    if not PATH: return "저장 계층 꺼짐(메모리만)"
    s = load()
    if not s: return f"저장 계층 켜짐({PATH}) — 비어 있음"
    return (f"저장 계층 켜짐({PATH}) — 위임 {len(s['mandates'])}건 · 신청 {len(s['requests'])}건 · "
            f"회원 현황 {len(s['members'])}명(모의)")
