// 妙搭小站 - Service Worker
const CACHE_NAME = 'miaoda-station-v10';
// 离线语音引擎/模型独立缓存（体积约 45MB，跨 SW 版本长期保留，不随主缓存清理）
const TTS_CACHE = 'biquge-tts-v1';
const ASSETS = [
  'index.html',
  'snake.html',
  'biquge.html',
  'novels_data.js',
  'manifest.json',
  'icon-192.png',
  'icon-512.png'
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          // 保留当前主缓存与离线语音缓存（模型很大，不随版本重下）
          .filter((k) => k !== CACHE_NAME && k !== TTS_CACHE)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// 判断是否为离线 TTS 引擎/模型资源（根目录 /tts/ 或 /games/tts/ 均命中）
function isTtsResource(url) {
  try {
    const u = new URL(url);
    return u.origin === self.location.origin && u.pathname.includes('/tts/');
  } catch (e) {
    return false;
  }
}

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;

  // 离线语音资源：缓存优先，未命中走网络并运行时落盘，断网回退缓存
  if (isTtsResource(req.url)) {
    e.respondWith(
      caches.open(TTS_CACHE).then(async (cache) => {
        const hit = await cache.match(req);
        if (hit) return hit;
        try {
          const resp = await fetch(req);
          if (resp && (resp.ok || resp.type === 'opaque')) {
            try { cache.put(req, resp.clone()); } catch (err) {}
          }
          return resp;
        } catch (err) {
          const fallback = await cache.match(req);
          if (fallback) return fallback;
          throw err;
        }
      })
    );
    return;
  }

  // 其余资源：缓存优先
  e.respondWith(
    caches.match(req).then((cached) => cached || fetch(req).catch(() => cached))
  );
});
