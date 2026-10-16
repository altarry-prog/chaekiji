#!/bin/sh
# 시연영상에 쓰는 글꼴 두 가지를 tools/video/fonts/ 에 받는다(저장소에는 넣지 않음 — .gitignore).
#  - Pretendard 1.3.9 (SIL Open Font License 1.1) — 화면 글
#  - D2Coding 1.3.2 (SIL Open Font License 1.1, 네이버) — 명령 창 글
set -e
cd "$(dirname "$0")"
mkdir -p fonts .dl
[ -f fonts/Pretendard-Bold.otf ] || {
  curl -sSL -o .dl/pretendard.zip https://github.com/orioncactus/pretendard/releases/download/v1.3.9/Pretendard-1.3.9.zip
  for w in Regular Medium SemiBold Bold; do unzip -p .dl/pretendard.zip "public/static/Pretendard-$w.otf" > "fonts/Pretendard-$w.otf"; done
  unzip -p .dl/pretendard.zip LICENSE.txt > fonts/Pretendard-LICENSE.txt
}
[ -f fonts/D2Coding-Bold.ttf ] || {
  curl -sSL -o .dl/d2coding.zip https://github.com/naver/d2codingfont/releases/download/VER1.3.2/D2Coding-Ver1.3.2-20180524.zip
  unzip -p .dl/d2coding.zip D2Coding/D2Coding-Ver1.3.2-20180524.ttf > fonts/D2Coding-Regular.ttf
  unzip -p .dl/d2coding.zip D2Coding/D2CodingBold-Ver1.3.2-20180524.ttf > fonts/D2Coding-Bold.ttf
}
rm -rf .dl
ls -la fonts
