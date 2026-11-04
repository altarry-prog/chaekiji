/* 책이지 서비스워커 — 화면은 항상 최신, 인터넷이 끊겨도 열림 */
const CACHE = 'chaekiji-v53';   /* v1.12.27(2026. 11. 4.): 사서용 상담 창 링크 · 권 번호 확인 · 서비스워커 안전장치 · v1.12.26: 직접 입력의 짧은 낱말로 시연 도서를 단정하지 않음 · v1.12.25: 「대신 한 일」 한 줄 바로잡음 */
const MINE = /^chaekiji-v\d+$/;   /* v1.12.27: 같은 주소(altarry-prog.github.io)를 쓰는 다른 화면의 캐시는 지우지 않는다(자체 점검) */
const SHELL = ['./index.html', './manifest.webmanifest', './icon-192.png', './icon-512.png',
  './covers/9788936434120.jpg', './covers/9788972756194.jpg', './covers/9791161571188.jpg', './covers/9791191824001.jpg'];   // v1.12.20 시연 도서 표지

self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).catch(() => {}));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => MINE.test(k) && k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

/* 네트워크 우선 → 실패 시 캐시. 깃허브에 새 index.html을 올리면 바로 반영된다.
   v1.12.23: 화면(페이지 열기) 요청은 브라우저에 남은 사본을 확인 없이 쓰지 않고 서버에 새로 확인(cache: no-cache) — 올린 직후 옛 화면이 섞이지 않게
   v1.12.27: 성공한 응답(200대)만 저장하고, 끊겼을 때 화면(index.html)으로 대신하는 것은 화면 열기 요청만. 자료 요청은 실패로 돌려준다 */
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== location.origin) return;
  e.respondWith(
    (req.mode === 'navigate' ? fetch(req.url, { cache: 'no-cache', credentials: 'same-origin' }) : fetch(req))
      .then(res => {
        if (res.ok && res.type === 'basic') {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(req, copy)).catch(() => {});
        }
        return res;
      })
      .catch(() =>
        caches.match(req).then(hit => hit || (req.mode === 'navigate' ? caches.match('./index.html') : Response.error()))
      )
  );
});
