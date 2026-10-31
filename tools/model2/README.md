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

### 결과: 깃허브 모델로는 잴 수 없음(2026. 10. 30.)

- 깃허브 모델(GitHub Models)은 **2026. 7. 30. 완전히 종료**되었다(GitHub 변경 기록 「GitHub Models is now retired」). 이 가지에서 네 번 돌린 결과(`model_gpt_record_actions_2026-10-30_1620`~`_1630`)는 모두 0/5이며, 서비스 주소가 어떤 요청에도 200 「OK」만 돌려준 연결 실패 기록이다(`gpt_probe_actions_41020774870.txt`). 실패도 기록이라 지우지 않는다.
- 그래서 GPT 계열은 아래 GPT-OSS(공개 모델)로 잰다. `gpt_host.py`·`run_gpt.py`·워크플로 `model-gpt`는 더 쓰지 않는다.

## GPT-OSS(오픈AI의 공개 모델) — 2026. 10. 30. 추가

- **무엇** — `gpt-oss:20b`(받는 크기 약 14GB)를 깃허브 액션 서버(CPU)의 Ollama로 돌려 같은 문의 5건을 처리한다(`run_gptoss.py`, 워크플로 `model-gptoss`). 호스트는 엑사원·라마 실측과 같은 main의 `server/hosts/ollama_host.py` 그대로다.
- **왜** — 결제 없이 GPT 계열을 잴 길이 공개 모델뿐이고, GPT-OSS는 행정안전부 AI 공통기반 목록(참가 안내서 10. 21. 변경판)에 있다.
- **주의** — 그래픽카드가 없는 서버(메모리 16GB)라 느리고, 메모리가 모자라면 실패할 수 있다. 실패도 그대로 기록한다.
- **결과** — 이 가지의 `server/lab/out/model_gptoss_record_actions_….md`와 원 기록(`gptoss_host_log_actions_…`·`gptoss_host_answers_actions_…`).

## AI가 맡는 몫 반복 실측 — 2026. 10. 31. 추가

- **무엇** — 제목 없이 한 말·맞춤법 틀린 말·외국어(베트남어 2·중국어·영어·일본어)·모호한 말 10건을 GPT-OSS(`gpt-oss:20b`)로 두 번씩 돌린다(`run_ai_role.py`, 워크플로 `ai-role`). 호스트·서버·지시문은 위 실측과 같다.
- **채점(기계)** — 도구를 불렀나, 모델이 넘긴 말로 도구가 찾은 책이 기대한 책인가(같은 인자로 도구를 다시 불러 ISBN 확인), 판정 갈래가 기준과 같은가, 답에 조회일·누리집 주소가 그대로 있나, 답이 이용자 언어인가(글자 종류 판정, 원어민 확인 전), 모호한 말에 되물었나.
- **왜** — 10. 30. 클로드로 잰 「AI가 하는 몫」은 장면 2건 한 번씩이라 「늘 이렇게 된다」의 근거가 아니었다(담당자 10. 31. 요청).
- **결과** — 이 가지의 `server/lab/out/ai_role_record_actions_….md`와 원 기록(`ai_role_calls_actions_…`·`ai_role_answers_actions_…`).

## 다른 도시 실측(시흥·광명) — 2026. 10. 31. 추가

- **무엇** — 책이지 코드는 그대로 두고 설정 파일만 바꿔, 시흥·광명 공공도서관의 소장·대출(정보나루 live, 전일 기준)로 책 5권을 판정한다(`tools/city/run_city.py`, 워크플로 `city-measure`).
- **설정** — main의 `lab/make_city_config.py`로 도서관 코드표를 받고 이름만 줄인다. 규정 값은 확인한 것만 덮어쓰고 나머지는 【확인】(부천 값 자리표시)으로 둔다.
- **인증키** — 저장소 비밀값 `NARU_KEY`로만 받는다(기록·로그에 없음).
- **결과** — 이 가지의 `server/lab/out/city_record_actions_….md`, 도시별 설정 `city_<도시>_config_….yaml`, 원 자료 `city_raw_actions_….json`.
