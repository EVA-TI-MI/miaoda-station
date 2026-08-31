// ============================================================
// 笔趣阁 离线神经 TTS Worker（sherpa-onnx WASM + aishell3 VITS）
// 模型文件位于 worker 同级 model/ 目录；运行时写入 WASM 内存文件系统。
// 主线程通过 postMessage 通信：
//   -> {type:'load'}            预加载/初始化引擎
//   -> {type:'gen',text,sid,speed} 合成一段，返回 PCM Float32
//   <- {type:'progress',stage,percent,msg}
//   <- {type:'ready',numSpeakers,sampleRate}
//   <- {type:'result',samples,sampleRate}
//   <- {type:'error',message}
// ============================================================
let tts = null;
let loadState = 'idle'; // idle | loading | ready | error
let pendingGen = null;   // ready 前到达的合成请求，只保留最新一段

function post(o) { try { self.postMessage(o); } catch (e) {} }

// 全局兜底：glue/WASM/异步里的未捕获错误也要上报，避免在 QQ/微信(X5) 内核里静默卡死
self.addEventListener('error', function (ev) {
  post({ type: 'error', message: '离线引擎脚本错误：' + ((ev && ev.message) || '未知错误') });
});
self.addEventListener('unhandledrejection', function (ev) {
  const r = ev && ev.reason;
  post({ type: 'error', message: '离线引擎加载异常：' + ((r && r.message) || r || '未知异常') });
});

// 带下载进度的文件读取（兼容 QQ/微信 X5 内核）：
// 1) 优先流式读取并回报进度；
// 2) 流式若 STALL_MS 内无任何数据（X5 下 getReader 偶发永久挂起），降级为一次性 arrayBuffer；
// 3) 仍失败则带 ?net=1 + cache:no-store 绕开 SW 缓存直连网络重试一次。
const STALL_MS = 15000;
async function fetchArrayBufferDirect(rel, useNetBypass) {
  const url = useNetBypass ? (rel + (rel.indexOf('?') >= 0 ? '&' : '?') + 'net=1') : rel;
  const opt = useNetBypass ? { cache: 'no-store' } : {};
  return await fetch(url, opt);
}
async function fetchWithProgress(rel, label, onPct) {
  // 第一遍：尝试流式
  try {
    const resp = await fetchArrayBufferDirect(rel, false);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const len = Number(resp.headers.get('Content-Length') || 0);
    if (!resp.body || !len || typeof resp.body.getReader !== 'function') {
      const ab0 = await resp.arrayBuffer(); onPct(100); return new Uint8Array(ab0);
    }
    const reader = resp.body.getReader();
    const chunks = []; let loaded = 0, last = -1, stalled = false;
    const stall = new Promise(function (resolve) {
      setTimeout(function () { stalled = true; resolve(); }, STALL_MS * 6); // 总兜底 90s
    });
    let tick = Date.now();
    while (true) {
      const rd = await Promise.race([
        reader.read(),
        new Promise(function (resolve) { setTimeout(function () { resolve({ __stall: true }); }, STALL_MS); })
      ]);
      if (rd && rd.__stall) {
        if (Date.now() - tick >= STALL_MS) { stalled = true; break; } // 15s 无进展
        continue;
      }
      if (rd.done) break;
      chunks.push(rd.value); loaded += rd.value.length; tick = Date.now();
      const pct = Math.floor(loaded * 100 / len);
      if (pct !== last) { last = pct; onPct(pct); }
    }
    if (!stalled) {
      const out = new Uint8Array(loaded); let off = 0;
      for (const c of chunks) { out.set(c, off); off += c.length; }
      if (loaded > 0) { onPct(100); return out; }
    }
    try { reader.cancel(); } catch (e) {}
    throw new Error('stream-stall');
  } catch (e1) {
    // 第二遍：一次性读取（X5 对 arrayBuffer 通常更稳）
    try {
      const r2 = await fetchArrayBufferDirect(rel, false);
      if (r2.ok) { const ab = await r2.arrayBuffer(); onPct(100); return new Uint8Array(ab); }
    } catch (e2) {}
    // 第三遍：绕开 SW 缓存直连
    const r3 = await fetchArrayBufferDirect(rel, true);
    if (!r3.ok) throw new Error(label + ' 下载失败 HTTP ' + r3.status);
    const ab3 = await r3.arrayBuffer(); onPct(100); return new Uint8Array(ab3);
  }
}

self.Module = {
  locateFile: function (path) { return path; }, // .wasm 与 worker 同目录
  // 返回空包，跳过 glue 内绑定的其它模型数据
  getPreloadedPackage: function () { return new ArrayBuffer(0); },
  setStatus: function (s) {
    post({ type: 'progress', stage: 'wasm', msg: String(s) });
  },
  onRuntimeInitialized: async function () {
    try {
      const need = [
        ['model/model.onnx', 'model.onnx'],
        ['model/tokens.txt', 'tokens.txt'],
        ['model/lexicon.txt', 'lexicon.txt'],
        ['model/date.fst', 'date.fst'],
        ['model/phone.fst', 'phone.fst'],
        ['model/number.fst', 'number.fst'],
      ];
      // 权重：模型主体占 96%，其余文件占 4%（按数量均分）
      for (let i = 0; i < need.length; i++) {
        const [rel, virt] = need[i];
        const isMain = virt === 'model.onnx';
        const u8 = await fetchWithProgress(rel, virt, function (pct) {
          const overall = isMain ? pct * 0.96 : 96 + (i - 1) * 0.8 + pct * 0.008;
          post({ type: 'progress', stage: 'model', percent: Math.min(99, Math.round(overall)),
                 msg: '加载离线语音模型 ' + Math.round(overall) + '%' });
        });
        self.Module.FS_createDataFile('/' + virt, null, u8, true, true, true);
      }
      post({ type: 'progress', stage: 'init', percent: 99, msg: '正在初始化语音引擎…' });
      const cfg = {
        offlineTtsModelConfig: {
          offlineTtsVitsModelConfig: {
            model: './model.onnx',
            lexicon: './lexicon.txt',
            tokens: './tokens.txt',
            dataDir: '',
            noiseScale: 0.667, noiseScaleW: 0.8, lengthScale: 1.0
          },
          numThreads: 1, debug: 0, provider: 'cpu'
        },
        ruleFsts: './date.fst,./phone.fst,./number.fst',
        ruleFars: '', maxNumSentences: 1
      };
      tts = createOfflineTts(self.Module, cfg);
      loadState = 'ready';
      post({ type: 'ready', numSpeakers: tts.numSpeakers, sampleRate: tts.sampleRate });
      if (pendingGen) { const g = pendingGen; pendingGen = null; doGen(g); }
    } catch (e) {
      loadState = 'error';
      post({ type: 'error', message: '离线引擎初始化失败：' + ((e && e.message) || e) });
    }
  }
};

if (typeof WebAssembly === 'undefined') {
  post({ type: 'error', message: '当前浏览器内核不支持 WebAssembly，离线引擎不可用，已为你保留在线语音' });
} else {
  try {
    importScripts('sherpa-onnx-wasm-main-tts.js', 'sherpa-onnx-tts.js');
  } catch (e) {
    post({ type: 'error', message: '离线引擎组件加载失败：' + ((e && e.message) || e) });
  }
}

function doGen(d) {
  if (!tts) { pendingGen = d; return; }
  try {
    const audio = tts.generate({ text: d.text, sid: d.sid || 0, speed: d.speed || 1.0 });
    post({ type: 'result', reqId: d.reqId, samples: audio.samples, sampleRate: tts.sampleRate },
         [audio.samples.buffer]);
  } catch (e) {
    post({ type: 'error', reqId: d.reqId, message: '合成失败：' + ((e && e.message) || e) });
  }
}

self.onmessage = function (e) {
  const d = e.data || {};
  if (d.type === 'load') {
    if (loadState === 'idle') {
      loadState = 'loading';
      // glue 加载后会自行实例化并触发 onRuntimeInitialized，这里仅作状态兜底
      post({ type: 'progress', stage: 'wasm', percent: 1, msg: '正在加载离线语音引擎…' });
    }
  } else if (d.type === 'gen') {
    if (loadState === 'error') { post({ type: 'error', reqId: d.reqId, message: '引擎未就绪' }); return; }
    if (loadState === 'ready') doGen(d); else pendingGen = d;
  }
};
