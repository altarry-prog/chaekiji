# 다른 도시 실측: 시흥·광명 — 설정 파일만 바꿔 판정 (2026-10-31 21:17 KST)

- 무엇을 보았나: 책이지 코드(`server/tools.py`·`connectors/naru.py`)는 그대로 두고 **설정 파일만 바꿔** 다른 도시 공공도서관의 소장·대출로 판정이 도는지
- 실행: GitHub Actions(사람 손 없음) · 저장소 main 커밋 `d5b0fa3` · 실행 기록 https://github.com/altarry-prog/chaekiji/actions/runs/41200393975
- 자료: 정보나루 Open API 실호출(live 모드, 관내 출처 정보나루) · 대출 상태는 **조회일 전일 기준** · 인증키는 깃허브 비밀값으로만
- 설정 만들기: `lab/make_city_config.py`(정보나루 libSrch 1회) → 이름 줄이기 → 확인한 규정 값만 덮어쓰기. 나머지 규정은 부천 값을 자리표시로 둔 【확인】
- 판정은 회원 정보 없이(손님 모드) 했다. 회원 한도·연체는 창구 확인으로 남고, 어떤 판정도 접수로 이어지지 않았다

## 시흥(정보나루 세부지역 31150)

설정 초안을 만들지 못했다(실패 그대로 적음):

```
/content/cfg_시흥_raw.yaml — 도서관 11곳 (지역 전체 12곳), home_library=시흥시군자도서관
  시흥시군자도서관: 141245
  시흥시능곡도서관: 141260
  시흥시대야도서관: 141045
  시흥시매화도서관: 141396
  시흥시목감도서관: 141609
  시흥시배곧도서관: 141632
  시흥시소래빛도서관: 141316
  시흥시신천도서관: 141314
  시흥시월곶도서관: 141199
  시흥시장곡도서관: 141562
  시흥시중앙도서관: 141066
Traceback (most recent call last):
  File "/content/chaekiji/server/lab/make_city_config.py", line 73, in <module>
    main()
  File "/content/chaekiji/server/lab/make_city_config.py", line 70, in main
    f"      python3 lab/measure.py --config {out.relative_to(ROOT)} --titles lab/out/titles.csv --limit 5 --tag {a.city}")
                                             ^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.15/x64/lib/python3.12/pathlib.py", line 682, in relative_to
    raise ValueError(f"{str(self)!r} is not in the subpath of {str(other)!r}")
ValueError: '/content/cfg_시흥_raw.yaml' is not in the subpath of '/content/chaekiji/server'
```

## 광명(정보나루 세부지역 31060)

설정 초안을 만들지 못했다(실패 그대로 적음):

```
/content/cfg_광명_raw.yaml — 도서관 6곳 (지역 전체 6곳), home_library=광명시광명도서관
  광명시광명도서관: 141080
  광명시소하도서관: 141561
  광명시연서도서관: 141613
  광명시철산도서관: 141405
  광명시충현도서관: 141155
  광명시하안도서관: 141019
Traceback (most recent call last):
  File "/content/chaekiji/server/lab/make_city_config.py", line 73, in <module>
    main()
  File "/content/chaekiji/server/lab/make_city_config.py", line 70, in main
    f"      python3 lab/measure.py --config {out.relative_to(ROOT)} --titles lab/out/titles.csv --limit 5 --tag {a.city}")
                                             ^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.15/x64/lib/python3.12/pathlib.py", line 682, in relative_to
    raise ValueError(f"{str(self)!r} is not in the subpath of {str(other)!r}")
ValueError: '/content/cfg_광명_raw.yaml' is not in the subpath of '/content/chaekiji/server'
```

## 읽는 법과 한계

- 같은 코드가 설정 파일만 바뀐 채 다른 도시 도서관의 소장·대출로 갈래(바로 이용·관내 상호대차·예약·책바다)를 정했다. 바뀐 것은 도서관 코드표와 규정 값뿐이다.
- 규정 값은 대부분 【확인】(부천 값 자리표시)이다. 운영하려면 그 도시 사서가 누리집 규정으로 바꿔야 한다. 안내문의 도착·보관 문장도 그 값에 따른다.
- 정보나루가 도서관을 「공공도서관」으로 등록한 곳만 들어간다. 작은도서관·학교도서관은 make_city_config의 기본 거르기로 뺐다.
- 대출 상태는 정보나루 조회일 전일 기준이라 그 도시 누리집의 실시간 상태와 다를 수 있다.

---
이 기록은 실제로 돌린 결과이며 사람이 고치지 않았다. 실패도 그대로 적는다.
