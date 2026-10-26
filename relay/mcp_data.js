// 자동 생성 파일 — 손으로 고치지 말 것. relay/build_mcp_data.py가 server/의 원본으로 만든다.
// 원본: server/config/bucheon.yaml · server/fixtures/catalog.json · server/fixtures/holdings.json ·
//       server/prompts/상담비서-지시문.md · server/server.py(TOOLS·PROMPTS)
export const SERVER_VERSION = "0.3.5";
export const CFG = {
 "city": "부천",
 "region_code": "31050",
 "home_library": "상동",
 "libraries": {
  "꿈빛": "141065",
  "꿈여울": "141248",
  "도당": "141583",
  "동화": "141315",
  "별빛마루": "141652",
  "북부": "141056",
  "상동": "141321",
  "송내": "141559",
  "수주": "141651",
  "심곡": "141043",
  "역곡": "141603",
  "역곡밝은": "141660",
  "오정": "141584",
  "원미": "141535",
  "책마루": "141115",
  "한울빛": "141151"
 },
 "rules": {
  "ill_limit": 5,
  "total_limit": 20,
  "per_lib_limit": 5,
  "block_if_pickup_on_shelf": true,
  "block_if_overdue": true,
  "excluded_types": [
   "부록"
  ],
  "exclude_new_arrival": false
 },
 "ill_eta_days": "1",
 "hold_days": 3,
 "official_search_url": "https://alpasq.bcl.go.kr/search/keyword/{isbn13}",
 "ill_eta_text": "월~목요일 신청은 다음 날, 금·토요일 신청은 월·화요일에",
 "hold_includes_arrival_day": true,
 "no_pickup_block_days": 7,
 "reserve_converts_to_ill": true,
 "official_search_url_title": "https://alpasq.bcl.go.kr/search/keyword/{title}",
 "pickup_points": [
  "상동역 칙칙폭폭",
  "숲속",
  "꿈꾸는새싹",
  "약대신나는가족",
  "시정담벼락",
  "신중동역 칙칙폭폭",
  "소사칙칙폭폭",
  "해밀"
 ]
};
export const CATALOG = [
 {
  "isbn13": "9788936434120",
  "title": "소년이 온다",
  "author": "한강",
  "publisher": "창비",
  "year": "2014",
  "keys": [
   "소년이 온다",
   "소년이온다",
   "소년",
   "한강 소년",
   "humanacts"
  ],
  "type": "일반",
  "new_arrival": false
 },
 {
  "isbn13": "9788972756194",
  "title": "나미야 잡화점의 기적",
  "author": "히가시노 게이고",
  "publisher": "현대문학",
  "year": "2012",
  "keys": [
   "나미야",
   "잡화점",
   "나미야 잡화점",
   "기적 나오는",
   "namiya"
  ],
  "type": "일반",
  "new_arrival": false
 },
 {
  "isbn13": "9791161571188",
  "title": "불편한 편의점",
  "author": "김호연",
  "publisher": "나무옆의자",
  "year": "2021",
  "keys": [
   "불편한 편의점",
   "불편한편의점",
   "편의점"
  ],
  "type": "일반",
  "new_arrival": false
 },
 {
  "isbn13": "9791195794799",
  "title": "설민석의 한국사 대모험",
  "author": "설민석·스토리박스",
  "publisher": "휴먼큐브",
  "year": "2017",
  "keys": [
   "설민석",
   "한국사 대모험",
   "설민석 한국사"
  ],
  "type": "일반",
  "new_arrival": false
 },
 {
  "isbn13": "9791191824001",
  "title": "지구 끝의 온실",
  "author": "김초엽",
  "publisher": "자이언트북스",
  "year": "2021",
  "keys": [
   "지구 끝의 온실",
   "지구끝의온실",
   "김초엽 온실",
   "온실"
  ],
  "type": "일반",
  "new_arrival": false
 },
 {
  "isbn13": "9790000000012",
  "title": "신착 도서(예시·모의)",
  "author": "예시",
  "publisher": "예시",
  "year": "2026",
  "type": "일반",
  "new_arrival": true,
  "keys": [
   "신착 예시 도서"
  ]
 },
 {
  "isbn13": "9790000000029",
  "title": "DVD 자료(예시·모의)",
  "author": "예시",
  "publisher": "예시",
  "year": "2024",
  "type": "DVD",
  "new_arrival": false,
  "keys": [
   "디브이디 예시"
  ]
 }
];
export const HOLD = {
 "_examples": [
  "9791191824001"
 ],
 "holdings": {
  "9788936434120": {
   "꿈빛": "ok",
   "꿈여울": "ok",
   "도당": "ok",
   "동화": "busy",
   "별빛마루": "busy",
   "북부": "busy",
   "상동": "ok",
   "송내": "ok",
   "수주": "ok",
   "심곡": "ok",
   "역곡": "busy",
   "역곡밝은": "busy",
   "오정": "ok",
   "원미": "ok",
   "책마루": "ok",
   "한울빛": "ok"
  },
  "9788972756194": {
   "꿈빛": "ok",
   "꿈여울": "ok",
   "도당": "ok",
   "동화": "none",
   "별빛마루": "busy",
   "북부": "busy",
   "상동": "busy",
   "송내": "ok",
   "수주": "busy",
   "심곡": "ok",
   "역곡": "busy",
   "역곡밝은": "none",
   "오정": "ok",
   "원미": "ok",
   "책마루": "none",
   "한울빛": "ok"
  },
  "9791161571188": {
   "꿈빛": "ok",
   "꿈여울": "busy",
   "도당": "ok",
   "동화": "ok",
   "별빛마루": "ok",
   "북부": "busy",
   "상동": "busy",
   "송내": "ok",
   "수주": "ok",
   "심곡": "ok",
   "역곡": "none",
   "역곡밝은": "none",
   "오정": "none",
   "원미": "none",
   "책마루": "none",
   "한울빛": "none"
  },
  "9791195794799": {
   "꿈빛": "ok",
   "꿈여울": "ok",
   "도당": "ok",
   "동화": "busy",
   "별빛마루": "busy",
   "북부": "ok",
   "상동": "ok",
   "송내": "busy",
   "수주": "none",
   "심곡": "busy",
   "역곡": "none",
   "역곡밝은": "none",
   "오정": "ok",
   "원미": "ok",
   "책마루": "ok",
   "한울빛": "ok"
  },
  "9791191824001": {
   "꿈빛": "none",
   "꿈여울": "none",
   "도당": "none",
   "동화": "none",
   "별빛마루": "none",
   "북부": "none",
   "상동": "none",
   "송내": "none",
   "수주": "none",
   "심곡": "none",
   "역곡": "none",
   "역곡밝은": "none",
   "오정": "none",
   "원미": "none",
   "책마루": "none",
   "한울빛": "none"
  }
 },
 "nation": {
  "9791191824001": {
   "count": 6,
   "note": "전국 참여도서관 소장(예시 데이터)"
  }
 }
};
export const PROMPT_BODY = "당신은 부천시립도서관의 창구·전화 상담을 돕는 「책이지 상담 비서」입니다. 사서가 이용자의 말을 그대로 전해 주면, 책이지 도구로 사실을 확인한 뒤 사서가 이용자에게 그대로 읽어 줄 안내문을 만듭니다. 받을 도서관은 「{pickup}」, 이용자 언어는 「{lang}」입니다.\n\n지켜야 할 것\n\n1. 사실은 도구로만 확인합니다. 책 제목, 어느 도서관에 있는지, 대출 가능 여부, 상호대차 규정은 추측하지 않습니다.\n2. 기본 순서는 `consult_request(utterance, pickup, lang)` 한 번입니다. 이 도구가 찾기, 관내 소장·대출 확인, 규정 판정, 안내문 초안, 접수 메모를 한꺼번에 돌려줍니다. 발화를 넘길 때는 가능하면 책 제목 부분만 넘깁니다(예: 「나미야 잡화점의 기적 빌리고 싶어요」 → `utterance`에 「나미야 잡화점의 기적」).\n3. 책을 찾지 못했다고 오면(`route: unknown`) 저자·출판사·대략의 내용을 이용자에게 되물어 달라고 사서에게 알리고, 새 정보로 다시 부릅니다. 후보가 여럿이면(`candidates`) 가장 앞의 것으로 안내하되 판본이 여럿임을 한 줄 덧붙입니다. 정보나루에 연결되지 않았거나 소장·대출 상태를 확인하지 못했다고 오면(`route: check`) 되묻거나 있다·없다를 짐작하지 말고, 창구 조회와 누리집 링크를 안내합니다.\n4. 개인정보를 넣지 않습니다. 이용자 이름·회원번호·전화번호·주소는 도구 인자에도, 답변에도 쓰지 않습니다. 회원 한도·연체·중복 여부는 사서가 창구 시스템에서 확인합니다(`pending` 항목).\n5. 접수는 사서가 합니다. 이 모드에서는 `request_service`·`cancel_request`·`manage_mandate`·`notify_user`를 부르지 않습니다. 답 끝에 `desk_memo`를 그대로 붙여 사서가 옮겨 적게 합니다.\n6. 대출 가능 여부는 정보나루 조회일의 전일 기준입니다. 도구가 준 날짜(`asof`)와 공식 누리집 링크 주소(`official_link`)를 안내문에 글자 그대로 둡니다. 날짜·주소를 바꾸거나 지우지 않습니다. 링크는 그 책의 누리집 화면까지이며 접수는 이용자가 로그인해 직접 합니다.\n7. 이용자 언어가 한국어가 아니면(`translate_to`) 안내문을 그 언어로 옮기고, 한국어 원문을 바로 아래 함께 둡니다. 짧은 문장, 쉬운 말.\n8. 답의 모양은 세 덩어리뿐입니다. ① 판정 한 줄(갈래: 바로 이용 / 관내 상호대차 / 예약 권장 / 책바다 안내 / 소장 확인 불가 / 미확정) ② 이용자 안내문 ③ 접수 메모. 그 밖의 설명·인사·사과는 붙이지 않습니다.\n";
export const TOOLS = [
 {
  "name": "consult_request",
  "description": "[v0.3.4 상담 묶음] 창구·전화 상담용. 이용자의 말(가능하면 책 제목)과 받을 도서관을 주면 도서 특정 → 관내 소장·대출 상태 → 상호대차 가능 여부·갈래(바로 이용/관내 상호대차/예약/책바다/소장 확인 불가) 판정 → 이용자 안내문 → 접수 메모까지 한 번에 돌려준다. 접수는 하지 않는다. 회원 토큰(user)이 있으면 규정 7종 전부, 없으면 비치·제외자료 규정만 판정하고 한도·연체·중복은 창구 확인으로 보류. [원격 판] 회원 토큰을 받지 않는다(개인정보를 받지 않음) — 한도·연체·중복은 늘 창구 확인으로 보류.",
  "inputSchema": {
   "type": "object",
   "properties": {
    "utterance": {
     "type": "string",
     "description": "이용자의 말 또는 책 제목"
    },
    "pickup": {
     "type": "string",
     "description": "받을 도서관 이름(기본: 설정의 home_library)"
    },
    "lang": {
     "type": "string",
     "description": "이용자 언어 코드(기본 ko). ko가 아니면 translate_to로 돌려줌"
    }
   },
   "required": [
    "utterance"
   ]
  }
 },
 {
  "name": "search_item",
  "description": "일상어 발화에서 도서를 식별해 ISBN 단위로 확정한다(근거 포함). [원격 판] 시연 도서 5종은 실측 서지, 그 밖의 책은 정보나루 전국 서지 검색(제목 부분일치).",
  "inputSchema": {
   "type": "object",
   "properties": {
    "utterance": {
     "type": "string"
    },
    "lang": {
     "type": "string"
    }
   },
   "required": [
    "utterance"
   ]
  }
 },
 {
  "name": "check_availability",
  "description": "관내 실시간 재고를 확인하고, 관내에 없으면 전국(정보나루·전일 기준)을 본다. [원격 판] 오늘 새벽 매일 갱신 자료에 있으면 그 자료, 없으면 정보나루를 그 자리에서 조회(전일 기준).",
  "inputSchema": {
   "type": "object",
   "properties": {
    "isbn13": {
     "type": "string"
    },
    "realtime": {
     "type": "boolean"
    }
   },
   "required": [
    "isbn13"
   ]
  }
 }
];
export const PROMPTS = [
 {
  "name": "consult",
  "description": "상담 비서 — 창구·전화 문의를 받아 책을 찾고 소장·대출 상태와 상호대차 가능 여부를 판정해 사서가 읽어 줄 안내문을 만든다(접수는 사서가).",
  "arguments": [
   {
    "name": "pickup",
    "description": "받을 도서관(기본 상동)",
    "required": false
   },
   {
    "name": "lang",
    "description": "이용자 언어 코드(기본 ko)",
    "required": false
   }
  ]
 }
];
