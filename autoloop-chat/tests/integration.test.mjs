import {test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {mkdtemp,writeFile,mkdir,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createApp,CHAT_RULE} from '../server.mjs';

test('真实 HTTP：消息去重、状态、审批、访问边界与重启历史', async t => {
  const dir = await mkdtemp(path.join(os.tmpdir(),'autoloop-chat-test-'));
  const received = [];
  const snapshot = {runs:[{id:8,rule:CHAT_RULE,state:'done',summary:'测试回复'}],
    cards:[{id:4,rule:CHAT_RULE,kind:'ask',options:['继续','暂停']}],recentCards:[],
    lines:[{name:CHAT_RULE}],agents:[],elsewhere:[],unrouted:[]};
  const fakeHub = http.createServer(async (req,res) => {
    let text=''; for await (const chunk of req) text+=chunk;
    received.push({path:req.url,auth:req.headers.authorization,body:text && JSON.parse(text)});
    res.setHeader('Content-Type','application/json');
    if (req.url === '/v1/state') return res.end(JSON.stringify(snapshot));
    if (req.url === '/v1/events' && req.method === 'POST') return res.end(JSON.stringify({event:42,routed:[CHAT_RULE]}));
    if (req.url === '/v1/events/42') return res.end(JSON.stringify({runs:[{run:8,state:'done',summary:'测试回复'}]}));
    res.end('{"ok":true}');
  });
  await new Promise(r=>fakeHub.listen(0,'127.0.0.1',r));
  const configPath=path.join(dir,'config.json');
  await writeFile(configPath,JSON.stringify({url:`http://127.0.0.1:${fakeHub.address().port}`,owner:'owner-secret',source:{key:'source-secret'}}));
  await mkdir(path.join(dir,'docs'));
  await writeFile(path.join(dir,'docs/development-status.md'),'DEV-01 尚未完成');
  const options={configPath,dataDir:path.join(dir,'data'),projectDir:dir};
  let app = await createApp(options);
  await new Promise(r=>app.listen(0,'127.0.0.1',r));
  let base=`http://127.0.0.1:${app.address().port}`;
  t.after(async()=>{await new Promise(r=>app.close(r));await new Promise(r=>fakeHub.close(r));await rm(dir,{recursive:true,force:true});});
  const session=await (await fetch(base+'/api/session')).json();
  const post=(url,body,headers={})=>fetch(base+url,{method:'POST',headers:{'Content-Type':'application/json','X-Local-CSRF':session.csrf,...headers},body:JSON.stringify(body)});
  await t.test('无 CSRF、跨站与伪造 Host 均被拒绝',async()=>{
    assert.equal((await fetch(base+'/api/continue',{method:'POST'})).status,403);
    assert.equal((await post('/api/continue',{}, {Origin:'https://example.com'})).status,403);
    const hostStatus = await new Promise((resolve,reject) => {
      http.get(base+'/api/state',{headers:{Host:'evil.example'}},res=>{res.resume();resolve(res.statusCode);}).on('error',reject);
    });
    assert.equal(hostStatus,403);
    assert.equal((await fetch(base+'/server.mjs')).status,404);
  });
  await t.test('重复提交只派发一次，正文原样保存，不执行脚本',async()=>{
    const body={id:'test-message-123456',text:'<script>alert(1)</script> 讨论需求'};
    assert.equal((await post('/api/messages',body)).status,200);
    assert.equal((await post('/api/messages',body)).status,200);
    assert.equal(received.filter(r=>r.path==='/v1/events').length,1);
    assert.equal(received.find(r=>r.path==='/v1/events').auth,'Bearer source-secret');
    assert.equal((await post('/api/messages',{...body,text:'不同内容'})).status,409);
    const messages=await (await fetch(base+'/api/messages')).json();
    assert.equal(messages[0].text,body.text); assert.equal(messages[0].progress.runs[0].summary,'测试回复');
  });
  await t.test('卡片范围、序号校验与回答转发；待审批时不重复启动开发',async()=>{
    assert.equal((await post('/api/cards/9/answer',{choice:0})).status,409);
    assert.equal((await post('/api/cards/4/answer',{choice:9})).status,400);
    assert.equal((await post('/api/cards/4/answer',{choice:1})).status,200);
    assert.deepEqual(received.find(r=>r.path==='/v1/cards/4/answer').body,{choice:1});
    assert.equal((await post('/api/continue',{})).status,409);
    const state=await (await fetch(base+'/api/state')).text();
    assert.ok(!state.includes('owner-secret') && !state.includes('source-secret'));
    assert.equal((await (await fetch(base+'/api/progress')).json()).text,'DEV-01 尚未完成');
  });
  await t.test('服务重启后消息与事件编号仍可恢复',async()=>{
    await new Promise(r=>app.close(r)); app=await createApp(options);
    await new Promise(r=>app.listen(0,'127.0.0.1',r)); base=`http://127.0.0.1:${app.address().port}`;
    const messages=await (await fetch(base+'/api/messages')).json();assert.equal(messages[0].event,42);
  });
});
