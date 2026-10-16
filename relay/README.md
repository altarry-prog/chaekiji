# relay/ — 정보나루 중계 (시연 웹이 인증키 없이 실데이터를 쓰기 위한 얇은 층)

시연 웹(깃허브 페이지스)은 정적 페이지라 비밀값을 가질 수 없다. 그래서 **키를 가진 작은 중계**를 하나 두고, 시연 웹은 중계에만 묻는다.
설계와 원칙은 [server/docs/정보나루-중계-설계.md](../server/docs/정보나루-중계-설계.md).

    시연 웹(index.html) ──/holdings?isbn=…──▶ 중계(키 보관) ──▶ 정보나루 Open API
    참조 서버(server/, relay 모드) ──/search·/holdings·/nation──▶ 중계 ──▶ 정보나루     [v0.3.4]
    중계가 없거나 답이 없으면 → 둘 다 2026. 8. 18. 실측 픽스처로 자동 복귀(화면·안내문에 그대로 표시)

중계 없이도 되는 길이 하나 더 있다 — **매일 갱신**(`server/lab/refresh_today.py` + 깃허브 액션 `refresh.yml`): 정해 둔 도서의 조회분을 새벽마다 받아 `data/holdings-today.json`으로 커밋하면, 시연 웹과 서버(auto 모드)가 그 파일을 읽는다. 대출 상태는 어차피 전일 기준이라 하루 한 번이면 신선도가 같다. 중계는 **목록에 없는 책**(상담 비서의 임의 문의)을 위한 것.

| 파일 | 어디서 돌리나 | 비용 |
|---|---|---|
| `worker.js` | **Cloudflare Workers**(무료) — 깃허브 액션 `deploy-relay.yml`이 올린다(아래). 브라우저 화면에서 붙여 넣고 비밀값 NARU_KEY를 넣어도 된다. 심사 기간 24시간 가동 | 0원 |
| `relay.py` | 도서관 PC·실험실 VM — 파이썬만 있으면 됨(의존성 없음). 개발·검증용 | 0원 |

둘 다 같은 경로·같은 응답(날짜는 `YYYY-MM-DD`):

- `GET /holdings?isbn=9788972756194` → `{"isbn","asof":"2026-10-15","libs":{"141321":"busy",…16관},"calls":9,"cached":false}`
- `GET /search?q=채식주의자` → `{"docs":[{"isbn13","title","author","publisher","year"},…최대 5건],"asof"}` (제목 부분일치) · `GET /search?isbn=…` → 서지 1건
- `GET /nation?isbn=9788972756194` → `{"found_count":12,"asof"}` (경기 광역 소장관 수 — 전국 예시)
- `GET /health` → `{"ok":true,"keyed":true}` (키 **값**은 어디에도 내보내지 않음)

**깃허브가 대신 올리기(10/16~)** — 행정망에서 Cloudflare 화면이 막혀 있어, 배포를 깃허브 액션 `.github/workflows/deploy-relay.yml`에 맡겼다. 저장소 비밀값 `CLOUDFLARE_API_TOKEN`(Cloudflare 「Edit Cloudflare Workers」 템플릿 토큰)·`CLOUDFLARE_ACCOUNT_ID`가 있으면 `worker.js`·`wrangler.toml`이 바뀔 때마다 배포하고, 이미 있는 정보나루 키(`NARU_KEY`/`NARUKEY`)를 Cloudflare 비밀값으로 넘긴 뒤 `/health`·`/holdings` 1건을 확인해 `relay/last_deploy.json`(주소·결과·실패 까닭, 키·토큰 없음)에 남긴다.

점검: `node relay/test_worker.mjs` — 정보나루를 흉내 낸 fetch로 네 경로·거절 규칙·https→http 넘어가기 15건(네트워크·키 불필요).

## 지키는 것 (설계 원칙 그대로)

1. 인증키는 환경변수(`NARU_KEY`)에만 — 코드·저장소·응답·로그·오류 문구 어디에도 없음. 키가 없으면 기동 거부(503).
2. 허용 출처만 응답 — `https://altarry-prog.github.io` (+ 로컬 점검 주소). 다른 출처는 403.
3. 경로 화이트리스트 — `/holdings` `/search` `/nation` `/health` 넷뿐. 나머지 404.
4. 호출 상한 — IP당 10분에 60회(429, 상담 1건 = 2~3회). 같은 조회는 10분 캐시. 브라우저가 아닌 호출(서버 relay 모드)은 Origin이 없어 통과하므로 상한이 남용 방어선이다.
5. 최소 가공 — 16관의 `ok|busy|none`과 조회일만 내려보냄. 「대출 상태는 조회일 전일 기준」 문구 포함.

## 참조 서버 쪽 연결 (상담 비서)

`server/config/bucheon.yaml`의 `relay_url`(또는 환경변수 `CHAEKIJI_RELAY`)에 중계 주소를 넣고 `CHAEKIJI_MODE=auto`(심사 기본값)로 띄우면, 중계가 살아 있을 때 키 없이 오늘 데이터로 판정한다. 시험: `python server/tests/run_relay.py`(모의 중계).

## 시연 웹 쪽 연결

`index.html` 맨 위 상수 `RELAY`에 중계 주소를 넣으면 켜진다(빈 문자열이면 지금처럼 픽스처만).

    const RELAY = "https://chaekiji-relay.<계정>.workers.dev";

실데이터로 답하면 결과 화면 출처 줄이 「정보나루 실데이터 · **오늘 날짜** 조회」로 바뀌고, 중계가 답하지 않으면 「2026. 8. 18. 조회」 그대로다 — 어느 쪽인지 화면에 늘 보인다.

## 점검 항목 (설계 문서의 4개)

| # | 항목 | 확인 방법 |
|---|---|---|
| 1 | 허용 출처 밖 요청 거절 | 브라우저 주소창으로 직접 열면(Origin 없음) 허용, 다른 사이트의 스크립트에서 부르면 403 |
| 2 | 화이트리스트 밖 경로 거절 | `/anything` → 404 |
| 3 | 키 미설정 시 기동 거부 | 환경변수 없이 실행 → `relay.py`는 종료, `worker.js`는 503 |
| 4 | 응답에 키 흔적 없음 | `/health`·`/holdings` 응답 본문에 `authKey` 문자열 없음 |
