import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,rm} from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {sign} from 'node:crypto';
import {createQQBridge,qqSigningKey,verifyQQCallback} from '../qq-bridge.mjs';

const secret='test-qq-client-secret';
const turn=()=>new Promise(r=>setTimeout(r,15));
const frame=(id,content,user='owner')=>({op:0,t:'C2C_MESSAGE_CREATE',d:{id,content,author:{user_openid:user,username:'本人'},timestamp:new Date().toISOString()}});
class Gateway {
  static instances=[];
  constructor(){this.sent=[];this.readyState=1;Gateway.instances.push(this);}
  send(text){this.sent.push(JSON.parse(text));}
  close(){this.readyState=3;this.onclose?.({code:1000});}
}
async function fixture(t,transport='websocket') {
  const dir=await mkdtemp(path.join(os.tmpdir(),'autoloop-qq-test-'));
  const apiCalls=[],localCalls=[];
  const snapshot={cards:[{id:2,version:1,kind:'ask',title:'是否继续',text:'已有工作保留',options:['继续','暂停']}],
    runs:[{id:3,state:'done',rule:'LifeAgent 开发',summary:'旧的开发结果'}]};
  const local=async(route,body)=>{
    localCalls.push({route,body});
    if(route==='state')return snapshot;
    if(route==='progress')return {text:'DEV-01：未完成'};
    if(route==='messages')return {event:42};
    if(route==='cards/2/answer'||route==='runs/3/cancel'||route==='cards/2/resolve')return {ok:true};
    throw Object.assign(Error('未知任务或卡片'),{status:404});
  };
  const fetchImpl=async(url,options={})=>{
    const u=new URL(url),body=options.body?JSON.parse(options.body):null;apiCalls.push({path:u.pathname,body,headers:options.headers});
    let data;
    if(u.pathname==='/app/getAppAccessToken')data={access_token:'test-access-token',expires_in:7200};
    else if(u.pathname==='/gateway')data={url:'wss://gateway.example.test'};
    else data={id:'sent-'+apiCalls.length};
    return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}});
  };
  const options={dataDir:dir,local,fetchImpl,Socket:Gateway,callbackPort:0,pollMs:600000};
  let bridge=await createQQBridge(options);
  await bridge.configure({appId:'12345678',secret,transport});await turn();
  t.after(async()=>{await bridge.stop();await rm(dir,{recursive:true,force:true});});
  return {get bridge(){return bridge;},dir,apiCalls,localCalls,snapshot,options,async restart(){await bridge.stop();bridge=await createQQBridge(options);await bridge.start();await turn();}};
}

test('QQ 官方文档签名向量及篡改/过期请求验证',()=>{
  const key=qqSigningKey('DG5g3B4j9X2KOErG');
  assert.equal(sign(null,Buffer.from('1725442341Arq0D5A61EgUu4OxUvOp'),key).toString('hex'),
    '87befc99c42c651b3aac0278e71ada338433ae26fcb24307bdc5ad38c1adc2d01bcfcadc0842edac85e85205028a1132afe09280305f13aa6909ffc2d652c706');
  const raw=Buffer.from('{"op":0}'),ts=String(Math.floor(Date.now()/1000));
  const headers={'x-signature-timestamp':ts,'x-signature-ed25519':sign(null,Buffer.concat([Buffer.from(ts),raw]),qqSigningKey(secret)).toString('hex')};
  assert.equal(verifyQQCallback(secret,headers,raw),true);
  assert.equal(verifyQQCallback(secret,headers,Buffer.from('{"op":1}')),false);
  assert.equal(verifyQQCallback(secret,headers,raw,Date.now()+600000),false);
});

test('QQ 长连接：认证、绑定隔离、需求幂等、指令与主动结果推送',async t=>{
  const f=await fixture(t),b=f.bridge,gateway=Gateway.instances.at(-1);
  gateway.onmessage({data:JSON.stringify({op:10,d:{heartbeat_interval:45000}})});await turn();
  assert.deepEqual(gateway.sent[0],{op:2,d:{token:'QQBot test-access-token',intents:1<<25,shard:[0,1]}});
  assert.equal(f.apiCalls[0].path,'/app/getAppAccessToken');
  assert.deepEqual(f.apiCalls[0].body,{appId:'12345678',clientSecret:secret});
  assert.equal(f.apiCalls.find(c=>c.path==='/gateway').headers.Authorization,'QQBot test-access-token');
  await b.receive(frame('unauthorized','帮我删文件'));assert.equal(f.localCalls.length,0);
  await b.receive(frame('wrong-pair','绑定 wrong'));assert.equal(b.status().pending.length,0);
  await b.receive(frame('pair','\u200b/绑定\n'+b.status().pairingCode.toUpperCase()));assert.equal(b.status().pending[0].openid,'owner');
  await b.bind('owner');assert.equal(b.status().owner,'owner');
  await b.receive(frame('stranger','进度','stranger'));assert.equal(f.localCalls.length,1);
  const message=frame('requirement1','给 LifeAgent 增加筛选功能');
  await b.receive(message);await b.receive(message);
  const submitted=f.localCalls.filter(c=>c.route==='messages');assert.equal(submitted.length,1);assert.equal(submitted[0].body.text,message.d.content);assert.match(submitted[0].body.id,/^qq-[a-f\d]{64}$/);
  await b.receive(frame('status','进度'));assert.equal(f.localCalls.at(-1).route,'state');
  await b.receive(frame('answer','回答 2 1'));assert.deepEqual(f.localCalls.at(-1),{route:'cards/2/answer',body:{choice:0}});
  await b.receive(frame('free-answer','回答 2 先完成基础测试'));assert.deepEqual(f.localCalls.at(-1).body,{text:'先完成基础测试'});
  await b.receive(frame('stop','停止 3'));assert.equal(f.localCalls.at(-1).route,'runs/3/cancel');
  const sendCount=f.apiCalls.filter(c=>c.path.includes('/messages')).length;
  await b.tick();assert.equal(f.apiCalls.filter(c=>c.path.includes('/messages')).length,sendCount+1);
  assert.match(f.apiCalls.at(-1).body.content,/待决定 #2/);
  await b.tick();assert.equal(f.apiCalls.filter(c=>c.path.includes('/messages')).length,sendCount+1);
  f.snapshot.runs.unshift({id:4,state:'done',rule:'LifeAgent 网页对话',summary:'筛选功能已完成'});
  await b.tick();assert.match(f.apiCalls.at(-1).body.content,/筛选功能已完成/);
  assert.ok(!JSON.stringify(b.status()).includes(secret));assert.ok(!JSON.stringify(b.status()).includes('test-access-token'));
  assert.equal(JSON.parse(await readFile(path.join(f.dir,'qq-config.json'),'utf8')).secret,secret);
  await f.restart();await f.bridge.receive(message);
  assert.equal(f.localCalls.filter(c=>c.route==='messages').length,1);
});

test('QQ Webhook：初始挑战、签名校验、回调去重与本机确认绑定',async t=>{
  const f=await fixture(t,'webhook'),b=f.bridge;
  const base=`http://127.0.0.1:${b.status().callbackPort}/qq/webhook`;
  const post=async(value,signed=true)=>{
    const raw=JSON.stringify(value),ts=String(Math.floor(Date.now()/1000));
    return fetch(base,{method:'POST',headers:{'Content-Type':'application/json','X-Bot-Appid':'12345678',
      ...(signed?{'X-Signature-Timestamp':ts,'X-Signature-Ed25519':sign(null,Buffer.from(ts+raw),qqSigningKey(secret)).toString('hex')}:{})},body:raw});
  };
  const challenge={op:13,d:{plain_token:'test-challenge',event_ts:'1725442341'}};
  const reply=await (await post(challenge,false)).json();assert.equal(reply.plain_token,'test-challenge');
  assert.equal(reply.signature,sign(null,Buffer.from('1725442341test-challenge'),qqSigningKey(secret)).toString('hex'));
  assert.equal((await post(frame('unsigned','随便执行'),false)).status,401);
  const pair=frame('webhook-pair','绑定 '+b.status().pairingCode);
  assert.equal((await post(pair)).status,200);await turn();await b.bind('owner');
  const req=frame('webhook-task','阅读项目进度，不修改代码');
  assert.deepEqual(await (await post(req)).json(),{op:12});await turn();
  assert.equal((await post(req)).status,200);await turn();
  assert.equal(f.localCalls.filter(c=>c.route==='messages').length,1);
  await b.disable(true);assert.equal(b.status().owner,null);assert.equal(b.status().enabled,false);
});

test('QQ 访问凭证 HTTP 200 业务失败也不得当成认证成功',async t=>{
  const dir=await mkdtemp(path.join(os.tmpdir(),'autoloop-qq-auth-'));
  const b=await createQQBridge({dataDir:dir,local:async()=>({}),Socket:Gateway,
    fetchImpl:async()=>new Response(JSON.stringify({code:100016,message:'invalid'})),pollMs:600000});
  t.after(async()=>{await b.stop();await rm(dir,{recursive:true,force:true});});
  await b.configure({appId:'12345678',secret,transport:'websocket'});await turn();
  assert.match(b.status().lastError,/100016/);assert.notEqual(b.status().connection,'QQ 已连接');
});

test('未绑定时服务重启保留口令，正确口令有确认回复但不执行需求',async t=>{
  const f=await fixture(t),code=f.bridge.status().pairingCode;
  await f.restart();assert.equal(f.bridge.status().pairingCode,code);
  await f.bridge.receive(frame('pair-after-restart','绑定 '+code));
  assert.equal(f.bridge.status().pending.length,1);
  assert.match(f.apiCalls.at(-1).body.content,/确认这是我的账号/);
  assert.equal(f.localCalls.length,0);
});
