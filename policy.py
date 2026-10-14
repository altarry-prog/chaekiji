# -*- coding: utf-8 -*-
"""규정 판정 엔진 — 숫자는 전부 설정(YAML)에서 온다. 코드에 지역 규정이 없다.
v0.3: 회원 상태(연체·정지) · 자료 제외(신착·비도서) · 동일 도서 중복 신청 판정 추가."""

def check(rules: dict, member: dict, pickup_on_shelf: bool, pickup: str,
          item: dict = None, isbn13: str = None):
    checks = []
    def rule(name, passed, detail):
        checks.append({"rule": name, "pass": bool(passed), "detail": detail})

    if rules.get("block_if_pickup_on_shelf", True):
        rule("수령관 동일도서 비치 시 신청 불가", not pickup_on_shelf,
             "수령관 서가에 비치 중" if pickup_on_shelf else "수령관 소장본 서가에 없음(대출중 또는 미소장)")
    rule(f"상호대차 1인 {rules['ill_limit']}권",
         member["ill_count"] < rules["ill_limit"], f"현재 {member['ill_count']}/{rules['ill_limit']}권")
    rule(f"통합 대출 {rules['total_limit']}권",
         member["total_loans"] < rules["total_limit"], f"현재 {member['total_loans']}/{rules['total_limit']}권")
    at = member.get("loans_at", {}).get(pickup, 0)
    rule(f"도서관별 {rules['per_lib_limit']}권(직접+상호대차)",
         at < rules["per_lib_limit"], f"{pickup} 현재 {at}/{rules['per_lib_limit']}권")

    # [v0.3] 회원 상태 — 연체·정지 회원은 알파스가 막는다. 판정에도 같은 규정을 둔다.
    if rules.get("block_if_overdue", True):
        od = member.get("overdue_count", 0)
        sus = bool(member.get("suspended", False))
        rule("연체·정지 회원 신청 불가", od == 0 and not sus,
             ("연체 " + str(od) + "건" + (" · 이용 정지 중" if sus else "")) if (od or sus) else "연체·정지 없음")

    # [v0.3] 자료 제외 — 신착·비도서 등 상호대차 제외 자료(값은 설정에서, 예시 규정).
    excl = rules.get("excluded_types", []) or []
    exna = bool(rules.get("exclude_new_arrival", False))
    if item:
        t = item.get("type", "일반")
        na = bool(item.get("new_arrival", False))
        bad_type = t in excl
        bad_new = exna and na
        detail = ("자료 유형 " + t + " — 제외 대상") if bad_type else \
                 ("신착 자료 — 신착 제외 기간" if bad_new else f"유형 {t} · 신착 아님")
        rule("상호대차 제외 자료 아님", not (bad_type or bad_new), detail)
    else:
        rule("상호대차 제외 자료 아님", True, "서지 미확인 — 제외 판정 보류(통과 처리)")

    # [v0.3] 중복 — 같은 도서에 진행 중 신청이 있으면 새 신청을 막는다.
    act = member.get("active_isbns", [])
    dup = bool(isbn13) and isbn13 in act
    rule("동일 도서 중복 신청 없음", not dup,
         "이미 진행 중인 신청 있음" if dup else "진행 중 신청 없음")

    return {"allowed": all(c["pass"] for c in checks), "checks": checks}
