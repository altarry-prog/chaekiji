# 코랩 노트북(server/lab/colab_model2.ipynb)의 코드 칸을 코랩이 아닌 곳(깃허브 액션)에서 차례로 실행한다.
# 노트북 코드는 그대로 쓰고, 바꾸는 것은 기록에 적히는 「실행 환경」 이름·실행 기록 주소·파일 이름뿐이다.
# 바꾼 곳은 실행 로그에 모두 찍는다. 바꿀 문장을 하나라도 못 찾으면 실행하지 않고 멈춘다(노트북이 바뀌었다는 뜻).
# 사용: python3 tools/model2/run_notebook.py server/lab/colab_model2.ipynb [--check]
import json
import sys

nb_path = sys.argv[1]
check_only = "--check" in sys.argv
nb = json.load(open(nb_path, encoding="utf-8"))
code = "\n\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")

SUBS = [
    ("host_log_colab_", "host_log_actions_"),
    ("host_answers_colab_", "host_answers_actions_"),
    ("model2_record_colab_", "model2_record_actions_"),
    ("# 공개 모델 2종 구동 실측 기록 — 코랩 (", "# 공개 모델 2종 구동 실측 기록 — 깃허브 액션 ("),
    ('f"- 실행 환경: Google Colab · GPU {GPU} · Ollama {OLLAMA_VER}",',
     'f"- 실행 환경: GitHub Actions(ubuntu-latest, 사람 손 없음) · CPU {os.cpu_count()}코어 · GPU {GPU} · Ollama {OLLAMA_VER}", '
     'f"- 실행 기록(공개): {os.environ.get(\'RUN_URL\', \'—\')} — 코랩 노트북의 코드 칸을 그대로 실행(행정망 PC에서 코랩이 열리지 않아 대신 돌림)",'),
    ("이 노트북이 실제로 돌린 결과이며", "코랩 노트북의 코드 칸을 깃허브 액션 서버에서 그대로 돌린 결과이며"),
]
for old, new in SUBS:
    n = code.count(old)
    if n != 1:
        sys.exit(f"멈춤: 바꿀 문장이 {n}번 나옴(1번이어야 함) — {old[:50]}")
    code = code.replace(old, new)
    print(f"바꿈: {old[:48]} → {new[:48]}", flush=True)

compiled = compile(code, nb_path, "exec")
if check_only:
    print("확인만 함: 바꿀 문장 모두 찾음, 문법 이상 없음")
    sys.exit(0)
exec(compiled, {"__name__": "__main__"})
