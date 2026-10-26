"""전일 기준 자료가 하루 사이 얼마나 그대로인지 — 매일 새벽 자료의 깃 이력으로 센다(정보나루 호출 없음).

책이지는 정보나루의 「조회일 전일 기준」 대출 상태를 쓴다. 이 스크립트는 저장소에 날마다 쌓인
`data/holdings-today.json`(시연 도서 5종 × 부천 16관)을 이어지는 두 날씩 견줘 다음을 센다.

- 「대출 가능」 유지: 앞날 「대출 가능」이던 쌍이 다음 날 자료에서도 「대출 가능」인 비율
- 소장 쌍의 상태 바뀜: 앞날 소장(대출 가능·대출 중)이던 쌍의 상태가 다음 날 달라진 비율

한계: 실시간 도서관리시스템과 견준 값이 아니라 정보나루 자료끼리 하루 차이를 본 것이다.
표본은 시연 도서 5종 × 16관이라 작고, 인기 도서 위주다. 깃 이력이 있는 사본(git clone)에서만 돈다.

    python server/lab/stability.py                     # 이력 전체
    python server/lab/stability.py --until 2026-10-22  # 그날까지
    python server/lab/stability.py --write             # server/lab/out/에 기록표(md·json) 저장
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DATA = "data/holdings-today.json"
HELD = ("ok", "busy")


def snapshots(until=None):
    """날짜(asof)마다 그날의 마지막 자료 하나. 앞뒤가 잘린 자료(partial)는 뺀다."""
    out = subprocess.run(["git", "-C", ROOT, "log", "--format=%H %cI", "--", DATA],
                         capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        sys.exit("깃 이력을 읽지 못했습니다 — git clone 한 사본에서 실행하세요.")
    seen = {}
    for line in out.stdout.split("\n"):
        if not line.strip():
            continue
        commit, when = line.split(" ", 1)
        raw = subprocess.run(["git", "-C", ROOT, "show", commit + ":" + DATA],
                             capture_output=True, text=True).stdout
        try:
            doc = json.loads(raw)
        except ValueError:
            continue
        day = doc.get("asof")
        if not day or day in seen or doc.get("partial"):
            continue  # 깃 로그는 새것부터 — 처음 본 것이 그날의 마지막 자료
        if until and day > until:
            continue
        seen[day] = {"commit": commit[:7], "committed": when, "holdings": doc.get("holdings", {})}
    return dict(sorted(seen.items()))


def compare(snaps):
    days = list(snaps)
    rows, ok_total, ok_kept, held_total, held_changed = [], 0, 0, 0, 0
    for a, b in zip(days, days[1:]):
        ha, hb = snaps[a]["holdings"], snaps[b]["holdings"]
        r = {"from": a, "to": b, "ok": 0, "ok_kept": 0, "held": 0, "held_changed": 0, "changes": []}
        for isbn, libs in ha.items():
            for lib, sa in libs.items():
                sb = hb.get(isbn, {}).get(lib)
                if sb is None:
                    continue
                if sa == "ok":
                    r["ok"] += 1
                    r["ok_kept"] += sb == "ok"
                if sa in HELD:
                    r["held"] += 1
                    if sb != sa:
                        r["held_changed"] += 1
                        r["changes"].append("%s %s %s→%s" % (isbn, lib, sa, sb))
        rows.append(r)
        ok_total += r["ok"]
        ok_kept += r["ok_kept"]
        held_total += r["held"]
        held_changed += r["held_changed"]
    pct = lambda n, d: round(100.0 * n / d, 1) if d else None
    return {
        "first": days[0] if days else None, "last": days[-1] if days else None,
        "snapshots": len(days), "pairs": len(rows),
        "ok_total": ok_total, "ok_kept": ok_kept, "ok_kept_pct": pct(ok_kept, ok_total),
        "held_total": held_total, "held_changed": held_changed, "held_changed_pct": pct(held_changed, held_total),
        "rows": rows,
    }


LABEL = {"ok": "대출 가능", "busy": "대출 중", "none": "미소장"}


def to_md(res, snaps):
    s = res
    lines = [
        "# 전일 기준 자료의 하루 사이 유지율 — %s ~ %s" % (s["first"], s["last"]),
        "",
        "- 만든 방법: `python server/lab/stability.py --write` — 저장소의 매일 새벽 자료(`data/holdings-today.json`) 깃 이력을 이어지는 두 날씩 견줌. 정보나루를 새로 부르지 않음",
        "- 자료: 시연 도서 5종 × 부천시립도서관 16관, 날짜마다 그날 마지막 자료 하나(%d일 치, 비교 %d쌍)" % (s["snapshots"], s["pairs"]),
        "- **한계**: 실시간 도서관리시스템과 견준 값이 아니라 정보나루 자료끼리의 하루 차이다. 표본이 작고 인기 도서 위주라 참고용이다",
        "",
        "## 한눈에",
        "",
        "| 지표 | 값 |",
        "|---|---|",
        "| 앞날 「대출 가능」이 다음 날도 「대출 가능」 | **%d / %d (%s%%)** |" % (s["ok_kept"], s["ok_total"], s["ok_kept_pct"]),
        "| 앞날 소장(대출 가능·대출 중) 쌍의 상태가 다음 날 바뀜 | %d / %d (%s%%) |" % (s["held_changed"], s["held_total"], s["held_changed_pct"]),
        "",
        "## 날짜별",
        "",
        "| 앞날 → 다음 날 | 「대출 가능」 유지 | 소장 쌍 상태 바뀜 |",
        "|---|---|---|",
    ]
    for r in s["rows"]:
        lines.append("| %s → %s | %d / %d | %d / %d |" % (r["from"], r["to"], r["ok_kept"], r["ok"], r["held_changed"], r["held"]))
    lines += ["", "## 바뀐 쌍(ISBN · 도서관 · 앞날→다음 날)", ""]
    for r in s["rows"]:
        for c in r["changes"]:
            isbn, lib, move = c.split(" ")
            a, b = move.split("→")
            lines.append("- %s → %s: %s · %s · %s → %s" % (r["from"], r["to"], isbn, lib, LABEL.get(a, a), LABEL.get(b, b)))
    lines += ["", "## 쓴 자료(날짜 · 커밋)", ""]
    for day, v in snaps.items():
        lines.append("- %s · `%s`" % (day, v["commit"]))
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--until", help="이 날짜(YYYY-MM-DD)까지의 자료만")
    ap.add_argument("--write", action="store_true", help="server/lab/out/에 기록표 저장")
    args = ap.parse_args()
    snaps = snapshots(args.until)
    if len(snaps) < 2:
        sys.exit("견줄 날짜가 두 날 이상 필요합니다.")
    res = compare(snaps)
    print("「대출 가능」 유지 %d/%d (%s%%) · 소장 쌍 상태 바뀜 %d/%d (%s%%) · %s~%s, %d일 치" % (
        res["ok_kept"], res["ok_total"], res["ok_kept_pct"], res["held_changed"], res["held_total"],
        res["held_changed_pct"], res["first"], res["last"], res["snapshots"]))
    if args.write:
        base = os.path.join(HERE, "out", "stability_%s_%s" % (res["first"], res["last"]))
        with open(base + ".md", "w", encoding="utf-8") as f:
            f.write(to_md(res, snaps))
        with open(base + ".json", "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in res.items()}, f, ensure_ascii=False, indent=1)
        print("저장:", os.path.relpath(base + ".md", ROOT))


if __name__ == "__main__":
    main()
