# tools: 측정 도구(재현용)

`server/lab/out/`에 있는 여러 모델·다른 도시 측정 기록을 만든 도구입니다. 처음에는 제출 산출물과 섞이지 않게 가지 `tools/model2`에서 깃허브 액션으로 돌렸고, 2026. 11. 2. 같은 방법으로 다시 돌려 볼 수 있도록 main에 그대로 옮겼습니다(코드 내용은 같음). 각 기록 파일 머리에 실행 기록(깃허브 액션) 주소와 커밋이 있습니다.

| 폴더 | 무엇을 쟀나 | 기록(`server/lab/out/`) |
|---|---|---|
| `model2/` | 코랩 노트북을 깃허브 액션에서 그대로 실행(엑사원·라마, `run_notebook.py`), GPT-OSS 구동(`run_gptoss.py`), AI가 맡는 일 반복(`run_ai_role.py`), AI가 맡는 일 지표(문의 24건 × 지시문 2종 × 3회, `run_ai_metrics.py`·`report_ai_metrics.py`) | `model2_record_actions_*`, `model_gptoss_record_actions_*`, `ai_role_record_actions_*`, `ai_metrics_record_actions_*` |
| `solar/` | Solar Pro 4(업스테이지 API)로 같은 지표. 공개 모델 호스트(`server/hosts/ollama_host.py`)에 업스테이지 API를 잇는 작은 연결 프로그램(`upstage_ollama_proxy.py`) | `ai_metrics_solar_record_actions_*` |
| `city/` | 코드는 그대로 두고 설정 파일만 바꿔 시흥·광명 도서관 기준으로 신청이 되는지 확인(`run_city.py`, 워크플로 `city-measure.yml`) | `city_record_actions_*`, `city_<도시>_config_*.yaml` |
| `workflows/run-scripts.yml` | PC 설치판 실행 스크립트: 깃허브 액션의 새 가상 PC에서 main의 `server/run.bat`(윈도우)·`server/run.sh`(맥)를 고치지 않고 실행하고 기록표를 만듦(따로 도구 파일 없이 워크플로만) | `run_scripts_record_actions_*` |
| `workflows/` | 위 도구를 돌린 깃허브 액션 워크플로의 사본(`model2.yml`·`model-gptoss.yml`·`ai-role.yml`·`ai-metrics.yml`·`model-solar.yml`·`city-measure.yml`·`run-scripts.yml`, 여기서는 돌지 않음) | - |

- **다시 돌리기**: `workflows/`의 파일을 `.github/workflows/`로 옮기거나 가지 `tools/model2`에서 수동 실행합니다. 이 사본들은 결과를 커밋·푸시하고 일부는 푸시할 때 저절로 도는 설정이라, main의 `.github/workflows/`에는 두지 않았습니다.
- **키**: 정보나루 인증키(`NARU_KEY`)와 업스테이지 키(`UPSTAGE_API_KEY`)는 저장소 비밀값으로만 받고 기록·로그에 남기지 않습니다. AI가 맡는 일 지표는 서버를 snapshot 모드로 돌려 정보나루를 부르지 않습니다.
- **더 쓰지 않는 것**: 깃허브 모델(GitHub Models)용 GPT 실행 도구는 그 서비스가 2026. 7. 30. 끝나 옮기지 않았습니다(시도와 실패 기록은 가지 `tools/model2`에 그대로 있음).
