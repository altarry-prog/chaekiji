# Solar Pro 4 측정 도구

업스테이지 Solar Pro 4(참가 안내서가 행정안전부 AI 공통기반 지원(예정) 모델로 든 솔라 계열)로 「AI가 맡는 몫 지표」를 돌립니다. 공개 모델 지표(`tools/model2/run_ai_metrics.py`, 문의 24건 × 지시문 2종 × 3회)와 같은 실행 도구·채점·호스트(`server/hosts/ollama_host.py`)를 쓰고, 모델 자리에만 작은 연결 프로그램을 붙입니다.

- `upstage_ollama_proxy.py`: 127.0.0.1:11434에서 Ollama 모양 요청(/api/chat)을 받아 업스테이지 API(오픈AI 모양, `solar-pro4`)로 옮겨 보내고 답을 돌려줍니다. `--check`는 연결·모델 이름·도구 호출 지원을 한 번 확인합니다.
- `report_solar.py`: 공개 모델 지표의 기록표 코드를 그대로 쓰고, 모델이 API로 돌아간다는 글만 바꿉니다. 기록 파일은 `server/lab/out/ai_metrics_solar_record_actions_*.md`.
- 워크플로: main에는 사본 `tools/workflows/model-solar.yml`만 있고 돌지 않습니다. 실측은 가지 `tools/model2`의 `.github/workflows/model-solar.yml`로 돌렸고, 그 워크플로는 11. 2.부터 수동 실행만 받습니다(지시문·회차를 고를 수 있음). 키(`UPSTAGE_API_KEY`, 깃허브 Secrets)가 없으면 확인 단계에서 멈춥니다.

정보나루: 서버를 snapshot 모드로 돌려 부르지 않습니다(호출 없음). 업스테이지로 가는 것은 지시문·이용자의 말(책 제목·도서관 이름)·도구 결과뿐이며 개인정보는 없습니다. 키 값은 출력·기록하지 않습니다.

시험(2026. 11. 2.): 가짜 오픈AI 모양 서버를 업스테이지 자리에 두고 문의 24건을 끝까지 돌려(요청 48건, 도구 호출 방식 native) 기록 파일과 기록표가 만들어지는 것을 확인했습니다. 실제 Solar 결과는 키를 넣은 뒤의 실행 기록에 있습니다.
