/* ===== 妙搭小站 · 账号与排行榜客户端 rank.js =====
 * 后端：本机 Flask + MySQL（默认 http://127.0.0.1:5000，可 localStorage.miaodaApiBase 覆盖）
 * 用法：<script src="rank.js"></script>
 *   window.RANK.isAuthed() / login() / logout() / register() / report(game,score,meta)
 * 登录后每 60s 自动扫描 localStorage 中全部游戏的最佳成绩并补录到后端。
 */
(function () {
  'use strict';
  var API = 'http://127.0.0.1:5000';
  try { if (localStorage.getItem('miaodaApiBase')) API = localStorage.getItem('miaodaApiBase'); } catch (e) {}
  var TOKEN_KEY = 'miaodaToken', USER_KEY = 'miaodaUser';
  var warned = false;

  function warnOnce() {
    if (!warned) { warned = true; console.warn('[排行榜] 后端未启动或不可达：请在本机运行 server/start.bat'); }
  }
  function getToken() { try { return localStorage.getItem(TOKEN_KEY) || ''; } catch (e) { return ''; } }
  function getUser() { try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); } catch (e) { return null; } }
  function api(path, opts) {
    opts = opts || {};
    opts.headers = opts.headers || {};
    var t = getToken();
    if (t) opts.headers['Authorization'] = 'Bearer ' + t;
    return fetch(API + path, opts).then(function (r) { return r.json(); }).catch(function () { warnOnce(); return { ok: false, msg: '后端不可达' }; });
  }

  /* 各游戏本地最佳成绩键：
   *  {game, key, parse} parse: 'num' 直接数值 / 'jsonMin' JSON对象取最小值（时长/步数越小越好）
   */
  var GAME_KEYS = [
    { game: '2048', key: 'miaoda2048BestV43', parse: 'num' },
    { game: 'minesweeper', key: 'miaodaMineBestV43', parse: 'num' },
    { game: 'tetris', key: 'miaodaTetrisBestV44', parse: 'num' },
    { game: 'breakout', key: 'miaodaBreakoutBestV44', parse: 'num' },
    { game: 'mole', key: 'miaodaMoleBestV44', parse: 'num' },
    { game: 'jump', key: 'miaodaJumpBestV43', parse: 'num' },
    { game: 'dino', key: 'miaodaDinoBestV44', parse: 'num' },
    { game: 'pong', key: 'miaodaPongBestV44', parse: 'num' },
    { game: 'memory', key: 'miaodaMemoryBestV44', parse: 'jsonMin' },
    { game: 'lianliankan', key: 'miaodaLianlianBestV47', parse: 'jsonMin' },
    { game: 'sudoku', key: 'miaodaSudokuBestV42', parse: 'jsonMin' },
    { game: 'hrd', key: 'miaodaHrdBestV42', parse: 'jsonMin' },
    { game: 'sokoban', key: 'miaodaSokobanBestV43', parse: 'num' },
    { game: 'nonogram', key: 'miaodaNonogramBestV46', parse: 'jsonMin' },
    { game: 'slitherlink', key: 'miaodaSlitherBestV46', parse: 'jsonMin' },
    { game: 'hashi', key: 'miaodaHashiBestV47', parse: 'jsonMin' },
    { game: 'nurikabe', key: 'miaodaNurikabeBestV47', parse: 'jsonMin' },
    { game: 'akari', key: 'miaodaAkariBestV47', parse: 'jsonMin' },
    { game: 'calc24', key: 'miaodaCalc24BestV46', parse: 'num' },
    { game: 'guessnum', key: 'miaodaGuessNumBestV46', parse: 'num' },
    { game: 'p15', key: 'miaodaP15BestV47', parse: 'num' },
    { game: 'reversi', key: 'miaodaReversiBestV45', parse: 'num' },
    { game: 'junqi', key: 'miaodaJunqiBestV45', parse: 'num' },
    { game: 'checkers', key: 'miaodaCheckersBestV45', parse: 'jsonMin' },
    { game: 'animals', key: 'miaodaAnimalsBestV45', parse: 'num' }
  ];
  var SNAKE_KEY = 'neonSnakeHighScore'; // 腾蛇按用户带后缀 neonSnakeHighScore_<username>

  function readLocal(key, parse) {
    try {
      var raw = localStorage.getItem(key);
      if (raw === null || raw === '') return null;
      if (parse === 'jsonMin') {
        var o = JSON.parse(raw);
        var vals = Object.keys(o).map(function (k) { return parseInt(o[k], 10); }).filter(function (v) { return isFinite(v); });
        if (!vals.length) return null;
        return Math.min.apply(null, vals);
      }
      var n = parseInt(raw, 10);
      return isFinite(n) ? n : null;
    } catch (e) { return null; }
  }

  var RANK = {
    apiBase: API,
    isAuthed: function () { return !!getToken(); },
    getUser: getUser,

    register: function (username, password, nickname) {
      return api('/api/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: username, password: password, nickname: nickname }) })
        .then(function (d) { if (d.ok) RANK._setAuth(d); return d; });
    },
    login: function (username, password) {
      return api('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: username, password: password }) })
        .then(function (d) { if (d.ok) RANK._setAuth(d); return d; });
    },
    logout: function () {
      var t = getToken();
      localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY);
      if (t) { try { fetch(API + '/api/logout', { method: 'POST', headers: { 'Authorization': 'Bearer ' + t } }); } catch (e) {} }
    },
    _setAuth: function (d) {
      try {
        localStorage.setItem(TOKEN_KEY, d.token);
        localStorage.setItem(USER_KEY, JSON.stringify({ username: d.username, nickname: d.nickname }));
      } catch (e) {}
    },

    /* 上报一条成绩（未登录/后端不可达时静默跳过，本地成绩不受影响） */
    report: function (game, score, meta) {
      if (!RANK.isAuthed()) return;
      if (!isFinite(score)) return;
      api('/api/score', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ game: game, score: Math.round(score), meta: meta || '' }) });
    },

    /* 扫描本地全部游戏最佳成绩补录到后端（登录后自动调用/定时） */
    syncLocalBest: function () {
      if (!RANK.isAuthed()) return;
      var u = getUser();
      var payload = [];
      for (var i = 0; i < GAME_KEYS.length; i++) {
        var g = GAME_KEYS[i];
        var v = readLocal(g.key, g.parse);
        if (v !== null && v > 0) payload.push({ game: g.game, score: v });
      }
      if (u && u.username) {
        var sv = readLocal(SNAKE_KEY + '_' + u.username, 'num');
        if (sv === null) sv = readLocal(SNAKE_KEY, 'num');
        if (sv !== null && sv > 0) payload.push({ game: 'snake', score: sv });
      }
      if (!payload.length) return;
      api('/api/scores-batch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ items: payload }) });
    }
  };

  /* 登录后每 60s 自动补录一次本地成绩 */
  setInterval(function () { RANK.syncLocalBest(); }, 60000);

  window.RANK = RANK;
})();
