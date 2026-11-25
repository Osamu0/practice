// オフライン用：一度読んだものをとっておき、次からはそれを返す（キャッシュ優先、裏で更新）。
// Cloudflare Access の後ろに置くとき、ログインの画面（別の住所への転送）をとっておかないように、
// 同じ住所から、転送されずに、成功したものだけをとっておく（R9）。
const CACHE = 'pd-techcheck-v1';
self.addEventListener('install', () => { self.skipWaiting(); });
self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k !== CACHE) await caches.delete(k); // 古い版を消す
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== location.origin) return;
  e.respondWith((async () => {
    const c = await caches.open(CACHE);
    const key = req.mode === 'navigate' ? new URL('./', location).href : req; // 画面の読み込みは index をひとつだけ持つ
    const hit = await c.match(key, { ignoreSearch: req.mode === 'navigate' });
    const net = fetch(req).then(r => {
      if (r.ok && r.type === 'basic' && !r.redirected) c.put(key, r.clone());
      return r;
    }).catch(() => hit);
    return hit || net;
  })());
});
