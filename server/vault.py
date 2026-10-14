# -*- coding: utf-8 -*-
"""토큰 금고 — 진짜 회원 식별자는 이 파일 밖으로 나가지 않는다.
에이전트·LLM 쪽에는 임시 토큰(tok_…)만 보이고,
커넥터가 회원 정보를 조회하는 순간에만 내부 id로 풀린다."""

_TOKENS = { "tok_kimsj": "m-1004",    # 시연용 고정 토큰 (운영: SSO 로그인 시 발급·만료)
            "tok_parkys": "m-2002" }  # 연체 시나리오용(가상)

def resolve(token: str) -> str:
    if token not in _TOKENS:
        raise PermissionError("유효하지 않은 이용자 토큰")
    return _TOKENS[token]
