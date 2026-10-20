"""장면마다 여러 번 만든 음성(_take0~N) 가운데 받아쓰기(음성 인식)가 원고와 가장 같게 들은 것 하나를 고른다.
고른 것은 「장면_속도1.0.mp3」로 이름을 바꾸고 나머지는 지운다. 고른 것들을 0.8초 쉬고 이어 붙여 「전체_이어듣기.mp3」를 만든다.
기록.json·받아쓰기.json은 고른 것 기준으로 다시 쓰고, 후보별 점수도 남긴다. 숫자를 아라비아 숫자로 적은 차이는 점수에 영향이 같아 공정하다.
사용: python3 tools/video/pick_best.py <음성 폴더>"""
import json, os, re, subprocess, sys
from collections import defaultdict

d = sys.argv[1]
asr = json.load(open(os.path.join(d, "받아쓰기.json"), encoding="utf-8"))
rec = json.load(open(os.path.join(d, "기록.json"), encoding="utf-8"))
by = defaultdict(list)
for it in asr["items"]:
    m = re.match(r"(.+)_속도([0-9.]+)_take(\d+)\.mp3$", it["file"])
    if m:
        by[(m.group(1), m.group(2))].append((it["같은 글자 비율"], -int(m.group(3)), it))


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                                capture_output=True, text=True).stdout.strip() or 0)


chosen, items, cand = [], [], {}
for (name, sp), lst in sorted(by.items()):
    lst.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best = lst[0][2]
    final = f"{name}_속도{sp}.mp3"
    os.replace(os.path.join(d, best["file"]), os.path.join(d, final))
    for _, _, it in lst[1:]:
        os.remove(os.path.join(d, it["file"]))
    cand[final] = {it["file"]: r for r, _, it in lst}
    best = dict(best, file=final, 고른_후보=lst[0][2]["file"])
    items.append(best)
    chosen.append(os.path.join(d, final))
asr["items"] = items
asr["고르기"] = "장면마다 3번 만든 것 가운데 받아쓰기 같은 글자 비율이 가장 높은 것(같으면 앞 번호)"
asr["후보별_비율"] = cand
json.dump(asr, open(os.path.join(d, "받아쓰기.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

gap = os.path.join(d, "_gap.wav")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "0.8", "-c:a", "pcm_s16le", gap], check=True)
parts = []
for c in chosen:
    parts += [c, gap]
parts = parts[:-1]
args = ["ffmpeg", "-y", "-loglevel", "error"]
for x in parts:
    args += ["-i", x]
filt = "".join(f"[{i}:a]aresample=44100,aformat=channel_layouts=mono[a{i}];" for i in range(len(parts)))
filt += "".join(f"[a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[a]"
args += ["-filter_complex", filt, "-map", "[a]", "-codec:a", "libmp3lame", "-q:a", "4", os.path.join(d, "전체_이어듣기.mp3")]
subprocess.run(args, check=True)
os.remove(gap)
secs = [{"file": os.path.basename(c), "seconds": round(dur(c), 1)} for c in chosen]
rec = {"engine": rec.get("engine"), "고르기": asr["고르기"], "items": secs,
       "합계_초": round(sum(x["seconds"] for x in secs), 1), "전체_이어듣기_초": round(dur(os.path.join(d, "전체_이어듣기.mp3")), 1)}
json.dump(rec, open(os.path.join(d, "기록.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(rec, ensure_ascii=False))
