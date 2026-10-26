# lab/ — AI 정부 실험실 4주 과제용 스크립트와 기록

AI 정부 실험실 가상서버(우분투)용으로 만든 것들. 가상서버는 접속이 되지 않아 쓰지 못했고, 이 스크립트들은 깃허브 액션 등 다른 우분투 환경에서 돌린다. 전부 파이썬 표준 라이브러리 + PyYAML만 쓴다.
**인증키는 환경변수로만**: `read -s NARU_KEY; export NARU_KEY` (화면·파일·기록에 남지 않음).

| 주차 | 파일 | 하는 일 | 정보나루 호출 |
|---|---|---|---|
| 1 | `naru_probe.py` | 첫 실호출 — 키 확인, `exactMatch` 값 비교, bookExist·libSrchByBook 모양 확인 | 5회 |
| 2 | `make_titles.py` | 인기대출도서로 측정용 목록(`out/titles.csv`) 생성 | 1~2회 |
| 2 | `measure.py` | 도서 1종당 호출 수·소요 시간 실측, 요약표, 실측 A 기록지 표본 생성 (`--demo`로 연습) | 도서당 2~18회 |
| 3 | `make_city_config.py` | 다른 도시 도서관 코드표로 `config/<도시>.yaml` 초안 | 1회 |
| 3 | `check_store.py` | 저장 계층·감사 기록·관내 출처 전환 점검 시험 14건(네트워크 없음) | 0 |
| — | `refresh_today.py` · `refresh_list.txt` | [v0.3.4] 매일 1회 조회분 갱신 — 픽스처 5종 + 목록의 ISBN, `--max-calls` 상한, `--demo` 연습 | 권당 1+소장관 수 |
| — | `stability.py` | 전일 기준 자료의 하루 사이 유지율 — 매일 새벽 자료(`data/holdings-today.json`)의 깃 이력을 이어지는 두 날씩 견줌, `--write`면 `out/`에 기록표 | 0 |
| — | `기록지/` | 실측 B·C·D·E 기록지, 자가점검 G | — |
| — | `codex_config.example.toml` · `vscode_mcp.example.json` · `gitlab-ci.example.yml` | AI 도구·CI 연결 예시 | — |

결과는 `lab/out/`에 쌓인다. 측정 CSV·요약(md)은 저장소에 올린다(개인정보 없음). SQLite·JSONL 상태 파일은 `.gitignore`.

## 서버 실행 방식(환경변수)

| 변수 | 값 | 뜻 |
|---|---|---|
| `CHAEKIJI_MODE` | `demo`(기본) / `snapshot` / `relay` / `live` / `auto` | 8/18 픽스처 / 매일 갱신 조회분 / 중계(키 없이 오늘) / 실호출 / 중계→스냅샷→픽스처 자동 |
| `CHAEKIJI_RELAY` | 중계 주소 | 비우면 설정 `relay_url` |
| `CHAEKIJI_SNAPSHOT` | 파일 경로 | 매일 갱신 조회분(기본 `fixtures/holdings-today.json`, 2일 넘으면 무시) |
| `CHAEKIJI_LOCAL_SOURCE` | `alpas`(기본) / `naru` | 관내 소장·대출 출처 — 도서관리시스템 모의(실시간) / 정보나루(전일 기준) |
| `CHAEKIJI_CONFIG` | `config/bucheon.yaml`(기본) | 도시 설정 |
| `CHAEKIJI_STORE` | 파일 경로 | 신청·위임 이력 SQLite 저장(없으면 메모리) |
| `CHAEKIJI_AUDIT` | 파일 경로 | 감사 기록 JSONL(없으면 안 씀) |
| `NARU_KEY` / `NARU_EXACT` | 인증키 / `true`·`Y` | live 모드 인증키 / srchBooks exactMatch 값 |

예 — 실제 정보나루로 관내까지 조회하고 이력·감사를 남기는 서버:
```
CHAEKIJI_MODE=live CHAEKIJI_LOCAL_SOURCE=naru \
CHAEKIJI_STORE=~/chaekiji-state.sqlite3 CHAEKIJI_AUDIT=~/chaekiji-audit.jsonl python3 server.py
```

## 다른 AI 도구에 연결하기 (MCP 표준이라 도구를 가리지 않는다)
- 클로드 데스크톱: `claude_desktop_config.example.json`
- Codex CLI: `lab/codex_config.example.toml` → `~/.codex/config.toml`
- VS Code(Copilot 등): `lab/vscode_mcp.example.json` → `.vscode/mcp.json`
- 정보나루 공식 MCP(biglib)를 나란히 연결하면 「조회는 국가, 판정·실행은 책이지」 구조가 그대로 보인다(시험 E).
