# GPT 모델 구동 실측 기록 — 깃허브 액션·깃허브 모델 (2026-10-30 16:21 KST)

- 실행 환경: GitHub Actions(ubuntu-latest, 사람 손 없음) · 모델 호출: GitHub Models(models.github.ai, 무료 시험용) · 인증은 깃허브 액션 기본 토큰(권한 models: read), 인증키·결제 없음
- 실행 기록(공개): https://github.com/altarry-prog/chaekiji/actions/runs/41019440535
- 책이지: 저장소 main 커밋 `d2339fb` · 같은 서버(`server.py`, 모드 auto) · 같은 지시문(프롬프트 `consult`) · 공개 모델 2종 노트북과 같은 문의 5건 · 모델에 보이는 도구는 `consult_request` 하나 · 호스트는 `server/hosts/ollama_host.py` 그대로(모델 부르는 함수만 깃허브 모델로, `tools/model2/gpt_host.py`)
- 기준 판정: 모델 없이 같은 도구를 같은 값으로 직접 부른 결과. 판정은 도구가 정하므로 모델의 판정은 기준과 같아야 정상
- 원 기록: `gpt_host_log_actions_2026-10-30_1620.ndjson`(도구 호출) · `gpt_host_answers_actions_2026-10-30_1620.ndjson`(최종 답) — 실제로 돌린 결과이며 사람이 고치지 않았다

## 한눈에

| 모델 | 방식 | 성공 | 기준 판정과 같음 | 판정을 답에 옮김 | 도구 없이 답함 | 평균 시간 |
|---|---|---|---|---|---|---|
| openai/gpt-4.1-mini | — | 0/5 | 0/5 | 0/5 | 0/5 | 0.0초 |
| openai/gpt-5-mini | — | 0/5 | 0/5 | 0/5 | 0/5 | 0.0초 |

성공 = 상담 도구가 오류 없이 불렸고 최종 답이 있음 · 기준 판정과 같음 = 모델이 부른 도구의 판정 갈래가 기준 판정과 같음 · 판정을 답에 옮김 = 갈래 이름이 모델의 답에 들어 있음 · 도구 없이 답함 = 도구 결과 없이 모델이 스스로 쓴 답(창구에서 쓰면 안 됨) · (멈춤) = 같은 오류가 되풀이되거나 호출 한도에 닿아 호스트가 멈춘 문의

## 문의 1. 나미야 잡화점의 기적 빌리고 싶어요, 상동에서 받을게요

받을 도서관 상동 · 언어 ko · 기준 판정 **관내 상호대차**(relay · 2026-10-30)

| 모델 | 부른 도구 | 판정 | 기준과 같음 | 자료 | 시간 |
|---|---|---|---|---|---|
| openai/gpt-4.1-mini | (도구 호출 없음) | — | 다름 | — · — | 0.0초 |
| openai/gpt-5-mini | (도구 호출 없음) | — | 다름 | — · — | 0.0초 |

<details><summary>openai/gpt-4.1-mini의 답 원문</summary>

(답 없음)

</details>

<details><summary>openai/gpt-5-mini의 답 원문</summary>

(답 없음)

</details>

## 문의 2. 소년이 온다 있나요? 꿈빛도서관에서 받을게요

받을 도서관 꿈빛 · 언어 ko · 기준 판정 **바로 이용(수령관에 대출 가능)**(relay · 2026-10-30)

| 모델 | 부른 도구 | 판정 | 기준과 같음 | 자료 | 시간 |
|---|---|---|---|---|---|
| openai/gpt-4.1-mini | (도구 호출 없음) | — | 다름 | — · — | 0.0초 |
| openai/gpt-5-mini | (도구 호출 없음) | — | 다름 | — · — | 0.0초 |

<details><summary>openai/gpt-4.1-mini의 답 원문</summary>

(답 없음)

</details>

<details><summary>openai/gpt-5-mini의 답 원문</summary>

(답 없음)

</details>

## 문의 3. 채식주의자 상호대차 되나요?

받을 도서관 상동 · 언어 ko · 기준 판정 **소장 확인 불가(창구에서 조회)**(relay · —)

| 모델 | 부른 도구 | 판정 | 기준과 같음 | 자료 | 시간 |
|---|---|---|---|---|---|
| openai/gpt-4.1-mini | (도구 호출 없음) | — | 다름 | — · — | 0.0초 |
| openai/gpt-5-mini | (도구 호출 없음) | — | 다름 | — · — | 0.0초 |

<details><summary>openai/gpt-4.1-mini의 답 원문</summary>

(답 없음)

</details>

<details><summary>openai/gpt-5-mini의 답 원문</summary>

(답 없음)

</details>

## 문의 4. 불편한 편의점 원미도서관으로 가져다줄 수 있어요?

받을 도서관 원미 · 언어 ko · 기준 판정 **바로 이용(수령관에 대출 가능)**(relay · 2026-10-30)

| 모델 | 부른 도구 | 판정 | 기준과 같음 | 자료 | 시간 |
|---|---|---|---|---|---|
| openai/gpt-4.1-mini | (도구 호출 없음) | — | 다름 | — · — | 0.0초 |
| openai/gpt-5-mini | (도구 호출 없음) | — | 다름 | — · — | 0.0초 |

<details><summary>openai/gpt-4.1-mini의 답 원문</summary>

(답 없음)

</details>

<details><summary>openai/gpt-5-mini의 답 원문</summary>

(답 없음)

</details>

## 문의 5. Tôi muốn mượn cuốn 나미야 잡화점의 기적

받을 도서관 상동 · 언어 vi · 기준 판정 **관내 상호대차**(relay · 2026-10-30)

| 모델 | 부른 도구 | 판정 | 기준과 같음 | 자료 | 시간 |
|---|---|---|---|---|---|
| openai/gpt-4.1-mini | (도구 호출 없음) | — | 다름 | — · — | 0.0초 |
| openai/gpt-5-mini | (도구 호출 없음) | — | 다름 | — · — | 0.0초 |

<details><summary>openai/gpt-4.1-mini의 답 원문</summary>

(답 없음)

</details>

<details><summary>openai/gpt-5-mini의 답 원문</summary>

(답 없음)

</details>

---
대출 상태는 정보나루 조회일 전일 기준이며, 이 기록의 어떤 상담도 실제 접수로 이어지지 않았다. 깃허브 모델은 무료 시험용(분당·하루 호출 한도 있음)이라 운영 경로가 아니라 「GPT 계열에서도 같은 도구가 돈다」는 실측용이다.