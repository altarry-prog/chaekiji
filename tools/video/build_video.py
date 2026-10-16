#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""record.py가 남긴 화면 묶음(rec/frames/*.jpg + rec/captions.json) → mp4 · 자막(SRT) · 구성표(md).

  python3 tools/video/build_video.py            # out/[시연영상]_부천시_책이지(_초안).mp4 · .srt · _구성표.md
  python3 tools/video/build_video.py --no-video # 자막·구성표만

- 화면이 바뀐 순간마다 받은 장면을 다음 장면까지 그대로 두는 방식(ffconcat)으로 이어 붙이고 30fps H.264(1920x1080)로 만든다.
- 자막은 화면에 글이 나타난 순간을 그대로 받아 적은 것(cues). 한 줄 40자 안팎, 한 번에 3줄까지.
- 길이가 5분을 넘으면 알린다(챌린지 규격: 약 5분 이내 mp4)."""
import sys, os, json, subprocess, math, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--rec", default=os.path.join(HERE, "rec"))
ap.add_argument("--out", default=os.path.join(HERE, "out"))
ap.add_argument("--name", default="[시연영상]_부천시_책이지")
ap.add_argument("--no-video", action="store_true")
A = ap.parse_args()
os.makedirs(A.out, exist_ok=True)
J = json.load(open(os.path.join(A.rec, "captions.json"), encoding="utf-8"))
t0, end = J["t0"], J["end"]
draft = bool(J.get("badge"))
base = os.path.join(A.out, A.name + ("_초안" if draft else ""))
frames = sorted(J["frames"], key=lambda x: x[0])

# 1) ffconcat — 화면이 바뀐 순간마다 한 장, 다음 장까지 그대로 둔다
starts = [max(ts - t0, 0.0) for ts, _, _ in frames]
items = []
for i, (ts, _, fn) in enumerate(frames):
    s = starts[i]
    nxt = starts[i + 1] if i + 1 < len(frames) else end
    if nxt <= 0 or s >= end:
        continue
    nxt = min(nxt, end)
    if nxt - s > 0:
        items.append((fn, nxt - s))
lst = os.path.join(A.rec, "frames.txt")
with open(lst, "w") as f:
    f.write("ffconcat version 1.0\n")
    for fn, d in items:
        f.write(f"file 'frames/{fn}'\nduration {d:.4f}\n")
    f.write(f"file 'frames/{items[-1][0]}'\n")
total = sum(d for _, d in items)
print(f"장면 {len(items)}장 · 길이 {int(total // 60)}분 {total % 60:.1f}초")
if total > 300:
    print("※ 5분을 넘습니다 — 챌린지 규격(약 5분 이내)에 맞게 장면을 줄이세요")
if not A.no_video:
    title = "책이지 — 상호대차 상담 비서 시연영상" + ("(초안)" if draft else "")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-vf", "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-profile:v", "high",
                    "-movflags", "+faststart", "-metadata", f"title={title}", base + ".mp4"], check=True)
    print("영상", base + ".mp4", f"{os.path.getsize(base + '.mp4') / 1e6:.1f}MB")


# 2) SRT — 한 줄 40자 안팎, 끝줄이 짧게 남지 않게 고르게 나눈다
def wrap(text, w=40):
    text = " ".join(text.split())
    if len(text) <= w:
        return [text]
    k = math.ceil(len(text) / w)
    tw = math.ceil(len(text) / k) + 2
    while True:
        lines, cur = [], ""
        for word in text.split(" "):
            if cur and len(cur) + 1 + len(word) > tw:
                lines.append(cur); cur = word
            else:
                cur = (cur + " " + word).strip()
        if cur:
            lines.append(cur)
        if len(lines) <= k or tw > w + 12:
            return lines
        tw += 2


def ts(t):
    ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


cues = sorted(J["cues"], key=lambda x: x[0])
out = []
for i, (t, parts) in enumerate(cues):
    t_next = cues[i + 1][0] if i + 1 < len(cues) else end
    blocks = [ln for p in parts for ln in wrap(p)]
    groups, cur = [], []
    for ln in blocks:                       # 한 화면 자막은 3줄까지
        if len(cur) == 3:
            groups.append(cur); cur = []
        cur.append(ln)
    if cur:
        groups.append(cur)
    tot = sum(len("".join(g)) for g in groups)
    a = t
    for g in groups:
        d = (t_next - t) * len("".join(g)) / tot
        out.append((a, a + d - 0.04, "\n".join(g))); a += d
with open(base + ".srt", "w", encoding="utf-8") as f:
    for n, (a, b, c) in enumerate(out, 1):
        f.write(f"{n}\n{ts(a)} --> {ts(b)}\n{c}\n\n")
print("자막", base + ".srt", len(out), "개")

# 3) 구성표 — 장면별 시각·화면·화면 글
mm = lambda t: f"{int(t // 60)}:{int(t % 60):02d}"
marks = [m for m in J["marks"] if m[1] != "종료"]
rows = []
for i, m in enumerate(marks):
    t, name, screen = m[0], m[1], (m[2] if len(m) > 2 else "")
    t2 = marks[i + 1][0] if i + 1 < len(marks) else end
    said = [" — ".join(p) for c, p in cues if t <= c < t2]
    rows.append(f"| {mm(t)} | {name.split(' ', 1)[1]} | {screen} | {'<br>'.join(said)} |")
md = [f"# 시연영상 구성표{' (초안)' if draft else ''}",
      "",
      f"길이 {int(total // 60)}분 {round(total % 60)}초 · 1920×1080 · 30fps · 자막만(무음)" + (f" · 화면 오른쪽 위 「{J['badge']}」 표시" if draft else ""),
      "",
      "| 시각 | 장면 | 화면 | 화면 글(자막과 같음) |",
      "|---|---|---|---|"] + rows
open(base + "_구성표.md", "w", encoding="utf-8").write("\n".join(md) + "\n")
print("구성표", base + "_구성표.md")
