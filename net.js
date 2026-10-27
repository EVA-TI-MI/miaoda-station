/* net.js — 妙搭小站联机网络层
 * 拓扑：房主星型。成员直连房主（WebRTC DataChannel），信令走 PeerJS 官方云（wss://0.peerjs.com，公网可达）。
 * 场景：局域网（同一 WiFi，P2P 直连最快）与远程（异地公网，同房间码互通，STUN 打洞，P2P 优先；
 *       双方为 cone NAT 的家用宽带一般可直连，严格 NAT 需中继——公共免费 TURN 国内不可达，未内置）。
 * 权威：房主运行完整游戏状态机，向各成员广播脱敏状态视图；成员只发意图、收视图渲染。
 * 单机模式完全不受影响；本文件仅被联机流程动态加载 PeerJS 库。
 */
(function(){
"use strict";
var PEER_SRC='peerjs.min.js';   // 同源本地库
// 默认连官方云：new Peer(id) → wss://0.peerjs.com；显式补充公共 STUN 提升打洞成功率
var ICE={iceServers:[
  {urls:['stun:stun.l.google.com:19302','stun:stun1.l.google.com:19302']},
  {urls:'stun:stun.services.mozilla.com'}
]};
var PEER_OPTS={debug:0, config:ICE};
var CODES='ABCDEFGHJKLMNPQRSTUVWXYZ23456789';

var L={ mode:'idle', role:null, peer:null, conns:[], conn:null, code:null };

function genCode(len){
  len=len||6;
  var s='';
  for(var i=0;i<len;i++) s+=CODES[Math.floor(Math.random()*CODES.length)];
  return s;
}

/* 动态加载 peerjs.min.js（首次联机才加载，单机不依赖） */
function loadPeer(cb){
  if(typeof Peer!=='undefined'){ cb(); return; }
  if(window.__peerLoading){ window.__peerCbs.push(cb); return; }
  window.__peerLoading=true; window.__peerCbs=[cb];
  var s=document.createElement('script');
  s.src=PEER_SRC;
  s.onload=function(){ window.__peerLoading=false; var q=window.__peerCbs; window.__peerCbs=[]; q.forEach(function(f){f();}); };
  s.onerror=function(){ window.__peerLoading=false; var q=window.__peerCbs; window.__peerCbs=[]; q.forEach(function(f){f({error:'peerjs-load-fail'});}); };
  document.head.appendChild(s);
}

/* 创建房间（房主）。opts:{game,onOpen(code),onPeer(conn),onData(conn,msg),onPeerClose(conn),onError(err)}
 * onData 收到的是已 JSON.parse 的成员消息。 */
function createRoom(opts){
  loadPeer(function(err){
    if(err){ opts.onError&&opts.onError(err); return; }
    var code=genCode();
    var peer=null;
    function mk(){
      peer=new Peer('mst-'+opts.game+'-'+code, PEER_OPTS);
      peer.on('open',function(id){
        L.mode='host'; L.role='host'; L.peer=peer; L.code=code;
        opts.onOpen&&opts.onOpen(code);
      });
      peer.on('connection',function(conn){
        conn.on('open',function(){
          L.conns.push(conn);
          conn.on('data',function(d){ try{ opts.onData&&opts.onData(conn,JSON.parse(d)); }catch(e){ opts.onData&&opts.onData(conn,{raw:d}); } });
          conn.on('close',function(){ L.conns=L.conns.filter(function(c){return c!==conn;}); opts.onPeerClose&&opts.onPeerClose(conn); });
          opts.onPeer&&opts.onPeer(conn);
        });
      });
      peer.on('error',function(e){
        if(e.type==='unavailable-id'||e.type==='peer-unavailable'||e.type==='id-taken'){
          // 房间码被占用：换码重试
          code=genCode();
          try{ peer.destroy(); }catch(_){}
          mk();
          return;
        }
        opts.onError&&opts.onError(e);
      });
      peer.on('disconnected',function(){ opts.onError&&opts.onError({type:'signaling-lost'}); });
    }
    mk();
  });
}

/* 加入房间。opts:{game,code,onOpen(conn),onData(conn,msg),onClose(),onError(err)} */
function joinRoom(opts){
  loadPeer(function(err){
    if(err){ opts.onError&&opts.onError(err); return; }
    var peer=new Peer(null, PEER_OPTS);
    peer.on('open',function(){
      var conn=peer.connect('mst-'+opts.game+'-'+opts.code,{reliable:true});
      var done=false;
      function ready(){
        if(done) return; done=true;
        L.mode='client'; L.role='client'; L.peer=peer; L.conn=conn; L.code=opts.code;
        conn.on('data',function(d){ try{ opts.onData&&opts.onData(conn,JSON.parse(d)); }catch(e){ opts.onData&&opts.onData(conn,{raw:d}); } });
        conn.on('close',function(){ opts.onClose&&opts.onClose(); });
        opts.onOpen&&opts.onOpen(conn);
      }
      conn.on('open',ready);
      conn.on('error',function(e){ opts.onError&&opts.onError(e); });
    });
    peer.on('error',function(e){
      if(e.type==='peer-unavailable'||e.type==='unavailable-id'){ opts.onError&&opts.onError({type:'room-not-found'}); return; }
      opts.onError&&opts.onError(e);
    });
    peer.on('disconnected',function(){ opts.onError&&opts.onError({type:'signaling-lost'}); });
  });
}

/* 客户端发消息给房主 */
function send(msg){
  if(L.mode==='client'&&L.conn&&L.conn.open){
    try{ L.conn.send(JSON.stringify(msg)); return true; }catch(e){ return false; }
  }
  return false;
}
/* 房主广播给所有成员 */
function broadcast(msg){
  var s=JSON.stringify(msg);
  L.conns.forEach(function(c){ try{ if(c.open) c.send(s); }catch(e){} });
}
/* 房主定向发送 */
function sendTo(conn,msg){
  try{ if(conn&&conn.open) conn.send(JSON.stringify(msg)); }catch(e){}
}

/* 断开联机（本地清理） */
function leave(){
  try{ if(L.peer) L.peer.destroy(); }catch(e){}
  L.mode='idle'; L.role=null; L.peer=null; L.conns=[]; L.conn=null; L.code=null;
}

window.Net={ genCode:genCode, createRoom:createRoom, joinRoom:joinRoom,
  send:send, broadcast:broadcast, sendTo:sendTo, leave:leave,
  isHost:function(){return L.role==='host';},
  isClient:function(){return L.role==='client';},
  mode:function(){return L.mode;},
  code:function(){return L.code;} };
})();
