import http from 'node:http';
import {readFile, writeFile, mkdir, rename} from 'node:fs/promises';
import {randomBytes} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import os from 'node:os';
import {createQQBridge} from './qq-bridge.mjs';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
export const CHAT_RULE = 'LifeAgent 网页对话';
const allowedRule = rule => ['LifeAgent 开发', CHAT_RULE].includes(rule);
const fail = (status, message) => Object.assign(new Error(message), {status});

export async function createApp(options = {}) {
  const configPath = options.configPath ?? path.join(os.homedir(), '.agent-autoloop/config.json');
  const dataDir = options.dataDir ?? path.join(ROOT, '.local');
  const projectDir = options.projectDir ?? path.dirname(ROOT);
  await mkdir(dataDir, {recursive: true, mode: 0o700});
  const historyFile = path.join(dataDir, 'messages.json');
  let history;
  try { history = JSON.parse(await readFile(historyFile, 'utf8')); }
  catch (e) { if (e.code !== 'ENOENT') throw e; history = []; }
  const csrf = randomBytes(32).toString('hex');
  let queue = Promise.resolve();
  const persist = async () => {
    await writeFile(historyFile + '.tmp', JSON.stringify(history), {mode: 0o600});
    await rename(historyFile + '.tmp', historyFile);
  };
  async function hub(route, method = 'GET', body, source = false) {
    const config = JSON.parse(await readFile(configPath, 'utf8'));
    const key = source ? config.source?.key : config.owner;
    if (!key) throw fail(503, '本机中台凭据尚未配置');
    // Credentials stay in this process; the browser only receives business data.
    const base = new URL(config.url);
    if (!['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname)) throw fail(503, '此界面只连接本机中台');
    let response;
    try {
      response = await fetch(new URL(route, base), {
        method, headers: {Authorization: `Bearer ${key}`, 'Content-Type': 'application/json'},
        ...(body !== undefined ? {body: JSON.stringify(body)} : {}), signal: AbortSignal.timeout(12000),
      });
    } catch { throw fail(503, '连接不到本机 Agent Autoloop，请检查后台服务'); }
    if (!response.ok) throw fail(response.status, `中台操作失败（${response.status}），请刷新状态后重试`);
    return response.json();
  }
  async function state() {
    const s = await hub('/v1/state');
    return {...s, runs: s.runs.filter(r => allowedRule(r.rule)), cards: s.cards.filter(c => allowedRule(c.rule)),
      recentCards: s.recentCards.filter(c => allowedRule(c.rule)), lines: s.lines.filter(l => allowedRule(l.name)),
      elsewhere: [], unrouted: []};
  }
  async function messages() {
    const items = history.slice(-60);
    const output = [];
    for (const m of items) {
      let progress = m.progress;
      if (m.event && !m.finished) {
        try { progress = await hub(`/v1/events/${m.event}`, 'GET', undefined, true); }
        catch { /* Preserve submitted text when the hub is temporarily offline. */ }
        if (progress) {
          m.progress = progress;
          m.finished = progress.runs?.length > 0 && progress.runs.every(r => ['done', 'nothing', 'cancelled'].includes(r.state));
        }
      }
      output.push({...m, progress});
    }
    return output;
  }
  async function jsonBody(req) {
    let input = '';
    for await (const chunk of req) {
      input += chunk;
      if (Buffer.byteLength(input) > 20000) throw fail(413, '消息过长');
    }
    try { return JSON.parse(input || '{}'); } catch { throw fail(400, '请求格式不正确'); }
  }
  let qqBridge;
  const server = http.createServer(async (req, res) => {
    const send = (status, value, type = 'application/json; charset=utf-8') => {
      res.writeHead(status, {'Content-Type': type, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
        'Referrer-Policy': 'no-referrer', 'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"});
      res.end(type.startsWith('application/json') ? JSON.stringify(value) : value);
    };
    try {
      const port = server.address().port;
      const hosts = [`127.0.0.1:${port}`, `localhost:${port}`];
      if (!hosts.includes(req.headers.host)) throw fail(403, '仅允许本机访问');
      const origin = `http://${req.headers.host}`;
      if (req.headers.origin && req.headers.origin !== origin) throw fail(403, '拒绝跨站请求');
      if (req.headers['sec-fetch-site'] === 'cross-site') throw fail(403, '拒绝跨站请求');
      const url = new URL(req.url, origin);
      if (req.method === 'GET' && url.pathname === '/api/session') return send(200, {csrf, project: 'LifeAgent'});
      if (req.method === 'GET' && url.pathname === '/api/qq/status') return send(200, qqBridge.status());
      if (req.method === 'GET' && url.pathname === '/api/state') return send(200, await state());
      if (req.method === 'GET' && url.pathname === '/api/messages') return send(200, await messages());
      if (req.method === 'GET' && url.pathname === '/api/progress') {
        const text = await readFile(path.join(projectDir, 'docs/development-status.md'), 'utf8').catch(() => '还没有项目进度记录。');
        return send(200, {text});
      }
      if (req.method === 'POST') {
        if (req.headers['x-local-csrf'] !== csrf) throw fail(403, '页面会话已过期，请刷新');
        const body = await jsonBody(req);
        // Serialize submissions and mutations so a double click cannot duplicate a task.
        const operation = queue.then(async () => {
          if (url.pathname === '/api/qq/config') return qqBridge.configure(body);
          if (url.pathname === '/api/qq/bind') return qqBridge.bind(body.openid);
          if (url.pathname === '/api/qq/disable') return qqBridge.disable(body.unbind === true);
          if (url.pathname === '/api/messages') {
            const text = typeof body.text === 'string' ? body.text.trim() : '';
            if (!text || text.length > 3500) throw fail(400, '请输入 1–3500 字的消息');
            if (typeof body.id !== 'string' || !/^[a-zA-Z0-9-]{16,80}$/.test(body.id)) throw fail(400, '消息编号无效');
            const s = await state();
            const rule = s.lines.find(l => l.name === CHAT_RULE);
            if (!rule) throw fail(503, '网页对话规则尚未加载，请稍后重试');
            if (rule.paused) throw fail(409, '网页对话规则已暂停，请先恢复规则');
            let message = history.find(m => m.id === body.id);
            if (message && message.text !== text) throw fail(409, '消息编号已被其他内容使用');
            if (!message) {
              message = {id: body.id, text, createdAt: new Date().toISOString(), ...(body.id.startsWith('qq-') ? {origin:'qq'} : {})};
              history.push(message); await persist();
            }
            if (!message.event) {
              const result = await hub('/v1/events', 'POST', {id: `webchat:${body.id}`, type: 'localchat.message',
                subject: 'lifeagent', summary: text.slice(0, 180), detail: text}, true);
              if (!result.routed?.includes(CHAT_RULE)) throw fail(409, '对话规则已暂停或未生效，消息已保存；恢复规则后重试发送');
              message.event = result.event; await persist();
            }
            return message;
          }
          const card = /^\/api\/cards\/(\d+)\/(answer|resolve)$/.exec(url.pathname);
          if (card) {
            const s = await state();
            const c = s.cards.find(c => c.id === Number(card[1]));
            if (!c) throw fail(409, '这张卡片已处理，请刷新查看');
            if (card[2] === 'resolve') return hub(`/v1/cards/${c.id}/resolve`, 'POST', {reason: '在本地聊天界面确认已查看'});
            if (c.kind !== 'ask') throw fail(400, '此卡片不需要作选择');
            let answer;
            if (Number.isInteger(body.choice) && body.choice >= 0 && body.choice < c.options.length) answer = {choice: body.choice};
            else if (typeof body.text === 'string' && body.text.trim() && body.text.length <= 3500) answer = {text: body.text.trim()};
            else throw fail(400, '请选择选项或填写回答');
            return hub(`/v1/cards/${c.id}/answer`, 'POST', answer);
          }
          if (url.pathname === '/api/continue') {
            const s = await state();
            if (s.cards.some(c => c.kind === 'ask')) throw fail(409, '请先回答待确认卡片，再继续开发');
            if (s.runs.some(r => ['queued', 'claimed'].includes(r.state))) throw fail(409, '已有任务正在进行，请等待结果');
            return hub(`/v1/rules/${encodeURIComponent('LifeAgent 开发')}/run`, 'POST', {});
          }
          const cancel = /^\/api\/runs\/(\d+)\/cancel$/.exec(url.pathname);
          if (cancel) {
            const s = await state();
            if (!s.runs.some(r => r.id === Number(cancel[1]))) throw fail(404, '没有这个项目任务');
            return hub(`/v1/runs/${cancel[1]}/cancel`, 'POST', {});
          }
          throw fail(404, '没有这个操作');
        });
        queue = operation.catch(() => {});
        return send(200, await operation);
      }
      const assets = {'/': ['index.html', 'text/html; charset=utf-8'], '/app.js': ['app.js', 'text/javascript; charset=utf-8'], '/style.css': ['style.css', 'text/css; charset=utf-8']};
      if (req.method === 'GET' && assets[url.pathname]) {
        const [file, type] = assets[url.pathname];
        return send(200, await readFile(path.join(ROOT, 'public', file)), type);
      }
      throw fail(404, '页面不存在');
    } catch (e) { send(e.status ?? 500, {error: e.status ? e.message : '本地服务出错，请检查日志后重试'}); }
  });
  qqBridge = await createQQBridge({dataDir, local:async (route, body) => {
    if (!server.listening) throw fail(503,'本地聊天服务尚未启动');
    const response = await fetch(`http://127.0.0.1:${server.address().port}/api/${route}`, {
      ...(body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Local-CSRF':csrf},body:JSON.stringify(body)}),
      signal:AbortSignal.timeout(25000),
    });
    const value=await response.json(); if(!response.ok)throw fail(response.status,value.error||'本地任务操作失败');return value;
  }});
  server.once('listening',()=>qqBridge.start().catch(()=>{}));
  const close=server.close.bind(server);
  server.close = callback => {qqBridge.stop().then(()=>close(callback)).catch(()=>close(callback));return server;};
  return server;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const server = await createApp();
  server.listen(Number(process.env.AUTOLOOP_CHAT_PORT || 3366), '127.0.0.1', () => console.log(`Agent Autoloop Chat: http://127.0.0.1:${server.address().port}`));
  for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => server.close(() => process.exit(0)));
}
