# lab/: AI 정부 실험실 4주 과제용 스크립트와 기록

AI 정부 실험실 가상서버(우분투)용으로 만든 것들. 가상서버는 접속이 되지 않아 쓰지 못했고, 이 스크립트들은 깃허브 액션 등 다른 우분투 환경에서 돌린다. 전부 파이썬 표준 라이브러리 + PyYAML만 쓴다.
**인증키는 환경변수로만**: `read -s NARU_KEY; export NARU_KEY` (화면·파일·기록에 남지 않음).

| 주차 | 파일 | 하는 일 | 정보나루 호출 |
|---|---|---|---|
| 1 | `naru_probe.py` | 첫 실호출: 키 확인, `exactMatch` 값 비교, bookExist·libSrchByBook 모양 확인 | 5회 |
| 2 | `make_titles.py` | 인기대출도서로 측정용 목록(`out/titles.csv`, 실행하면 생기며 저장소에는 없음) 생성 | 1\~2회 |
| 2 | `measure.py` | 도서 1종당 호출 수·소요 시간 측정, 요약표, 측정 A 기록지 표본 생성 (`--demo`로 연습). 실측 결과(`out/measure_*`, 측정 A 기록지)는 저장소에 아직 없음 | 도서당 2\~18회 |
| 3 | `make_city_config.py` | 다른 도시 도서관 번호 목록으로 `config/<도시>.yaml` 초안 | 1회 |
| 3 | `check_store.py` | 저장 계층·감사 기록·관내 출처 전환 점검 시험 14건(네트워크 없음) | 없음 |
| - | `refresh_today.py` · `refresh_list.txt` | [v0.3.4] 매일 1회 조회분 갱신: 픽스처 5종 + 목록의 ISBN, `--max-calls` 상한, `--demo` 연습 | 권당 1+책이 있는 도서관 수 |
| - | `stability.py` | 하루 전 기준 자료의 하루 사이 유지율: 매일 새벽 자료(`data/holdings-today.json`)의 깃 이력을 이어지는 두 날씩 견줌, `--write`면 `out/`에 기록표 | 없음 |
| - | `consult_cli.py` | 상담 비서를 명령 창에서 한 번 부르기: 모델 없이 `consult_request`의 결과·안내문·접수 메모를 읽기 쉽게 보인다(`run.sh`·`run.bat`가 끝에 다음 순서로 안내) | 모드에 따름(기본 auto: 연결 서버를 거쳐 키 없이) |
| - | `measure_consult.py` | 인터넷 판 상담 도구(`/mcp`) 처리 시간 실측: 문의 15건, 깃허브 액션 `measure-consult.yml`, 기록 `out/consult_timing_*` | 매일 갱신 자료에 있는 책은 없음, 그 밖의 책은 권당 서지 1 + 1 + 책이 있는 도서관 수(연결 서버가 부름) |
| - | `refresh_examples.py` | 시연 웹 예시 단추 ①②의 장면 자료를 그날 새벽 자료로 바꿈(동결일에 한 번) | 없음 |
| - | `colab_model2.ipynb` | 코랩에서 설치 없이 공개 모델 2종(엑사원 3.5·라마 3.2)에 같은 지시문·같은 문의 5건을 처리하고 기록표를 만듦 | 모드에 따름(기본 auto: 연결 서버를 거쳐 키 없이) |
| - | `기록지/` | 사서 확인 시간 B(아직 재지 않음, 방법만 공개)·신청 단계 C(10. 27. 마침), 실기기 음성 D(기기별 점검 때 채움), 안내데스크·전화 5일 병행 E(10. 29.\~11. 3., 세기표 없음), 자가점검 G(10. 31. 마침) | - |
| - | `codex_config.example.toml` · `vscode_mcp.example.json` · `gitlab-ci.example.yml` | AI 도구·CI 연결 예시 | - |

결과는 `lab/out/`에 쌓인다. 실측 기록(json·ndjson·csv와 요약 md)은 저장소에 올린다(개인정보 없음). `--demo` 연습 결과와 SQLite·JSONL 상태 파일은 `.gitignore`로 올리지 않는다.

## 서버 실행 방식(환경변수)

| 변수 | 값 | 뜻 |
|---|---|---|
| `CHAEKIJI_MODE` | `demo`(기본) / `snapshot` / `relay` / `live` / `auto` | 8/18 픽스처 / 매일 갱신 조회분 / 연결 서버(인증키를 숨기고 정보나루에 대신 묻는 서버, 키 없이 그 자리 조회, 하루 전 기준) / 실호출 / 연결 서버→스냅샷→픽스처 자동 |
| `CHAEKIJI_RELAY` | 연결 서버 주소 | 비우면 설정 `relay_url` |
| `CHAEKIJI_SNAPSHOT` | 파일 경로 | 매일 갱신 조회분(기본 `fixtures/holdings-today.json`, 2일 넘으면 무시. 심사 기간에는 10. 30. 이후 자료를 11. 26.까지 씀) |
| `CHAEKIJI_LOCAL_SOURCE` | `alpas` / `naru` (기본: demo면 alpas, relay·live·snapshot이면 naru, auto는 고른 모드를 따름) | 관내 소장·대출 출처: 도서관리시스템 연동 모의(값은 8. 18. 픽스처) / 정보나루(하루 전 기준) |
| `CHAEKIJI_CONFIG` | `config/bucheon.yaml`(기본) | 도시 설정 |
| `CHAEKIJI_STORE` | 파일 경로 | 신청·위임 이력 SQLite 저장(없으면 메모리) |
| `CHAEKIJI_AUDIT` | 파일 경로 | 감사 기록 JSONL(없으면 안 씀) |
| `NARU_KEY` / `NARU_EXACT` | 인증키 / `true`·`Y` | live 모드 인증키 / srchBooks exactMatch 값 |

예(실제 정보나루로 관내까지 조회하고 이력·감사를 남기는 서버):
```
CHAEKIJI_MODE=live CHAEKIJI_LOCAL_SOURCE=naru \
CHAEKIJI_STORE=~/chaekiji-state.sqlite3 CHAEKIJI_AUDIT=~/chaekiji-audit.jsonl python3 server.py
```

## 다른 AI 도구에 연결하기 (MCP 표준이라 도구를 가리지 않는다)
- 클로드 데스크톱: `claude_desktop_config.example.json`
- Codex CLI: `lab/codex_config.example.toml` → `~/.codex/config.toml`
- VS Code(Copilot 등): `lab/vscode_mcp.example.json` → `.vscode/mcp.json`
- 정보나루 공식 MCP(biglib)를 나란히 연결하면 「조회는 국가, 확인·실행은 책이지」 구조가 그대로 보인다. 다만 공식 MCP는 같은 인증키·같은 사용량을 쓰므로 이번 기간에는 공식 MCP와 나란히 대조하는 시험을 하지 않았다(9. 27. 계획의 「기록지 E」. 지금의 기록지 E는 안내데스크·전화 병행).
