# MCP 공식 점검 도구(MCP Inspector CLI)로 서버 확인: 2026-11-04 08:59 KST

- 무엇을: 모델 없이 MCP 공식 점검 도구가 책이지 서버(`server/server.py`, stdio)에 붙어 연결(initialize), 도구 목록, 정상 호출, 오류 호출을 해 본 결과
- 도구: `npx @modelcontextprotocol/inspector@0.17.2 --cli`(1판대, 2판이 따로 있음). 서버 모드 `CHAEKIJI_MODE=demo`(정보나루 호출 없음, 2026. 8. 18. 받아 둔 자료)
- 어디서: 작업 공간(리눅스, 파이썬 3.13, 노드 22). 인터넷 판(HTTP) 쪽은 이 작업 공간에서 workers.dev에 닿지 않아 하지 않음
- 11. 4. 함께 고친 것: 없는 도구를 부르면 전에는 도구 결과의 오류(isError)로 답했는데, 인터넷 판처럼 프로토콜 오류(-32602)로 답하게 바꿈

| 경우 | 점검 도구 인자 | 종료코드 | 결과 |
|---|---|---|---|
| 목록 | `--method tools/list` | 0 | 도구 11종: search_item, check_availability, check_policy, request_service, track_request, cancel_request, find_alternative, notify_user, suggest_items, manage_mandate, consult_request |
| 정상 호출: 상담 묶음(소년이 온다, 받을 곳 역곡) | `--method tools/call --tool-name consult_request --tool-arg utterance=소년이 온다 --tool-arg pickup=역곡` | 0 | isError=false · route=ill · verdict=관내 상호대차 · 안내데스크 확인: 회원 조건 |
| 필수 인자 빠짐: utterance 없음 | `--method tools/call --tool-name consult_request --tool-arg pickup=역곡` | 0 | isError=true · TypeError: consult_request() missing 1 required positional argument: 'utterance' |
| 잘못된 ISBN | `--method tools/call --tool-name check_availability --tool-arg isbn13=12345` | 0 | isError=true · ValueError: isbn13(13자리 ISBN)이 필요합니다 |
| 붙임표 ISBN | `--method tools/call --tool-name check_availability --tool-arg isbn13=978-89-364-3412-0` | 0 | isError=false · 키 city, home_library, home_status, available_at, loaned_at, basis |
| 없는 도구 | `--method tools/call --tool-name no_such_tool` | 1 | 점검 도구가 「Failed to call tool no_such_tool: MCP error -32602: unknown tool: no_such_tool」로 끝남(프로토콜 오류로 답함) |
| 지시문 목록 | `--method prompts/list` | 0 | 지시문 1개: consult |

원 기록: 이 표는 점검 도구의 출력(JSON)을 프로그램으로 줄인 것이다. 「없는 도구」 칸만 같은 명령을 한 번 더 돌려 오류 문장을 옮겨 적었다(처음 표는 종료코드만 적었음). 같은 명령으로 다시 확인할 수 있다(`server/` 폴더에서).
