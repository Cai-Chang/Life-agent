const $ = id => document.getElementById(id);
let csrf, state, busy = false, refreshing = false, stopId, conversationSignature = '';
let retryMessage;
let qqStatus;
const names = {claimed:'进行中',queued:'排队中',done:'本轮结束',nothing:'无需处理',cancelled:'已停止',unknown:'状态待确认'};
function el(tag, text, cls) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }
function error(message) { $('error').textContent = message || ''; $('error').hidden = !message; }
async function api(route, body) {
  const res = await fetch('/api/' + route, {cache:'no-store', ...(body !== undefined ? {method:'POST',headers:{'Content-Type':'application/json','X-Local-CSRF':csrf},body:JSON.stringify(body)} : {}), signal:AbortSignal.timeout(30000)});
  const data = await res.json(); if (!res.ok) throw new Error(data.error || '操作失败'); return data;
}
function time(value) { return value ? new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) : ''; }
async function act(button, route, body) {
  button.disabled = true; error('');
  try { await api(route,body); await refresh(); } catch(e) { error(e.message); } finally { button.disabled = false; }
}
function renderState(s) {
  state = s;
  const active = s.runs.filter(r => ['claimed','queued'].includes(r.state));
  $('running').textContent = active.length;
  $('waiting').textContent = s.cards.filter(c => c.kind === 'ask').length;
  $('done').textContent = s.runs.filter(r => ['done','nothing'].includes(r.state)).length;
  $('connection').textContent = '中台已连接'; $('connection').className = 'connection';
  $('agent-status').textContent = s.agents.some(a => a.online) ? 'Codex 在线 · 可接收任务' : 'Codex 离线 · 新任务将等待接单';
  $('updated').textContent = new Date().toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'});
  $('card-count').textContent = s.cards.length;
  // Keep in-progress free-text answers intact across automatic refreshes.
  const signature = JSON.stringify(s.cards);
  if ($('cards').dataset.signature !== signature) {
    $('cards').dataset.signature = signature; $('cards').replaceChildren();
    if (!s.cards.length) $('cards').append(el('p','暂时没有需要你处理的事项。','empty'));
    for (const c of s.cards) {
      const item = el('article',undefined,'approval'); item.append(el('h3',c.title),el('p',c.text));
      if (c.kind === 'ask') {
        c.options.forEach((option,i) => { const b = el('button',option); b.onclick = () => act(b,`cards/${c.id}/answer`,{choice:i}); item.append(b); });
        const form = el('form'), input = el('input'); input.placeholder = '或填写你的具体想法'; input.maxLength = 3500; input.required = true; input.setAttribute('aria-label',`${c.title}：自定义回答`);
        const b = el('button','提交回答'); b.type = 'submit'; form.append(input,b); form.onsubmit = e => { e.preventDefault(); act(b,`cards/${c.id}/answer`,{text:input.value}); }; item.append(form);
      } else { const b = el('button','已查看'); b.onclick = () => act(b,`cards/${c.id}/resolve`,{}); item.append(b); }
      $('cards').append(item);
    }
  }
  $('runs').replaceChildren();
  if (!s.runs.length) $('runs').append(el('p','还没有项目任务。发一条消息开始。','empty'));
  for (const r of s.runs.slice(0,6)) {
    const item = el('article',undefined,'run'), row = el('div',undefined,'run-top');
    row.append(el('strong',`#${r.id} ${r.rule}`),el('span',r.stopping ? '停止中' : names[r.state] || r.state,'status'));
    item.append(row,el('p',r.summary || r.error || 'Agent 正在处理，完成后会更新结果。'),el('small',time(r.finishedAt || r.createdAt)));
    if (['claimed','queued'].includes(r.state)) { const b = el('button','停止此任务','stop'); b.onclick = () => { stopId = r.id; $('stop-dialog').showModal(); }; item.append(b); }
    $('runs').append(item);
  }
  $('continue').disabled = !!active.length || s.cards.some(c => c.kind === 'ask');
  $('continue').title = $('continue').disabled ? '先等待任务结束或回答待确认卡片' : '按开发进度推进下一个任务';
}
function addMessage(who, text, meta) {
  const node = el('article',undefined,`message ${who === '你' ? 'user' : 'agent'}`);
  node.append(el('div',who,'message-label'),el('div',text,'bubble'));
  if (meta) node.append(el('div',meta,'message-meta')); $('chat').append(node);
}
function renderMessages(items) {
  const followups = (state?.runs || []).filter(r => r.rule === 'LifeAgent 网页对话' && r.events?.some(e => e.type === 'card.answered'));
  const signature = JSON.stringify([items,followups]);
  if (signature === conversationSignature) return;
  conversationSignature = signature;
  if (!items.length) return;
  const chat = $('chat'), nearBottom = chat.scrollHeight-chat.scrollTop-chat.clientHeight < 100;
  chat.replaceChildren(); const shown = new Set();
  for (const m of items) {
    addMessage('你',m.text,`${m.origin === 'qq' ? '来自 QQ · ' : ''}${time(m.createdAt)}`);
    if (!m.event) { addMessage('本地工作台','消息已保存在本机，尚未成功交给中台。请用相同消息重试发送。'); continue; }
    const runs = m.progress?.runs || [];
    let hasResult = false;
    for (const r of runs) {
      if (shown.has(r.run)) continue;
      shown.add(r.run);
      if (['done','nothing','cancelled'].includes(r.state)) {
        addMessage('Agent',r.summary || r.error || '本轮已结束，请查看项目记录。',`#${r.run} · ${names[r.state] || r.state} · ${time(r.finishedAt)}`); hasResult = true;
      } else { addMessage('Agent',r.error ? `遇到问题，等待重试：${r.error}` : '已收到，正在后台处理。你可以离开页面，稍后回来查看。',`#${r.run} · ${names[r.state] || r.state}`); hasResult = true; }
    }
    if (!runs.length && !hasResult) addMessage('本地工作台','需求已提交，等待 Agent 接单。');
  }
  for (const r of followups.slice().reverse()) {
    if (!shown.has(r.id)) addMessage('Agent',r.summary || r.error || '已收到你的卡片回答，正在继续处理。',`#${r.id} · ${names[r.state] || r.state} · ${time(r.finishedAt || r.createdAt)}`);
  }
  if (nearBottom || items.length === 1) chat.scrollTop = chat.scrollHeight;
}
async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
    const [s,m,p] = await Promise.all([api('state'),api('messages'),api('progress')]);
    renderState(s); renderMessages(m); $('progress').textContent = p.text;
    if ($('qq-dialog').open) await refreshQQ();
  } catch(e) { $('connection').textContent = '连接暂不可用'; $('connection').className = 'connection offline'; error(e.message); }
  finally { refreshing = false; }
}
$('composer').onsubmit = async e => {
  e.preventDefault(); if (busy) return;
  const text = $('message').value.trim(); if (!text) return;
  busy = true; $('send').disabled = true; $('send').textContent = '正在提交'; error('');
  if (!retryMessage || retryMessage.text !== text) retryMessage = {id:crypto.randomUUID(),text};
  try { await api('messages',retryMessage); $('message').value = ''; retryMessage = undefined; await refresh(); $('chat').scrollTop = $('chat').scrollHeight; }
  catch(e) { error(e.message + '。消息保留在输入框中，可重试。'); }
  finally { busy = false; $('send').disabled = false; $('send').textContent = '发送消息'; }
};
$('message').onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('composer').requestSubmit(); } };
document.querySelectorAll('[data-suggestion]').forEach(b => b.onclick = () => { $('message').value = b.dataset.suggestion; $('message').focus(); });
$('refresh').onclick = async () => { error(''); await refresh(); };
$('continue').onclick = () => act($('continue'),'continue',{});
$('dismiss-stop').onclick = () => $('stop-dialog').close();
$('confirm-stop').onclick = async () => { $('stop-dialog').close(); await act($('confirm-stop'),`runs/${stopId}/cancel`,{}); };
function qqError(message) { $('qq-error').textContent=message||''; $('qq-error').hidden=!message; }
function transportHelp() {
  const webhook=$('qq-transport').value==='webhook';
  $('qq-transport-help').textContent=webhook?'Webhook 需要可达的 HTTPS 回调地址；本地代码已准备好，转发地址还需另行配置。':'WebSocket 由这台 Mac 主动连接 QQ，通常不需要公网回调地址。请确认机器人控制台提供此方式。';
  $('qq-webhook-help').hidden=!webhook;
}
async function refreshQQ(fill=false) {
  qqStatus=await api('qq/status'); const s=qqStatus;
  $('qq-status').textContent=[s.connection,s.lastError,s.deliveryError].filter(Boolean).join(' · ');
  $('qq-disable').disabled=!s.enabled; $('qq-unbind').disabled=!s.owner;
  $('qq-pairing').hidden=!(s.enabled&&!s.owner); $('qq-bound').hidden=!s.owner;
  $('qq-owner').textContent=s.owner||''; $('qq-code').textContent=s.pairingCode?`绑定 ${s.pairingCode}`:'';
  $('qq-binding-hint').textContent=s.bindingHint||'';
  $('qq-pending').replaceChildren();
  for(const p of s.pending) {
    const item=el('div',undefined,'pending-account');item.append(el('strong',p.name),el('p',`OpenID：${p.openid}`));
    const b=el('button','确认这是我的账号','primary');b.onclick=async()=>{
      b.disabled=true;qqError('');try{await api('qq/bind',{openid:p.openid});await refreshQQ();}catch(e){qqError(e.message);}finally{b.disabled=false;}
    };item.append(b);$('qq-pending').append(item);
  }
  if(fill){$('qq-appid').value=s.appId; $('qq-transport').value=s.transport;$('qq-secret').value='';$('qq-secret').placeholder=s.hasSecret?'已保存，留空保持不变':'仅保存到这台电脑，不在页面回显';transportHelp();}
}
$('qq-open').onclick=async()=>{$('qq-dialog').showModal();qqError('');try{await refreshQQ(true);}catch(e){qqError(e.message);}};
$('qq-close').onclick=()=>$('qq-dialog').close();
$('qq-transport').onchange=transportHelp;
$('qq-copy').onclick=async()=>{try{await navigator.clipboard.writeText($('qq-code').textContent);$('qq-copy').textContent='已复制';setTimeout(()=>$('qq-copy').textContent='复制绑定口令',2000);}catch{$('qq-binding-hint').textContent='请选中上面的口令文字后手动复制。';}};
$('qq-form').onsubmit=async e=>{
  e.preventDefault();$('qq-save').disabled=true;qqError('');
  try{await api('qq/config',{appId:$('qq-appid').value,secret:$('qq-secret').value,transport:$('qq-transport').value});$('qq-secret').value='';await refreshQQ(true);}
  catch(e){qqError(e.message);}finally{$('qq-save').disabled=false;}
};
for(const [id,unbind] of [['qq-disable',false],['qq-unbind',true]]) $(id).onclick=async()=>{
  $(id).disabled=true;qqError('');try{await api('qq/disable',{unbind});await refreshQQ(true);}catch(e){qqError(e.message);}finally{$(id).disabled=false;}
};
try { ({csrf} = await api('session')); await refresh(); setInterval(refresh,4000); if(new URLSearchParams(location.search).get('settings')==='qq')$('qq-open').click(); }
catch(e) { error(e.message); }
