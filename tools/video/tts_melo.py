"""시연영상 음성 만들기 — narration/*.txt 한 파일을 mp3 하나로(MeloTTS 한국어, MIT).
숫자는 원고에서 한글로 풀어 쓴다(예: 「삼십이만 권」) — 숫자를 그대로 두면 잘못 읽을 수 있다.
사용: python tools/video/tts_melo.py <원고 폴더> <출력 폴더>"""
import glob, os, subprocess, sys, json, time
from melo.api import TTS

src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
model = TTS(language="KR", device="cpu")
spk = model.hps.data.spk2id["KR"]
log = []
for path in sorted(glob.glob(os.path.join(src, "*.txt"))):
    name = os.path.splitext(os.path.basename(path))[0]
    text = open(path, encoding="utf-8").read().strip()
    for speed in (1.0, 1.1):
        wav = os.path.join(out, f"{name}_속도{speed}.wav")
        t0 = time.time()
        model.tts_to_file(text, spk, wav, speed=speed)
        mp3 = wav[:-4] + ".mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-codec:a", "libmp3lame", "-q:a", "4", mp3], check=True)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp3],
                                   capture_output=True, text=True).stdout.strip() or 0)
        os.remove(wav)
        log.append({"file": os.path.basename(mp3), "speed": speed, "seconds": round(dur, 1), "chars": len(text), "made_in_s": round(time.time() - t0, 1)})
        print(mp3, dur)
json.dump({"engine": "MeloTTS KR (MIT)", "items": log}, open(os.path.join(out, "기록.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
