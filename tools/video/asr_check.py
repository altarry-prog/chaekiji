"""시연영상 음성 받아쓰기 점검 — 만든 mp3를 음성 인식(faster-whisper medium, MIT)으로 다시 받아써 원고와 견준다.
사람이 듣기 전에 「잘못 읽은 곳」을 미리 찾으려는 것이다. 인식기도 틀릴 수 있으므로 결과는 참고용이다.
원고 쪽으로 기울지 않게 하려고 원고 낱말을 인식기에 미리 알려 주지 않는다(initial_prompt 없음).
사용: python tools/video/asr_check.py <원고 폴더> <음성 폴더>  → <음성 폴더>/받아쓰기.json"""
import difflib, glob, json, os, re, subprocess, sys, unicodedata
import numpy as np
from faster_whisper import WhisperModel

src_dir, audio_dir = sys.argv[1], sys.argv[2]
model = WhisperModel("medium", device="cpu", compute_type="int8")


def load(path):
    """mp3를 16kHz 단일 채널 소리 값으로 — ffmpeg로 푼다(faster-whisper의 PyAV 풀기는 av 19에서 metadata_errors 인자 때문에 실패함)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def norm(s):
    return re.sub(r"[^가-힣0-9A-Za-z]", "", unicodedata.normalize("NFC", s))


items = []
for mp3 in sorted(glob.glob(os.path.join(audio_dir, "*.mp3"))):
    name = os.path.basename(mp3).rsplit("_속도", 1)[0]
    src = open(os.path.join(src_dir, name + ".txt"), encoding="utf-8").read().strip()
    segs, _ = model.transcribe(load(mp3), language="ko", beam_size=5)
    segs = list(segs)
    heard = " ".join(s.text.strip() for s in segs)
    a, b = norm(src), norm(heard)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    diffs = [{"원고": a[i1:i2], "들린 말": b[j1:j2]} for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]
    items.append({
        "file": os.path.basename(mp3),
        "같은 글자 비율": round(sm.ratio(), 3),
        "받아쓴 글": heard,
        "다른 곳": diffs,
        "구간": [{"시작": round(s.start, 1), "끝": round(s.end, 1), "글": s.text.strip()} for s in segs],
    })
    print(os.path.basename(mp3), round(sm.ratio(), 3))

json.dump({"인식기": "faster-whisper 1.2.1 medium int8 (CPU), language=ko, beam 5, initial_prompt 없음, 소리 풀기는 ffmpeg",
           "주의": "숫자를 한글로 쓴 원고(예: 삼십이만)를 인식기가 숫자(32만)로 적으면 「다른 곳」에 나오지만 잘못 읽은 것이 아니다.",
           "items": items},
          open(os.path.join(audio_dir, "받아쓰기.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
