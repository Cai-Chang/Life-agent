import http from 'node:http';
import path from 'node:path';
import {readFile, writeFile, rename} from 'node:fs/promises';
import {createHash, randomBytes, createPrivateKey, createPublicKey, sign, verify} from 'node:crypto';

const fail = (status, message) => Object.assign(new Error(message), {status});
const done = state => ['done','nothing','cancelled'].includes(state);
const matchesPairing = (text, code) => /^\/?绑定\s*([a-f\d]{8})$/i.exec(text.normalize('NFKC').replace(/[\u200B-\u200D\uFEFF]/g,'').trim())?.[1].toLowerCase() === code;
export function qqSigningKey(secret) {
  if (!secret) throw new Error('缺少机器人密钥');
  let seed = Buffer.from(secret);
  while (seed.length < 32) seed = Buffer.concat([seed,seed]);
  return createPrivateKey({key:Buffer.concat([Buffer.from('302e020100300506032b657004220420','hex'),seed.subarray(0,32)]),format:'der',type:'pkcs8'});
}
export function verifyQQCallback(secret, headers, raw, now = Date.now()) {
  const ts = headers['x-signature-timestamp'], signature = headers['x-signature-ed25519'];
  if (!/^\d{10,13}$/.test(ts || '') || !/^[a-f\d]{128}$/i.test(signature || '')) return false;
  if (Math.abs(now/1000 - Number(ts)) > 300) return false;
  return verify(null,Buffer.concat([Buffer.from(ts),raw]),createPublicKey(qqSigningKey(secret)),Buffer.from(signature,'hex'));
}
export function cardText(c) {
  return [`${c.kind === 'ask' ? '待决定' : '通知'} #${c.id}：${c.title}`,c.text,
    ...(c.kind === 'ask' ? c.options.map((v,i)=>`${i+1}. ${v}`) : []),
    c.kind === 'ask' ? `回复：回答 ${c.id} 1\n自定义回答：回答 ${c.id} 你的具体意见` : `回复：已查看 ${c.id}`].join('\n');
}
export function formatStatus(s) {
  const runs=s.runs.slice(0,5);
  const labels={claimed:'进行中',queued:'排队 / 等待重试',done:'本轮结束',nothing:'无需处理',cancelled:'已停止',unknown:'待确认'};
  return ['LifeAgent 任务进度',...runs.map(r=>`#${r.id} ${labels[r.state] || r.state} · ${r.rule}\n${r.summary || r.error || '等待后台结果'}`),
    ...s.cards.map(cardText),'“本轮结束”不代表整个项目已完成。'].join('\n\n');
}

export async function createQQBridge({dataDir, local, apiBase='https://api.bot.qq.com', fetchImpl=fetch, Socket=WebSocket, callbackPort=3367, pollMs=5000}) {
  const configFile=path.join(dataDir,'qq-config.json'), stateFile=path.join(dataDir,'qq-state.json');
  let config={}, store={seen:{},notifications:{},pending:[]};
  for (const [file,assign] of [[configFile,v=>config=v],[stateFile,v=>store=v]]) {
    try { assign(JSON.parse(await readFile(file,'utf8'))); } catch(e) { if(e.code!=='ENOENT')throw e; }
  }
  let writeQueue=Promise.resolve(), inbound=Promise.resolve(), stopping=true, generation=0;
  let socket, heartbeat, reconnect, polling, callback, token, tokenExpiry=0, tokenPromise;
  let seq=null, session=null, heartbeatAck=true, pollBusy=false, nextPushAt=0;
  let connection='未配置', lastError='', deliveryError='', lastReceivedAt=null, lastSentAt=null, verifiedAt=null;
  let pairingCode=store.pairingCode||randomBytes(4).toString('hex');
  store.pairingCode=pairingCode;
  let bindingHint='';
  function atomic(file,value) {
    const text=JSON.stringify(value,null,2)+'\n';
    const operation=writeQueue.then(async()=>{await writeFile(file+'.tmp',text,{mode:0o600});await rename(file+'.tmp',file);});
    writeQueue=operation.catch(()=>{});return operation;
  }
  const save=()=>atomic(stateFile,store);
  function status() {
    return {configured:!!(config.appId&&config.secret),enabled:!!config.enabled,appId:config.appId||'',hasSecret:!!config.secret,
      transport:config.transport||'websocket',connection,lastError,deliveryError,lastReceivedAt,lastSentAt,verifiedAt,
      owner:config.owner||null,pending:store.pending||[],pairingCode:config.enabled&&!config.owner?pairingCode:null,bindingHint,
      callbackPath:'/qq/webhook',callbackPort:callback?.address()?.port ?? callbackPort};
  }
  function report(e) { lastError=e.status?e.message:'QQ 连接或本地服务异常，请检查网络与平台配置'; }
  async function getToken() {
    if(token && Date.now()<tokenExpiry-60000)return token;
    if(tokenPromise)return tokenPromise;
    const current=generation;
    tokenPromise=(async()=>{
      const response=await fetchImpl(new URL('/app/getAppAccessToken',apiBase),{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({appId:config.appId,clientSecret:config.secret}),signal:AbortSignal.timeout(12000)});
      const data=await response.json();
      if(!response.ok||data.code&&Number(data.code)!==0||!data.access_token)throw fail(502,`QQ 凭据验证失败（${data.code || response.status}），请检查 AppID、AppSecret 和机器人状态`);
      if(current!==generation)throw fail(409,'QQ 配置已变更，请重试');
      token=data.access_token;tokenExpiry=Date.now()+Number(data.expires_in||7200)*1000;return token;
    })();
    try{return await tokenPromise;}finally{tokenPromise=null;}
  }
  async function qq(route,body) {
    const access=await getToken();
    const response=await fetchImpl(new URL(route,apiBase),{method:body===undefined?'GET':'POST',headers:{Authorization:`QQBot ${access}`,'Content-Type':'application/json'},
      ...(body===undefined?{}:{body:JSON.stringify(body)}),signal:AbortSignal.timeout(12000)});
    const data=await response.json();const code=Number(data.err_code || data.code || 0);
    if(!response.ok||code) { if(response.status===401){token=null;tokenExpiry=0;}throw fail(502,`QQ API 请求失败（${code||response.status}）；请检查接口权限、IP 白名单及主动消息开关`); }
    return data;
  }
  async function send(user,text,msgId,pairing=false) {
    const permitted=user===config.owner || pairing&&!config.owner&&store.pending.some(p=>p.openid===user);
    if(stopping || !config.enabled || !permitted)throw fail(409,'QQ 接入已停用或绑定账号已改变');
    // One bounded text reply avoids exhausting the platform's per-message reply count.
    const content=text.length>1700?text.slice(0,1650)+'\n…内容较长，请在本机网页查看完整结果。':text;
    const body={msg_type:0,content,...(msgId?{msg_id:msgId,msg_seq:1}:{})};
    const result=await qq(`/v2/users/${encodeURIComponent(user)}/messages`,body);
    if(!result.id)throw fail(502,'QQ 未确认消息送达，请检查平台返回与消息审核状态');
    lastSentAt=new Date().toISOString();return result;
  }
  async function command(text,message) {
    if(/^(帮助|菜单|help|\/help)$/i.test(text))return 'Autoloop · LifeAgent\n进度：查看当前任务和审批\n任务：查看开发进度文档\n继续开发：按既有进度执行下一步\n回答 2 1：卡片2选择第1项\n回答 2 具体意见：自定义回复\n已查看 3：确认通知\n停止 8：停止第8轮\n其他文字：作为需求交给后台 Codex（使用模型额度）。';
    if(/^(进度|状态|查看进度|查看任务进度)$/.test(text))return formatStatus(await local('state'));
    if(/^(任务|项目进度|开发记录)$/.test(text))return (await local('progress')).text;
    const answer=/^回答\s+(\d+)\s+([\s\S]+)$/.exec(text);
    if(answer) {
      const value=answer[2].trim();
      await local(`cards/${answer[1]}/answer`,/^\d+$/.test(value)?{choice:Number(value)-1}:{text:value});
      return `已提交卡片 #${answer[1]} 的回答，Agent 会继续处理。`;
    }
    const resolve=/^已查看\s+(\d+)$/.exec(text);
    if(resolve) {await local(`cards/${resolve[1]}/resolve`,{});return `通知 #${resolve[1]} 已确认。`;}
    const stop=/^停止\s+(\d+)$/.exec(text);
    if(stop) {await local(`runs/${stop[1]}/cancel`,{});return `已请求停止第 ${stop[1]} 轮，已写入文件会保留。`;}
    if(text==='继续开发') {
      const s=await local('state');
      if(s.cards.some(c=>c.kind==='ask'))return '还有待确认问题，请先回复对应卡片。\n\n'+s.cards.filter(c=>c.kind==='ask').map(cardText).join('\n\n');
    }
    if(text.length>3500)return '消息太长，请拆分为不超过 3500 字的需求。';
    const id='qq-'+createHash('sha256').update(config.appId+':'+message.id).digest('hex');
    await local('messages',{id,text:text==='继续开发'?'请按照项目当前开发进度，继续下一个未完成的可验收小任务。':text});
    return '需求已交给后台 Codex，结束后会在这里推送结果。发“进度”可随时查看。';
  }
  async function processMessage(frame) {
    if(stopping||frame.op!==0||frame.t!=='C2C_MESSAGE_CREATE')return;
    const d=frame.d||{}, user=d.author?.user_openid;
    if(typeof user!=='string'||!user||d.author?.bot||typeof d.id!=='string'||typeof d.content!=='string')return;
    lastReceivedAt=new Date().toISOString();const text=d.content.trim();
    if(!config.owner) {
      if(!matchesPairing(text,pairingCode)) { bindingHint='QQ 消息已收到，但不是当前绑定口令。请复制本机显示的完整口令发送。';return; }
      bindingHint='绑定口令已匹配，请在本机确认下面的账号。';
      store.pending=[{openid:user,name:String(d.author.username||'QQ 用户').slice(0,80),receivedAt:lastReceivedAt}];
      await save();
      if(store.pairingAck!==d.id){await send(user,'绑定口令已收到。请回到电脑上的 QQ 接入页面，点击“确认这是我的账号”，确认后即可发“进度”查看任务。',d.id,true);store.pairingAck=d.id;await save();}
      return;
    }
    if(user!==config.owner)return;
    const key=createHash('sha256').update(config.appId+':'+d.id).digest('hex');
    let record=store.seen[key];
    if(!record) {
      try { record={response:await command(text,d),sent:false}; }
      catch(e) { record={response:e.status?e.message:'本地操作暂未完成，请查询进度后重试。',sent:false}; }
      store.seen[key]=record;
      if(Object.keys(store.seen).length>2000)delete store.seen[Object.keys(store.seen)[0]];
      await save();
    }
    if(!record.sent) {
      // Old gateway replays may arrive outside the conservative passive reply window.
      const recent=Number.isFinite(Date.parse(d.timestamp))&&Date.now()-Date.parse(d.timestamp)<4*60000;
      await send(user,record.response,recent?d.id:undefined);record.sent=true;await save();
    }
  }
  function receive(frame) {
    const action=inbound.then(()=>processMessage(frame));
    inbound=action.catch(report);return action;
  }
  async function tick() {
    if(stopping||!config.owner||pollBusy||Date.now()<nextPushAt)return;
    pollBusy=true;
    try {
      const s=await local('state'), entries=[];
      for(const c of s.cards) {
        const key=`card:${c.id}:${c.version}`;
        if(!store.notifications[key])entries.push([key,cardText(c)]);
      }
      for(const r of s.runs) {
        const key=`run:${r.id}`;
        if(done(r.state)&&!store.notifications[key])entries.push([key,`任务 #${r.id} · ${r.rule}\n${r.summary||r.error||'本轮已结束'}`]);
      }
      if(entries.length) {
        // Deliver one item per poll, keeping results readable and below rate limits.
        const [key,text]=entries[0];await send(config.owner,text);store.notifications[key]=true;await save();
      }
      deliveryError='';nextPushAt=0;
    } catch(e) {deliveryError=e.status?e.message:'结果推送暂不可用；可在 QQ 发“进度”主动查询';nextPushAt=Date.now()+60000;}
    finally{pollBusy=false;}
  }
  function scheduleReconnect(current) {
    clearInterval(heartbeat);if(stopping||current!==generation)return;
    connection='等待重连';clearTimeout(reconnect);
    reconnect=setTimeout(()=>connect(current).catch(e=>{report(e);scheduleReconnect(current);}),10000);reconnect.unref?.();
  }
  async function connect(current) {
    const gateway=await qq('/gateway');
    if(stopping||current!==generation)return;
    if(typeof gateway.url!=='string'||!gateway.url.startsWith('wss://'))throw fail(502,'QQ 未提供可用的长连接地址，请核对平台是否开放 WebSocket');
    socket=new Socket(gateway.url);const ws=socket;
    connection='正在连接 QQ';
    ws.onmessage=event=>{
      if(current!==generation||stopping)return;
      let frame;try{frame=JSON.parse(String(event.data));}catch{return;}
      if(frame.op===10) {
        heartbeatAck=true;
        const interval=Number(frame.d?.heartbeat_interval);
        if(!Number.isFinite(interval)||interval<1000){ws.close();return;}
        getToken().then(access=>{
          if(current!==generation||ws.readyState!==1)return;
          ws.send(JSON.stringify(session?{op:6,d:{token:`QQBot ${access}`,session_id:session,seq}}:
            {op:2,d:{token:`QQBot ${access}`,intents:1<<25,shard:[0,1]}}));
        }).catch(e=>{report(e);ws.close();});
        clearInterval(heartbeat);heartbeat=setInterval(()=>{
          if(ws.readyState!==1)return;
          if(!heartbeatAck){ws.close();return;}
          heartbeatAck=false;ws.send(JSON.stringify({op:1,d:seq}));
        },interval);heartbeat.unref?.();
      } else if(frame.op===11) heartbeatAck=true;
      else if(frame.op===1&&ws.readyState===1)ws.send(JSON.stringify({op:1,d:seq}));
      else if(frame.op===7)ws.close();
      else if(frame.op===9){session=null;seq=null;ws.close();}
      else if(frame.op===0) {
        if(frame.t==='READY'){session=frame.d?.session_id;connection='QQ 已连接';lastError='';verifiedAt=new Date().toISOString();}
        if(frame.t==='RESUMED'){connection='QQ 已连接';lastError='';}
        receive(frame).then(()=>{if(current===generation&&frame.s!==undefined)seq=frame.s;}).catch(report);
      }
    };
    ws.onerror=()=>{lastError='QQ 长连接失败，请检查网络、IP 白名单和接入权限';};
    ws.onclose=event=>{
      if(current!==generation)return;
      if([4006,4007].includes(event.code)){session=null;seq=null;}
      if([4001,4002,4010,4011,4012,4013,4014,4914,4915].includes(event.code)){
        clearInterval(heartbeat);connection='需要处理';lastError=`QQ 网关拒绝连接（${event.code}），请检查订阅权限、机器人状态和环境`;return;
      }
      scheduleReconnect(current);
    };
  }
  async function callbackHandler(req,res) {
    const answer=(code,value)=>{res.writeHead(code,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
    try {
      if(req.method!=='POST'||req.url!=='/qq/webhook')return answer(404,{error:'not found'});
      if(!config.enabled||config.transport!=='webhook')return answer(503,{error:'disabled'});
      const chunks=[];let size=0;
      for await(const chunk of req){size+=chunk.length;if(size>100000)return answer(413,{error:'too large'});chunks.push(chunk);}
      const raw=Buffer.concat(chunks);
      const frame=JSON.parse(raw.toString('utf8'));
      if(req.headers['x-bot-appid']!==config.appId)return answer(401,{error:'invalid app'});
      if(frame.op===13) {
        const {plain_token,event_ts}=frame.d||{};
        // The platform's initial challenge may be unsigned. It can only request
        // a challenge proof; it must never dispatch messages or change bindings.
        if(typeof plain_token!=='string'||plain_token.length>512||!/^\d{10}$/.test(event_ts||''))return answer(400,{error:'invalid challenge'});
        if(req.headers['x-signature-ed25519']&&!verifyQQCallback(config.secret,req.headers,raw))return answer(401,{error:'invalid signature'});
        return answer(200,{plain_token,signature:sign(null,Buffer.from(event_ts+plain_token),qqSigningKey(config.secret)).toString('hex')});
      }
      if(!verifyQQCallback(config.secret,req.headers,raw))return answer(401,{error:'invalid signature'});
      verifiedAt=new Date().toISOString();connection='Webhook 已收到签名请求';lastError='';
      if(frame.op===0&&frame.t==='C2C_MESSAGE_CREATE') {
        const d=frame.d||{};
        if(typeof d.id!=='string'||typeof d.content!=='string'||!d.author?.user_openid)return answer(400,{error:'invalid message'});
        const owner=d.author.user_openid===config.owner;
        const pairing=!config.owner&&matchesPairing(d.content,pairingCode);
        if(owner||pairing) {
          const key=createHash('sha256').update(d.id).digest('hex');
          store.inbox??={};
          if(Object.keys(store.inbox).length>=200&&!store.inbox[key])return answer(503,{error:'inbox full'});
          // Persist before ACK; only retain fields needed for this text adapter.
          store.inbox[key]={op:0,t:frame.t,d:{id:d.id,content:d.content,timestamp:d.timestamp,
            author:{user_openid:d.author.user_openid,username:d.author.username,bot:d.author.bot}}};
          await save();
          const accepted=store.inbox[key], acceptedGeneration=generation;
          setImmediate(()=>receive(accepted).then(async()=>{
            if(acceptedGeneration===generation&&!stopping){delete store.inbox[key];await save();}
          }).catch(report));
        }
      }
      return answer(200,{op:12});
    } catch(e) {report(e);answer(500,{error:'callback not completed'});}
  }
  async function stop() {
    stopping=true;generation++;clearInterval(heartbeat);clearTimeout(reconnect);clearInterval(polling);
    socket?.close();socket=null;session=null;seq=null;
    if(callback){const old=callback;callback=null;await new Promise(r=>old.close(r));}
    connection=config.appId?'已停用':'未配置';
  }
  async function start() {
    await stop();token=null;tokenExpiry=0;
    if(!config.enabled||!config.appId||!config.secret)return;
    stopping=false;const current=generation;
    polling=setInterval(()=>tick().catch(report),pollMs);polling.unref?.();
    if(config.transport==='webhook') {
      callback=http.createServer(callbackHandler);callback.on('error',()=>{connection='需要处理';lastError='QQ 回调端口无法启动，请检查 3367 端口占用';});
      await new Promise((resolve,reject)=>{callback.once('error',reject);callback.listen(callbackPort,'127.0.0.1',resolve);});
      connection='等待 HTTPS 回调配置';
      getToken().catch(report);
    } else connect(current).catch(e=>{report(e);scheduleReconnect(current);});
    for(const [key,frame] of Object.entries(store.inbox||{})) {
      receive(frame).then(async()=>{if(current===generation&&!stopping){delete store.inbox[key];await save();}}).catch(report);
    }
  }
  async function configure(body) {
    const appId=String(body.appId||'').trim(), transport=body.transport||'websocket';
    if(!/^\d{4,30}$/.test(appId))throw fail(400,'请输入 QQ 开放平台的 AppID');
    if(!['websocket','webhook'].includes(transport))throw fail(400,'请选择 WebSocket 或 Webhook');
    const changed=appId!==config.appId;
    const secret=String(body.secret||'').trim()||(!changed?config.secret:'');
    if(!secret||secret.length>256||!/^[\x21-\x7e]+$/.test(secret))throw fail(400,'请填写有效的 AppSecret');
    await stop();
    if(changed){pairingCode=randomBytes(4).toString('hex');store={seen:{},notifications:{},pending:[],pairingCode};await save();}
    config={appId,secret,transport,enabled:true,owner:changed?null:config.owner||null};
    await atomic(configFile,config);await start();return status();
  }
  async function bind(openid) {
    if(config.owner)throw fail(409,'已绑定账号；如需更换请先解除绑定');
    if(!store.pending.some(p=>p.openid===openid&&Date.now()-Date.parse(p.receivedAt)<600000))throw fail(400,'绑定请求不存在或已过期，请重新发送绑定口令');
    // Seed old completed runs so enabling QQ does not resend the entire history.
    const s=await local('state');for(const r of s.runs)if(done(r.state))store.notifications[`run:${r.id}`]=true;
    config.owner=openid;store.pending=[];pairingCode=randomBytes(4).toString('hex');store.pairingCode=pairingCode;bindingHint='';await atomic(configFile,config);await save();
    return status();
  }
  async function disable(unbind=false) {
    await stop();config.enabled=false;
    if(unbind){config.owner=null;store.pending=[];pairingCode=randomBytes(4).toString('hex');store.pairingCode=pairingCode;bindingHint='';await save();}
    await atomic(configFile,config);return status();
  }
  return {start,stop,status,configure,bind,disable,receive,tick,callbackHandler};
}
