// 妙搭小站 - Service Worker
const CACHE_NAME = 'miaoda-station-v17';
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

// 允许页面主动通知等待中的新 SW 立即接管（配合前端 controllerchange 平滑刷新）
self.addEventListener('message', (e) => {
  if (e.data && e.data.type === 'SKIP_WAITING') self.skipWaiting();
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
// 前端降级直连标记：?net=1 时完全绕开缓存（规避个别 X5 内核缓存流卡死）
function isNetBypass(url) {
  try { return new URL(url).searchParams.get('net') === '1'; } catch (e) { return false; }
}
// 离线时导航请求的页面兜底
async function navFallback(req) {
  const hit = await caches.match(req);
  if (hit) return hit;
  try {
    const p = new URL(req.url).pathname;
    if (p.endsWith('biquge.html') || p.endsWith('/games/') || p.endsWith('/games')) {
      const b = await caches.match('biquge.html'); if (b) return b;
    }
  } catch (e) {}
  return caches.match('index.html');
}

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;

  // 1) 页面导航（HTML）：网络优先，保证每次打开都是最新版（根治“首次显示旧版、要再刷新一次”）；
  //    断网时才回退缓存，实现离线可开。
  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req)
        .then((resp) => {
          if (resp && resp.ok) {
            const copy = resp.clone();
            caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
          }
          return resp;
        })
        .catch(() => navFallback(req))
    );
    return;
  }

  // 2) 离线语音资源
  if (isTtsResource(req.url)) {
    // 前端显式要求绕缓存直连（X5 流式卡死时的兜底通道）
    if (isNetBypass(req.url)) {
      e.respondWith(fetch(req).catch(() => caches.match(req, { ignoreSearch: true })));
      return;
    }
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

  // 3) 其余静态资源：缓存优先，未命中走网络
  e.respondWith(
    caches.match(req).then((cached) => cached || fetch(req).catch(() => cached))
  );
});
