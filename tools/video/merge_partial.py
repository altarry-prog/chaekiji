# -*- coding: utf-8 -*-
"""일부 장면만 다시 만든 음성(pick_best.py를 거친 폴더)을 본 음성 폴더에 넣고, 기록.json·받아쓰기.json의 그 장면 줄만 바꾼다.
전체_이어듣기.mp3도 본 폴더 음성으로 다시 잇는다. 사용: python3 tools/video/merge_partial.py <부분 폴더> <본 폴더>"""
import json, os, shutil, subprocess, sys
part, main = sys.argv[1], sys.argv[2]
def load(d, n):
    return json.load(open(os.path.join(d, n), encoding="utf-8"))
pr, mr = load(part, "기록.json"), load(main, "기록.json")
pa, ma = load(part, "받아쓰기.json"), load(main, "받아쓰기.json")
new = {it["file"]: it for it in pr["items"]}
for f in new:
    shutil.copy(os.path.join(part, f), os.path.join(main, f))
mr["items"] = [new.get(it["file"], it) for it in mr["items"]] + [it for f, it in new.items() if f not in {x["file"] for x in mr["items"]}]
mr["items"].sort(key=lambda x: x["file"])
mr["합계_초"] = round(sum(x["seconds"] for x in mr["items"]), 1)
newa = {it["file"]: it for it in pa["items"]}
ma["items"] = [newa.get(it["file"], it) for it in ma["items"]]
ma.setdefault("후보별_비율", {}).update(pa.get("후보별_비율", {}))
gap = os.path.join(main, "_gap.wav")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "0.8", "-c:a", "pcm_s16le", gap], check=True)
parts = []
for it in mr["items"]:
    parts += [os.path.join(main, it["file"]), gap]
parts = parts[:-1]
args = ["ffmpeg", "-y", "-loglevel", "error"]
for x in parts:
    args += ["-i", x]
filt = "".join(f"[{i}:a]aresample=44100,aformat=channel_layouts=mono[a{i}];" for i in range(len(parts)))
filt += "".join(f"[a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[a]"
args += ["-filter_complex", filt, "-map", "[a]", "-codec:a", "libmp3lame", "-q:a", "4", os.path.join(main, "전체_이어듣기.mp3")]
subprocess.run(args, check=True)
os.remove(gap)
json.dump(mr, open(os.path.join(main, "기록.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ma, open(os.path.join(main, "받아쓰기.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({"바꾼 장면": sorted(new), "합계_초": mr["합계_초"]}, ensure_ascii=False))
