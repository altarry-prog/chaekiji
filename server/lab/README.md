# lab/ — AI 정부 실험실 4주 과제용 스크립트와 기록

실험실 VM(우분투)에서 돌리는 것들. 전부 파이썬 표준 라이브러리 + PyYAML만 쓴다.
**인증키는 환경변수로만**: `read -s NARU_KEY; export NARU_KEY` (화면·파일·기록에 남지 않음).

| 주차 | 파일 | 하는 일 | 정보나루 호출 |
|---|---|---|---|
| 1 | `naru_probe.py` | 첫 실호출 — 키 확인, `exactMatch` 값 비교, bookExist·libSrchByBook 모양 확인 | 5회 |
| 2 | `make_titles.py` | 인기대출도서로 측정용 목록(`out/titles.csv`) 생성 | 1~2회 |
| 2 | `measure.py` | 도서 1종당 호출 수·소요 시간 실측, 요약표, 실측 A 기록지 표본 생성 (`--demo`로 연습) | 도서당 2~18회 |
| 3 | `make_city_config.py` | 다른 도시 도서관 코드표로 `config/<도시>.yaml` 초안 | 1회 |
| 3 | `check_store.py` | 저장 계층·감사 기록·관내 출처 전환 점검 시험 14건(네트워크 없음) | 0 |
| — | `기록지/` | 실측 B·C·D·E 기록지, 자가점검 G | — |
| — | `codex_config.example.toml` · `vscode_mcp.example.json` · `gitlab-ci.example.yml` | AI 도구·CI 연결 예시 | — |

결과는 `lab/out/`에 쌓인다. 측정 CSV·요약(md)은 저장소에 올린다(개인정보 없음). SQLite·JSONL 상태 파일은 `.gitignore`.

## 서버 실행 방식(환경변수)

| 변수 | 값 | 뜻 |
|---|---|---|
| `CHAEKIJI_MODE` | `demo`(기본) / `live` | 정보나루 픽스처 / 실호출 |
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
