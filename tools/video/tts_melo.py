"""시연영상 음성 만들기 — narration/*.txt 한 파일을 mp3 하나로(MeloTTS 한국어, MIT).
숫자는 원고에서 한글로 풀어 쓴다(예: 「삼십이만 권」) — 숫자를 그대로 두면 잘못 읽을 수 있다.
사용: python tools/video/tts_melo.py <원고 폴더> <출력 폴더>
환경변수: SPEEDS(기본 「1.0」 — 담당자가 10. 20. 보통 속도를 고름, 예: 「1.0,1.1」) · JOIN=1이면 장면을 이름 순서로 0.8초 쉬고 이어 붙인 「전체_이어듣기.mp3」도 만든다."""
import glob, os, subprocess, sys, json, time
from melo.api import TTS

src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
model = TTS(language="KR", device="cpu")
spk = model.hps.data.spk2id["KR"]
speeds = [float(x) for x in os.environ.get("SPEEDS", "1.0").split(",") if x.strip()]
log, wavs = [], []
for path in sorted(glob.glob(os.path.join(src, "*.txt"))):
    name = os.path.splitext(os.path.basename(path))[0]
    text = open(path, encoding="utf-8").read().strip()
    for speed in speeds:
        wav = os.path.join(out, f"{name}_속도{speed}.wav")
        t0 = time.time()
        model.tts_to_file(text, spk, wav, speed=speed)
        mp3 = wav[:-4] + ".mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-codec:a", "libmp3lame", "-q:a", "4", mp3], check=True)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp3],
                                   capture_output=True, text=True).stdout.strip() or 0)
        wavs.append(wav)
        log.append({"file": os.path.basename(mp3), "speed": speed, "seconds": round(dur, 1), "chars": len(text), "made_in_s": round(time.time() - t0, 1)})
        print(mp3, dur)
joined = None
if os.environ.get("JOIN") and wavs:
    gap = os.path.join(out, "_gap.wav")
    sr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate",
                         "-of", "csv=p=0", wavs[0]], capture_output=True, text=True).stdout.strip() or "44100"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"anullsrc=r={sr}:cl=mono", "-t", "0.8",
                    "-c:a", "pcm_s16le", gap], check=True)
    pick = [w for w in wavs if f"_속도{speeds[0]}.wav" in w]  # 첫 속도만 이어 붙임
    parts = []
    for w in pick:
        parts += [w, gap]
    parts = parts[:-1]
    args = ["ffmpeg", "-y", "-loglevel", "error"]
    for x in parts:
        args += ["-i", x]
    args += ["-filter_complex", "".join(f"[{i}:a]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[a]",
             "-map", "[a]", "-codec:a", "libmp3lame", "-q:a", "4", os.path.join(out, "전체_이어듣기.mp3")]
    subprocess.run(args, check=True)
    os.remove(gap)
    joined = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                   os.path.join(out, "전체_이어듣기.mp3")], capture_output=True, text=True).stdout.strip() or 0)
for w in wavs:
    os.remove(w)
json.dump({"engine": "MeloTTS KR (MIT)", "items": log,
           "합계_초": round(sum(i["seconds"] for i in log if i["speed"] == speeds[0]), 1),
           "전체_이어듣기_초": round(joined, 1) if joined else None}, open(os.path.join(out, "기록.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
