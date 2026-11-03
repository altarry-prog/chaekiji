#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Solar Pro 4 실측의 기록표: tools/model2/report_ai_metrics.py(공개 모델 지표 기록표)를 그대로 쓰고,
모델이 API로 돌아간다는 점만 글을 바꾼다(채점·표 계산은 같은 코드). 기록 파일 이름은 ai_metrics_solar_record_….md.
사용: python3 report_solar.py <결과 JSON 폴더> <기록 폴더> <실행 기록 주소>"""
import pathlib, sys

SRC = pathlib.Path(__file__).resolve().parents[1] / "model2" / "report_ai_metrics.py"
code = SRC.read_text(encoding="utf-8")
REPL = [
    ('NAME = {"gpt-oss:20b": "GPT-OSS 20B",', 'NAME = {"solar-pro4": "Solar Pro 4", "gpt-oss:20b": "GPT-OSS 20B",'),
    ('A(f"# AI가 맡는 몫 지표 — 공개 모델 {len({k[0] for k in ORDER})}종 · ',
     'A(f"# AI가 맡는 몫 지표 — Solar Pro 4(업스테이지 API) · '),
    ("f\"CPU {docs[0]['env'].get('cpu')}코어 · GPU 없음 · 메모리 {docs[0]['env'].get('mem')}(전체·사용) · Ollama {docs[0]['env'].get('ollama')} · 인증키·결제 없음\")",
     "\"모델은 업스테이지 API(solar-pro4)로 부름 · 같은 호스트(server/hosts/ollama_host.py)에 Ollama 모양을 오픈AI 모양으로 옮기는 작은 중계(tools/solar/upstage_ollama_proxy.py)를 붙임 · \"\n"
     "  \"인증키는 깃허브 Secrets(값은 기록하지 않음) · 크레딧은 2026 공공 AI 대전환 챌린지 참가자 API 지원 · 보낸 것은 지시문·이용자의 말·도구 결과(개인정보 없음)\")"),
    ('A("- 그래픽카드 없는 CPU 서버라 시간이 길다. 시간은 환경 차이를 그대로 적은 것이고, 판정은 도구가 정하므로 시간과 상관없다.")',
     'A("- 모델은 업스테이지 서버에서 돌아 시간에는 네트워크와 대기열이 들어 있다. 판정은 도구가 정하므로 시간과 상관없다.")'),
    ('"GPT-OSS(오픈AI)와 EXAONE(LG AI연구원)은 내려받는 공개 모델로, 참가 안내서(10. 21. 변경판)가 행정안전부 AI 공통기반에서 지원(또는 지원 예정)하는 모델로 든 것이다.")',
     '"Solar Pro 4(업스테이지)는 API로 부르는 모델이며, 참가 안내서(10. 21. 변경판)가 행정안전부 AI 공통기반에서 지원(또는 지원 예정)하는 모델로 든 솔라(Solar) 계열이다. '
     '공개 모델(GPT-OSS·EXAONE)의 같은 지표는 ai_metrics_record_actions_2026-11-01_1529.md에 있다.")'),
    ('out = DST / f"ai_metrics_record_actions_{stamp}.md"', 'out = DST / f"ai_metrics_solar_record_actions_{stamp}.md"'),
    ('"같은 날 13:44에 시작한 첫 실행이 시연 도서 밖 책을 정보나루로 조회하다 하루 호출 한도(500건)를 넘겨 취소하고, 정보나루를 부르지 않는 이 방식으로 다시 돌렸다. "',
     '"공개 모델 지표(11. 1.)와 같은 방식이다. "'),
]
missing = [a[:60] for a, _ in REPL if a not in code]
if missing:
    sys.exit("기록표 코드가 바뀌어 글을 맞출 수 없습니다: " + " / ".join(missing))
for a, b in REPL:
    code = code.replace(a, b, 1)
sys.argv[0] = str(SRC)
exec(compile(code, str(SRC), "exec"), {"__name__": "__main__", "__file__": str(SRC)})
