# AGENTS.md — AI 코딩 도구를 위한 이 저장소의 규칙

이 파일은 Codex CLI · GitHub Copilot · Claude 등 AGENTS.md를 읽는 모든 AI 코딩 도구에 적용된다.
사람이 읽어도 그대로 유효한 작업 규칙이다.

## 이 저장소는 무엇인가
부천시립도서관 상호대차 AI 에이전트 「책이지」의 **표준 도구 계층 참조 서버**(MCP, stdio JSON-RPC).
도구 11종(`server.py` TOOLS)과 규정 판정 7종(`policy.py`), 지역 고유값은 전부 `config/*.yaml`.
운영 서비스가 아니다 — 시연·검증용이며 실제 접수는 일어나지 않는다.

## 실행·시험
- 한 번에: `run.bat`(윈도우) · `sh run.sh` — 시험 104건(적합성 50 · 실험실 14 · 중계 모드 30 · 공개 모델 호스트 10)
- 적합성 시험(50건 전부 통과 유지): `python3 tests/run_scenarios.py`
- 실험실 점검 시험: `python3 lab/check_store.py`
- 중계·원격 상담 비서(저장소 루트에서): `node relay/test_worker.mjs` · `node relay/test_mcp.mjs` · `python3 relay/test_mcp_parity.py` · `python3 relay/build_mcp_data.py --check`
- 서버 수동 실행: `python3 server.py` (stdin으로 JSON-RPC 한 줄씩)
- 의존성: Python 3.9+ · PyYAML. **새 외부 패키지를 더하지 말 것**(꼭 필요하면 출처·라이선스를 prompts/에 기록하고 사람 확인).

## 절대 규칙 (AI 정부 실험실 이용수칙과 같음)
1. 인증키·비밀번호·토큰을 코드·설정 파일·기록·커밋에 쓰지 않는다. 정보나루 키는 `NARU_KEY` 환경변수로만 읽는다.
2. 운영 중인 시스템(도서관리시스템 알파스, 도서관 누리집, 통합 SSO)에 접속·자동화하는 코드를 만들지 않는다. 연동은 `connectors/alpas_stub.py`의 함수 7종 **모의**로만.
3. 개인정보를 만들거나 넣지 않는다. 회원은 `fixtures/members.json`의 가상 인물뿐. 내부망 주소·시스템 구조·화면 구성을 코드·주석·문서에 적지 않는다.
4. 정직 고지를 지운다·약화하지 않는다: 「전일 기준」(정보나루 대출 가능 여부), 「모의」(알파스·회원·추천·대체자료), 「실제 접수 없음」.
5. 기존 시험의 판정 기준을 바꾸거나 시험을 지우지 않는다(약하게 만들지 않는다). 새 시험은 더해도 되며, 더하면 시험 수를 README·CHANGELOG·CI 이름에 함께 고친다(2026. 10. 기준 적합성 50건).
   원격 상담 비서(`relay/mcp.js`)는 이 서버의 relay 모드와 같은 답을 내야 한다 — `tools.py`·`policy.py`·`connectors/naru.py`의 판정·안내문을 고치면 `relay/mcp.js`도 같이 고치고 `relay/test_mcp_parity.py`로 대조한다. 설정·픽스처·지시문을 고치면 `python3 relay/build_mcp_data.py`.
6. 지역 규정 숫자·도서관 코드를 코드에 쓰지 않는다 — `config/*.yaml`에만.
7. 파일 삭제·외부 접속·발송처럼 영향이 큰 동작은 실행 전에 사람에게 묻는다.

## 코드 규칙
- 파이썬 표준 라이브러리 우선. 주석·문서는 한국어. 함수 이름·도구 이름·JSON 키는 영어 그대로.
- 커넥터 원칙: demo(픽스처)와 live(실호출)의 **응답 모양이 같아야** 한다.
- 정보나루 호출은 `connectors/naru._get()`만 쓴다(계측·오류 처리·키 처리가 거기 있다).
- 커밋 메시지: 무엇을 왜 바꿨는지 한 줄 + (AI 생성이면) 쓴 도구 표기. 예: `naru: 관내 조회 캐시 10분 (Codex 생성, 사람 검토)`

## 기록
- AI로 만든 변경은 `prompts/YYYY-MM-DD-주제.md`에 목적·지시문 요지·검토·검증 결과를 남긴다(`prompts/README.md`).
- 실측 결과는 `lab/out/`(CSV·요약 md). 인증키·개인정보가 섞였는지 커밋 전에 확인.

## 구조 요약
```
server.py      MCP 전송·도구 노출·감사 훅       tools.py      도구 11종 구현
policy.py      규정 판정 7종(숫자 없음)          vault.py      토큰 금고(시연용 고정 토큰)
store.py       영속 저장(SQLite, 환경변수로 켬)  audit.py      감사 기록(해시 사슬 JSONL)
connectors/    naru.py(정보나루) · alpas_stub.py(도서관리시스템 모의 = 벤더 명세)
config/        도시별 설정                        fixtures/     실측·모의 데이터
tests/         적합성 50 · 중계 모드 30 · 호스트 10 lab/          실험실 스크립트·점검 시험·결과·코랩 노트북
docs/          로드맵·명세·설계                   prompts/      지시문 기록
```
