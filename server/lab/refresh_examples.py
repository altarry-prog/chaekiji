#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""시연 웹 예시 단추 ①②의 장면 자료를 그날 새벽 실제 자료로 바꾼다(v1.12.20~, 여러 번 돌려도 같음).

  python3 server/lab/refresh_examples.py . data/holdings-today.json     # 저장소 루트에서

- 바꾸는 곳(index.html): CASES의 실제 책 4권(소년이 온다·나미야·불편한 편의점·설민석)의 bx, const 기준일,
  첫 화면 단추 ①② 배지와 바닥글·ⓘ 날짜(스크립트가 돌기 전에 보이는 글).
- 갈래 확인: ① 한강 소년이 온다는 상동 대출 중이고 다른 관에 대출 가능(관내 상호대차), ② 불편한 편의점은 상동 대출 가능(바로 이용).
  (v1.12.22, 10. 30.: ①을 나미야 잡화점의 기적에서 소년이 온다로 바꿈. 담당자 15:03 요청·15:29 승인)
  둘 중 하나라도 안 맞으면 끝 코드 3(파일은 이미 바뀌었으니 git checkout으로 되돌리고 다른 날 자료를 고른다).
- 동결일(2026. 11. 5.)에 그날 새벽 자료로 한 번 돌리고, 판 표시(index.html 머리 줄)·서비스워커 캐시 이름을 올린 뒤
  README 움짤(tools/video 가지의 cmp/shoot_app.py·make_gif.py)도 같은 날 자료로 다시 찍는다. 인증키·정보나루 호출 없음."""
import sys, os, re, json
root, src = sys.argv[1], sys.argv[2]
p = os.path.join(root, 'index.html')
s = open(p, encoding='utf-8').read()
d = json.load(open(src, encoding='utf-8'))
iso = d['asof']; y, m, dd = iso.split('-'); M, D = int(m), int(dd)
KDAY = f'{y}. {M}. {D}.'
LIBS = ['꿈빛','꿈여울','도당','동화','별빛마루','북부','상동','송내','수주','심곡','역곡','역곡밝은','오정','원미','책마루','한울빛']
BOOKS = {'9788936434120': '소년이 온다', '9788972756194': '나미야 잡화점의 기적', '9791161571188': '불편한 편의점', '9791195794799': '설민석의 한국사 대모험'}

def fmt(h):
    v = [f'"{n}":"{h.get(n, "none")}"' for n in LIBS]
    return '{' + ','.join(v[:6]) + ',\n        ' + ','.join(v[6:12]) + ',\n        ' + ','.join(v[12:]) + '}'

for isbn, t in BOOKS.items():
    h = d['holdings'].get(isbn)
    assert h, f'자료에 없음: {t}'
    pat = re.compile(r'(isbn:"' + isbn + r'"\},\n\s*bx:)\{[^}]*\}')
    assert len(pat.findall(s)) == 1, f'bx 자리 못 찾음: {t}'
    s = pat.sub(lambda mm: mm.group(1) + fmt(h), s)

s, n = re.subn(r'const 기준일 = "[^"]*";', f'const 기준일 = "{KDAY}";', s); assert n == 1
# 첫 화면 단추 ①② 배지(스크립트 전 글)
s, n = re.subn(r'(<span class="m">[①②] [^<]*<em class="lv">)[^<]*(</em>)', lambda mm: mm.group(1) + f'{M}. {D}. 실제 자료' + mm.group(2), s); assert n == 2, n
s, n = re.subn(r'(<span id="footSrc">)[^<]*(</span>)', lambda mm: mm.group(1) + f'자료 {M}. {D}. 조회' + mm.group(2), s); assert n == 1
s, n = re.subn(r'(<span id="exDayInfo">)[^<]*(</span>)', lambda mm: mm.group(1) + KDAY + mm.group(2), s); assert n == 1
open(p, 'w', encoding='utf-8').write(s)

# 갈래 확인
H = d['holdings']
son, conv = H['9788936434120'], H['9791161571188']
c1 = son.get('상동') == 'busy' and any(v == 'ok' for k, v in son.items() if k != '상동')
c2 = conv.get('상동') == 'ok'
okn = sum(1 for k, v in son.items() if k != '상동' and v == 'ok')
print(f'기준일 {KDAY} · ① 소년이 온다: 상동 {son.get("상동")}, 다른 관 대출 가능 {okn}곳 → {"관내 상호대차 ✓" if c1 else "✗ 갈래 안 맞음"}')
print(f'           ② 불편한 편의점: 상동 {conv.get("상동")} → {"바로 이용 ✓" if c2 else "✗ 갈래 안 맞음"}')
for isbn in ('9788972756194', '9791195794799'):
    print(f'           (단추 아님) {BOOKS[isbn]}: 상동 {H[isbn].get("상동")}')
sys.exit(0 if (c1 and c2) else 3)
