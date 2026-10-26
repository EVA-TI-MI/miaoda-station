/* ===== 妙搭小站 · 全局音效库 sounds.js =====
 * 所有音效由 Web Audio API 实时合成，无任何音频文件、离线可用。
 * 用法：<script src="sounds.js"></script> 后
 *   window.SFX.click()  / .win() / .lose() / .move() / .eat() / .explode()
 *   / .tick() / .coin() / .level() / .flip() / .pop() / .start() / .error()
 * 全局自动：任意 click 播放软点击音；检测到 .win/.lose/.over/.gameover
 * 可见容器出现时自动播放胜利/失败音。静音：localStorage miaodaSfxMuted='1'。
 */
(function(){
  'use strict';
  var ctx=null,muted=false;
  try{muted=localStorage.getItem('miaodaSfxMuted')==='1';}catch(e){}

  function ac(){
    if(ctx)return ctx;
    var AC=window.AudioContext||window.webkitAudioContext;
    if(!AC)return null;
    ctx=new AC();
    if(ctx.state==='suspended')ctx.resume();
    return ctx;
  }
  function ensure(){
    var c=ac();
    if(c&&c.state==='suspended'){c.resume();}
    return c;
  }
  function tone(freq,time,dur,type,vol,slideTo){
    var c=ac();if(!c)return;
    var o=c.createOscillator(),g=c.createGain();
    o.type=type||'sine';
    o.frequency.setValueAtTime(freq,c.currentTime+time);
    if(slideTo)o.frequency.exponentialRampToValueAtTime(slideTo,c.currentTime+time+dur);
    g.gain.setValueAtTime(vol||0.12,c.currentTime+time);
    g.gain.exponentialRampToValueAtTime(0.0001,c.currentTime+time+dur);
    o.connect(g);g.connect(c.destination);
    o.start(c.currentTime+time);o.stop(c.currentTime+time+dur+0.02);
  }
  function noise(time,dur,vol,hp){
    var c=ac();if(!c)return;
    var len=Math.max(1,Math.floor(c.sampleRate*dur));
    var buf=c.createBuffer(1,len,c.sampleRate),d=buf.getChannelData(0);
    for(var i=0;i<len;i++)d[i]=(Math.random()*2-1)*(1-i/len);
    var src=c.createBufferSource();src.buffer=buf;
    var f=c.createBiquadFilter();f.type='highpass';f.frequency.value=hp||800;
    var g=c.createGain();g.gain.setValueAtTime(vol||0.25,c.currentTime+time);
    g.gain.exponentialRampToValueAtTime(0.0001,c.currentTime+time+dur);
    src.connect(f);f.connect(g);g.connect(c.destination);
    src.start(c.currentTime+time);
  }
  var SFX={
    setMuted:function(m){muted=!!m;try{localStorage.setItem('miaodaSfxMuted',muted?'1':'0');}catch(e){}},
    isMuted:function(){return muted;},
    click:function(){if(muted)return;ensure();tone(760,0,0.05,'square',0.05,520);},
    hover:function(){if(muted)return;ensure();tone(520,0,0.04,'sine',0.03,600);},
    start:function(){if(muted)return;ensure();tone(440,0,0.12,'triangle',0.1,880);},
    move:function(){if(muted)return;ensure();tone(420,0,0.06,'sine',0.07,520);},
    eat:function(){if(muted)return;ensure();tone(320,0,0.14,'triangle',0.12,640);},
    flip:function(){if(muted)return;ensure();tone(560,0,0.08,'sine',0.08,420);},
    pop:function(){if(muted)return;ensure();tone(600,0,0.07,'sine',0.09,900);},
    tick:function(){if(muted)return;ensure();tone(1100,0,0.035,'square',0.04);},
    coin:function(){if(muted)return;ensure();tone(660,0,0.09,'triangle',0.1);tone(880,0.09,0.14,'triangle',0.1);},
    level:function(){if(muted)return;ensure();tone(523,0,0.09,'triangle',0.1);tone(659,0.09,0.09,'triangle',0.1);tone(784,0.18,0.16,'triangle',0.12);},
    win:function(){if(muted)return;ensure();tone(523,0,0.12,'triangle',0.12);tone(659,0.12,0.12,'triangle',0.12);tone(784,0.24,0.12,'triangle',0.12);tone(1047,0.36,0.32,'triangle',0.14);},
    lose:function(){if(muted)return;ensure();tone(392,0,0.16,'sawtooth',0.1);tone(311,0.16,0.16,'sawtooth',0.1);tone(233,0.32,0.4,'sawtooth',0.12);},
    explode:function(){if(muted)return;ensure();noise(0,0.32,0.3,400);tone(120,0,0.3,'sawtooth',0.14,60);},
    error:function(){if(muted)return;ensure();tone(220,0,0.14,'square',0.08,180);},
    clearLine:function(){if(muted)return;ensure();tone(880,0,0.07,'square',0.07);tone(1100,0.07,0.07,'square',0.07);},
    bounce:function(){if(muted)return;ensure();tone(240,0,0.08,'sine',0.1,180);},
    hit:function(){if(muted)return;ensure();tone(500,0,0.05,'square',0.08,300);}
  };

  // 全局自动：任意 click → 软点击音（排除文本输入区，避免打字声）
  document.addEventListener('click',function(e){
    if(muted)return;
    var t=e.target;
    if(t&&(t.tagName==='INPUT'||t.tagName==='TEXTAREA'||t.tagName==='SELECT'))return;
    if(!ctx){try{ctx=new (window.AudioContext||window.webkitAudioContext)();}catch(err){}}
    if(ctx&&ctx.state==='suspended')ctx.resume();
    SFX.click();
  },true);

  // 全局自动：检测 .win/.lose/.over/.gameover 可见容器出现 → 胜利/失败音
  function visible(el){
    if(!el||!el.getRootNode||el.nodeType!==1)return false;
    var r=el.getBoundingClientRect();
    return r.width>0&&r.height>0&&r.top<innerHeight&&r.bottom>0;
  }
  function scanWin(){
    if(muted)return;
    var wins=document.querySelectorAll('.win,.winner,.success,.gameover,.lose,.over');
    for(var i=0;i<wins.length;i++){
      var el=wins[i];
      if(!el.dataset.sfx){
        if(visible(el)){
          el.dataset.sfx='1';
          if(/gameover|lose|over/i.test(el.className))SFX.lose();else SFX.win();
        }
      }
    }
  }
  if(typeof MutationObserver!=='undefined'){
    try{
      var mo=new MutationObserver(function(){scanWin();});
      mo.observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['class','style']});
      setTimeout(scanWin,600);
    }catch(e){}
  }

  window.SFX=SFX;
})();
