# tools/model2 — 코랩 노트북을 깃허브 액션에서 돌리는 실측 도구

이 가지(`tools/model2`)는 제출 산출물과 따로 둔 실측 도구다. main은 건드리지 않는다.

- **무엇** — `server/lab/colab_model2.ipynb`(공개 모델 2종 구동 노트북)의 코드 칸을 깃허브 액션 서버에서 차례로 실행한다. 엑사원 3.5(2.4B)·라마 3.2(3B)에 같은 서버·같은 지시문·같은 문의 5건을 넣고 기록표를 만든다.
- **왜** — 2026. 10. 18. 담당자의 행정망 PC에서 코랩이 열리지 않았다. 사람 손 없이 같은 단계를 실행하고, 실행 기록을 공개로 남긴다.
- **바꾸는 것** — 노트북 코드는 그대로다. 기록에 적히는 「실행 환경」(코랩 → 깃허브 액션), 실행 기록 주소, 파일 이름(`_colab_` → `_actions_`)만 바꾸고, 바꾼 곳은 실행 로그에 모두 찍는다(`run_notebook.py`).
- **다른 점** — 코랩은 T4 GPU, 깃허브 액션은 CPU라 시간이 더 걸린다. 판정은 도구가 정하므로 같아야 정상이고, 시간은 환경 차이를 그대로 적는다.
- **결과** — 이 가지의 `server/lab/out/model2_record_actions_….md`(기록표)와 원 기록(`host_log_actions_…`·`host_answers_actions_…`). 실행 기록은 Actions 탭의 `model2`.
- **다시 돌리기** — 이 가지의 `tools/model2/` 또는 워크플로 파일을 고쳐 올리거나, Actions 탭에서 수동 실행.

## GPT 모델(깃허브 모델) — 2026. 10. 30. 추가

- **무엇** — 같은 문의 5건을 오픈AI GPT 모델(기본 `openai/gpt-4.1-mini`·`openai/gpt-5-mini`)로 돌린다(`run_gpt.py`, 워크플로 `model-gpt`). 호스트는 main의 `server/hosts/ollama_host.py`를 그대로 쓰고, 모델을 부르는 함수 하나만 깃허브 모델 주소로 바꾼다(`gpt_host.py`).
- **왜** — ChatGPT 커넥터는 유료 요금제에서만 열린다. 결제·인증키 없이 GPT 계열에서도 같은 도구·같은 판정이 나오는지 기록한다(담당자 10. 30. 16:15 승인).
- **인증** — 깃허브 액션 기본 토큰(`GITHUB_TOKEN`)에 `models: read` 권한만 더한다. 깃허브 모델은 무료 시험용이라 분당·하루 호출 한도가 있고, 운영 경로가 아니다.
- **기준 판정** — 모델 없이 같은 도구를 같은 값으로 직접 부른 결과를 함께 적어, 모델마다 판정이 기준과 같은지 본다.
- **결과** — 이 가지의 `server/lab/out/model_gpt_record_actions_….md`와 원 기록(`gpt_host_log_actions_…`·`gpt_host_answers_actions_…`). 실행 기록은 Actions 탭의 `model-gpt`.
