import {test,expect,type Page} from '@playwright/test';
import {randomUUID} from 'node:crypto';

async function register(page:Page){
  await page.goto('/#/register');await page.getByLabel('昵称',{exact:true}).fill('对话测试');await page.getByLabel('邮箱',{exact:true}).fill(`chat-${randomUUID()}@example.com`);await page.getByLabel('密码',{exact:true}).fill('Chat-Browser-Only!2026');await page.getByLabel('你的时区').selectOption('Asia/Shanghai');await page.getByRole('button',{name:'创建账号并进入空间'}).click();await expect(page.locator('.page-heading h1')).toContainText('对话测试');
}
async function say(page:Page,text:string){await page.getByLabel('你的消息',{exact:true}).fill(text);await page.getByRole('button',{name:'发送消息',exact:true}).click();}

test('模型设置、持久化多轮对话、重试恢复、清除与数据边界',async({page},info)=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  await register(page);await page.getByRole('link',{name:'AI 对话',exact:true}).click();
  await expect(page.getByRole('button',{name:'发送消息',exact:true})).toBeDisabled();
  await page.getByLabel('模型名称',{exact:true}).fill('fixture-model');await page.getByLabel('API Key',{exact:true}).fill('test-only-model-key');await page.getByRole('checkbox',{name:/允许把我发送的消息/}).check();
  await page.getByRole('button',{name:'保存模型配置',exact:true}).click();await expect(page.getByRole('status')).toContainText('配置已保存');await expect(page.getByLabel('API Key',{exact:true})).toHaveValue('');
  await page.getByRole('button',{name:'测试连接',exact:true}).click();await expect(page.getByRole('status')).toContainText('连接测试成功');
  expect(JSON.stringify(await(await page.request.get('/api/v1/model-settings')).json())).not.toContain('test-only-model-key');
  await page.getByRole('button',{name:'收起模型设置'}).click();
  await say(page,'你好，帮我整理想法');await expect(page.locator('.chat-message.assistant')).toContainText('测试模型回复：你好');
  await say(page,'继续讨论');await expect(page.locator('.chat-message.assistant').last()).toContainText('此前用户消息：你好');
  await page.reload();await expect(page.locator('.chat-message')).toHaveCount(4);await expect(page.getByLabel('你的消息')).toHaveValue('');
  await page.screenshot({path:info.outputPath('chat.png'),fullPage:true});
  await page.getByRole('button',{name:'新建对话',exact:true}).click();await say(page,'另一个会话');await expect(page.locator('.chat-message.assistant')).toContainText('另一个会话');await expect(page.locator('.chat-message.assistant')).not.toContainText('整理想法');
  await page.locator('.conversation-item').filter({hasText:'你好，帮我整理想法'}).click();await expect(page.locator('.chat-message')).toHaveCount(4);
  await say(page,'请模拟一次限流');await expect(page.locator('.message-failure')).toContainText('限流');await page.getByRole('button',{name:'重试回复',exact:true}).click();await expect(page.locator('.message-failure')).toHaveCount(0);await expect(page.locator('.chat-message.user')).toHaveCount(3);
  let lost=false;const keys:string[]=[];
  await page.route('**/api/v1/conversations/*/messages',async route=>{if(route.request().method()!=='POST'){await route.continue();return;}keys.push(route.request().headers()['idempotency-key']);if(!lost){lost=true;await route.fetch();await route.abort('failed');}else await route.continue();});
  await say(page,'丢失响应后再试');await expect(page.getByRole('alert')).toContainText('连接不上');await expect(page.getByLabel('你的消息')).toHaveValue('丢失响应后再试');await page.getByRole('button',{name:'发送消息',exact:true}).click();await expect(page.locator('.chat-message.user')).toHaveCount(4);expect(keys).toHaveLength(2);expect(keys[0]).toBe(keys[1]);await page.unroute('**/api/v1/conversations/*/messages');
  const cid=new URLSearchParams(new URL(page.url()).hash.split('?')[1]).get('conversation');
  await say(page,'等待刷新恢复');await expect.poll(async()=>{const r=await(await page.request.get('/api/v1/conversations/'+cid)).json();return r.items.at(-1)?.status;}).toBe('pending');await page.reload();await expect(page.locator('.chat-message.assistant').last()).toContainText('等待刷新恢复');
  await say(page,'<img src=x onerror="window.chatInjected=true">');await expect(page.locator('.chat-message.assistant').last()).toContainText('<img');expect(await page.evaluate(()=>Boolean((window as unknown as Record<string,unknown>).chatInjected))).toBe(false);await expect(page.locator('img[src=x]')).toHaveCount(0);
  const profile=await(await page.request.get('/api/v1/me')).json();const task=await page.request.post('/api/v1/tasks',{data:{title:'清除对话后保留待办'},headers:{'X-CSRF-Token':profile.csrf_token,'Idempotency-Key':randomUUID()}});expect(task.status()).toBe(201);
  await page.getByRole('button',{name:'清除会话',exact:true}).click();await expect(page.locator('.conversation-item').filter({hasText:'你好，帮我整理想法'})).toHaveCount(0);
  expect((await page.request.get('/api/v1/conversations/'+cid)).status()).toBe(404);expect(JSON.stringify(await(await page.request.get('/api/v1/tasks')).json())).toContain('清除对话后保留待办');
  await page.getByRole('button',{name:'模型设置',exact:true}).click();await page.getByRole('button',{name:'删除模型配置',exact:true}).click();await expect(page.getByRole('status')).toContainText('已删除');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);expect(errors).toEqual([]);
});
