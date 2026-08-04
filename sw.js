/* 陈安叙工作台 Service Worker —— 用于 PWA「添加到主屏幕 / 离线打开」
 * 说明：
 *  - 本工作台是单文件 HTML，所有页面、样式、脚本、图标均已内联，
 *    数据（灵感/热点/财经）也以 window.ANXU_DATA 内嵌，因此离线缓存只需缓存本页即可。
 *  - 数据 JSON（ideas_data.json / hot_data.json / finance_data.json）当前不存在，
 *    页面会走内联兜底，所以这里对 *.json 请求不拦截、不缓存 404。
 */
const CACHE = 'anxu-workbench-v1';
const ASSETS = [
  './',
  './index.html',
  './index(1).html',
  './sw.js'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // 数据 JSON：始终放行到网络，让页面拿到 404 后自动用内联兜底（不缓存 404）
  if (url.pathname.endsWith('.json')) {
    return;
  }

  // 页面导航：网络优先（强制重新校验，避免浏览器缓存旧 HTML 导致看不到每日刷新）
  // cache: 'no-cache' 让每次打开都向服务器确认是否有新版本，离线下才回退到已缓存页面
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req, { cache: 'no-cache' }).catch(() =>
        caches.match(req) ||
        caches.match('./index.html') ||
        caches.match('./index(1).html') ||
        caches.match('./')
      )
    );
    return;
  }

  // 其余资源：缓存优先，缺失再回源并缓存
  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req).then((res) => {
        if (res && res.ok && (res.type === 'basic' || res.type === 'cors')) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      }).catch(() => cached);
    })
  );
});
