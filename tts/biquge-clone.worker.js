// ============================================================
// 笔趣阁 · 我的声音克隆 Worker（sherpa-onnx ZipVoice distill-int8 / WASM）
// 模型与页面同源托管在 tts/zvmodel/（GitHub Pages 单文件≤100MB，故 decoder 切成
// 两个分块 part0/part1，下载后拼回）。用 Cache Storage 缓存，第二次打开免下载。
// espeak 数据包用 fflate 解到 MEMFS。
// 主线程协议：
//   -> {type:'load', dir}                dir 为模型目录相对 worker 的路径（默认 zvmodel）
//   -> {type:'gen', reqId, text, ref(Float32Array), refText, speed}
//   <- {type:'progress', percent, msg} / {type:'ready', sampleRate}
//   <- {type:'result', reqId, samples, sampleRate} / {type:'error', reqId?, message}
// 关键坑：pocket-tts wasm 的 MEMFS 预置了 /decoder.int8.onnx，故 ZipVoice 的
// decoder 已改名 zv_decoder.onnx，否则建文件节点撞名报 errno20。
// ============================================================
let tts = null, ready = false, loading = false;
function post(o) { try { self.postMessage(o); } catch (e) {} }

// 直接整体写入 MEMFS 的顶层文件
const PLAIN = ['tokens.txt', 'lexicon.txt', 'encoder.int8.onnx', 'vocos.onnx'];
// decoder 分块（拼回为 zv_decoder.onnx）
const DECODER_PARTS = ['zv_decoder.part0', 'zv_decoder.part1'];

self.Module = {
  locateFile: (p) => p,
  getPreloadedPackage: () => new ArrayBuffer(0),
  setStatus: (s) => post({ type: 'progress', msg: String(s) }),
  print: () => {}, printErr: () => {},
  onRuntimeInitialized() {}
};
importScripts('sherpa-onnx-wasm-main-tts.js', 'sherpa-onnx-tts.js');

// 模型缓存统一交给 Service Worker（/tts/ 路径缓存优先、运行时落盘、断网回退），
// Worker 不再单独开 Cache Storage，避免 195MB 模型被重复缓存两份。
async function fetchBytes(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error('模型下载失败 HTTP ' + resp.status + '：' + url);
  return new Uint8Array(await resp.arrayBuffer());
}

async function loadModels(dir) {
  loading = true;
  const root = (dir || 'zv').replace(/\/$/, '');
  post({ type: 'progress', percent: 1, msg: '正在准备「我的声音」引擎（首次约 195MB，仅下载一次）…' });

  const data = {};
  const all = PLAIN.concat(DECODER_PARTS);
  for (let i = 0; i < all.length; i++) {
    const name = all[i];
    post({ type: 'progress', percent: Math.round(i * 100 / (all.length + 1)), msg: '下载/读取 ' + name });
    data[name] = await fetchBytes(root + '/' + name);
  }
  // 拼回 decoder 分块
  const p0 = data[DECODER_PARTS[0]], p1 = data[DECODER_PARTS[1]];
  const dec = new Uint8Array(p0.length + p1.length);
  dec.set(p0, 0); dec.set(p1, p0.length);
  data['zv_decoder.onnx'] = dec;
  post({ type: 'progress', percent: 96, msg: '模型已就绪，正在载入引擎…' });

  const M = self.Module;
  for (const name of ['tokens.txt', 'lexicon.txt', 'encoder.int8.onnx', 'zv_decoder.onnx', 'vocos.onnx']) {
    M.FS_createDataFile('/', name, data[name], true, true, false);
  }
  // espeak 数据：按散文件清单逐个写入（zip 解包在 MEMFS 建目录不稳，散文件方式已验证）
  const manResp = await fetch(root + '/espeak-manifest.json');
  const esList = await manResp.json();
  for (let i = 0; i < esList.length; i++) {
    const path = esList[i];
    const parts = path.split('/');
    const d = parts.slice(0, -1).join('/');
    if (d) { try { M.FS_createPath('/', d, true, true, true); } catch (e) {} }
    const u = await fetchBytes(root + '/' + path);
    M.FS_createDataFile('/' + d, parts[parts.length - 1], u, true, true, false);
    if (i % 60 === 0) post({ type: 'progress', percent: Math.round(i * 100 / esList.length), msg: '载入语音数据 ' + i + '/' + esList.length });
  }

  const cfg = {
    offlineTtsModelConfig: {
      offlineTtsZipVoiceModelConfig: {
        tokens: './tokens.txt',
        encoder: './encoder.int8.onnx',
        decoder: './zv_decoder.onnx',
        vocoder: './vocos.onnx',
        dataDir: './espeak-ng-data',
        lexicon: './lexicon.txt',
        featScale: 0.1, tShift: 0.5, targetRMS: 0.1, guidanceScale: 1.0
      },
      numThreads: 4, debug: 0, provider: 'cpu'
    },
    ruleFsts: '', ruleFars: '', maxNumSentences: 1
  };
  tts = createOfflineTts(M, cfg);
  ready = true; loading = false;
  post({ type: 'ready', sampleRate: tts.sampleRate });
}

self.onmessage = function (e) {
  const d = e.data || {};
  if (d.type === 'load') {
    if (ready) { post({ type: 'ready', sampleRate: tts.sampleRate }); return; }
    if (loading) return;
    loadModels(d.dir).catch(function (err) {
      loading = false;
      post({ type: 'error', message: '克隆引擎加载失败：' + ((err && err.message) || err) });
    });
  } else if (d.type === 'gen') {
    if (!ready) { post({ type: 'error', reqId: d.reqId, message: '克隆引擎尚未就绪' }); return; }
    try {
      const opt = { sid: 0, speed: d.speed || 1.0 };
      if (d.ref) {
        opt.referenceAudio = Float32Array.from(d.ref);
        opt.referenceSampleRate = d.refSr || 24000;
        if (d.refText) opt.referenceText = d.refText;
      }
      const audio = tts.generateWithConfig(d.text, opt);
      post({ type: 'result', reqId: d.reqId, samples: audio.samples, sampleRate: audio.sampleRate }, [audio.samples.buffer]);
    } catch (err) {
      post({ type: 'error', reqId: d.reqId, message: '克隆合成失败：' + ((err && err.message) || err) });
    }
  }
};
