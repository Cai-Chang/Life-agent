import {test,expect,type Page} from '@playwright/test';
import {randomUUID} from 'node:crypto';
import {candidates,instant,localTime,dayStart} from '../src/time';

async function register(page:Page,zone='Asia/Shanghai'){
  await page.goto('/#/register');await page.getByLabel('昵称',{exact:true}).fill('日程测试');
  await page.getByLabel('邮箱',{exact:true}).fill(`planning-${randomUUID()}@example.com`);
  await page.getByLabel('密码',{exact:true}).fill('Browser-Planning-Only!2026');
  await page.getByLabel('你的时区').selectOption(zone);
  await page.getByRole('button',{name:'创建账号并进入空间'}).click();
  await expect(page.locator('.page-heading h1')).toContainText('日程测试');
}
async function calendar(page:Page){await page.getByRole('link',{name:'日程',exact:true}).click();await page.getByLabel('查看日期').fill('2026-12-01');await expect(page.locator('.range-label')).toContainText('2026-11-30');}
async function createEvent(page:Page,title='学习 Python',start='09:00',end='10:00'){
  await page.getByRole('button',{name:'新建日程',exact:true}).click();
  await page.getByLabel('日程标题',{exact:true}).fill(title);
  await page.getByLabel('开始时间',{exact:true}).fill('2026-12-01T'+start);
  await page.getByLabel('结束时间',{exact:true}).fill('2026-12-01T'+end);
  await page.getByRole('button',{name:'保存日程',exact:true}).click();
}

test('日程与待办完整闭环，取消日程保留待办',async({page},info)=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  await register(page);await calendar(page);await createEvent(page);
  let card=page.locator('.event-card').filter({has:page.getByRole('heading',{name:'学习 Python',exact:true})});
  await expect(card).toBeVisible();await expect(card).toContainText('09:00');
  await card.getByRole('button',{name:'编辑',exact:true}).click();await page.getByLabel('日程标题').fill('学习计划');await page.getByRole('button',{name:'保存日程',exact:true}).click();
  await page.getByRole('button',{name:'月视图'}).click();await expect(page.locator('.calendar-day')).toHaveCount(31);
  await page.screenshot({path:info.outputPath('calendar-month.png'),fullPage:true});
  await page.getByRole('link',{name:'待办',exact:true}).click();await page.getByRole('button',{name:'新建待办',exact:true}).click();
  await page.getByLabel('待办标题').fill('完成第一章');await page.getByLabel('待办备注').fill('记录学习笔记');
  await page.getByLabel('截止时间',{exact:true}).fill('2026-12-01T18:00');await page.getByRole('combobox',{name:'优先级',exact:true}).selectOption('high');
  const select=page.getByLabel('关联日程（可选）');await expect(select.locator('option')).toHaveCount(2);await select.selectOption({index:1});
  await page.getByRole('button',{name:'保存待办',exact:true}).click();await expect(page.locator('.task-card')).toHaveCount(1);
  await page.reload();await expect(page.locator('.task-card')).toContainText('完成第一章');await expect(page.locator('.task-card')).toContainText('高优先级');
  await page.screenshot({path:info.outputPath('tasks.png'),fullPage:true});
  await page.getByRole('link',{name:'概览',exact:true}).click();await expect(page.locator('.agenda')).toContainText('完成第一章');await expect(page.locator('.agenda-counts')).toContainText('1 未完成待办');
  await calendar(page);card=page.locator('.event-card').filter({hasText:'学习计划'});await card.getByRole('button',{name:'取消日程',exact:true}).click();await expect(card).toHaveCount(0);
  await page.getByLabel('显示已取消').check();await expect(page.locator('.event-card')).toContainText('已取消');
  await page.getByRole('link',{name:'待办',exact:true}).click();await expect(page.locator('.task-card')).toContainText('完成第一章');
  await page.getByRole('button',{name:'标记完成',exact:true}).click();await page.reload();await expect(page.locator('.task-card')).toContainText('已完成');
  await page.getByLabel('筛选状态').selectOption('pending');await expect(page.locator('.task-card')).toHaveCount(0);
  await page.getByLabel('筛选状态').selectOption('done');await expect(page.locator('.task-card')).toHaveCount(1);
  await page.getByRole('button',{name:'重新打开',exact:true}).click();await expect(page.locator('.task-card')).toHaveCount(0);
  await page.getByLabel('筛选状态').selectOption('all');await page.getByRole('button',{name:'编辑待办',exact:true}).click();
  await page.getByLabel('待办标题').fill('继续学习');await page.getByLabel('截止时间',{exact:true}).fill('');await page.getByLabel('待办状态').selectOption('in_progress');
  await page.getByRole('button',{name:'保存待办',exact:true}).click();await page.getByRole('combobox',{name:'截止日期',exact:true}).selectOption('none');await expect(page.locator('.task-card')).toContainText('进行中');
  await page.getByRole('button',{name:'取消待办',exact:true}).click();await expect(page.locator('.task-card')).toContainText('已取消');
  await page.getByRole('button',{name:'删除待办',exact:true}).click();await expect(page.locator('.task-card')).toHaveCount(0);
  await calendar(page);await page.getByLabel('显示已取消').check();await page.getByRole('button',{name:'恢复日程',exact:true}).click();await expect(page.locator('.event-card')).not.toContainText('已取消');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);expect(errors).toEqual([]);
});

test('冲突、相邻日程和夏令时歧义处理',async({page})=>{
  await register(page);await calendar(page);await createEvent(page,'已有日程');await expect(page.locator('.event-card')).toHaveCount(1);
  await createEvent(page,'重叠日程','09:30','10:30');await expect(page.getByRole('alert')).toContainText('重叠');await expect(page.getByLabel('日程标题')).toHaveValue('重叠日程');
  await page.getByLabel('开始时间',{exact:true}).fill('2026-12-01T10:00');await page.getByLabel('结束时间',{exact:true}).fill('2026-12-01T11:00');await page.getByRole('button',{name:'保存日程',exact:true}).click();
  await expect(page.locator('.event-card')).toHaveCount(2);await page.reload();await expect(page.locator('.event-card')).toHaveCount(2);
  await page.getByRole('link',{name:'个人设置',exact:true}).click();await page.getByLabel('生活时区',{exact:true}).selectOption('America/New_York');await page.getByRole('button',{name:'保存个人资料'}).click();await expect(page.getByRole('status')).toContainText('已保存');
await page.getByRole('link',{name:'日程',exact:true}).click();await page.getByLabel('查看日期').fill('2026-11-01');
  await page.getByRole('button',{name:'新建日程',exact:true}).click();await page.getByLabel('日程标题').fill('夏令时日程');
  await page.getByLabel('开始时间',{exact:true}).fill('2026-11-01T01:30');await page.getByLabel('结束时间',{exact:true}).fill('2026-11-01T02:30');
  await page.getByRole('combobox',{name:'重复时刻（开始时间）',exact:true}).selectOption('2026-11-01T06:30:00.000Z');
  await page.getByRole('button',{name:'保存日程',exact:true}).click();await expect(page.locator('.event-card')).toHaveCount(1);
  const saved=await(await page.request.get('/api/v1/events?start=2026-11-01T00:00Z&end=2026-11-02T12:00Z')).json();expect(saved.items[0].start_at).toBe('2026-11-01T06:30:00+00:00');
  await page.getByRole('button',{name:'新建日程',exact:true}).click();await page.getByLabel('日程标题').fill('不存在的时间');
  await page.getByLabel('开始时间',{exact:true}).fill('2026-03-08T02:30');await page.getByLabel('结束时间',{exact:true}).fill('2026-03-08T03:30');
  await page.getByRole('button',{name:'保存日程',exact:true}).click();await expect(page.getByRole('alert')).toContainText('不存在');await expect(page.locator('.event-card')).toHaveCount(1);
});

test('响应丢失后重试不重复创建待办',async({page})=>{
  await register(page);await page.getByRole('link',{name:'待办',exact:true}).click();
  const keys:string[]=[];let lost=false;
  await page.route('**/api/v1/tasks',async route=>{
    if(route.request().method()!=='POST'){await route.continue();return;}
    keys.push(route.request().headers()['idempotency-key']);
    if(!lost){lost=true;await route.fetch();await route.abort('failed');}else await route.continue();
  });
  await page.getByRole('button',{name:'新建待办',exact:true}).click();await page.getByLabel('待办标题').fill('仅创建一次');await page.getByRole('button',{name:'保存待办',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('连接不上');await page.getByRole('button',{name:'保存待办',exact:true}).click();
  await expect(page.locator('.task-card')).toHaveCount(1);expect(keys).toHaveLength(2);expect(keys[0]).toBe(keys[1]);
});

test('配置时区与夏令时重复、缺失时刻处理',()=>{
  expect(localTime('2026-12-01T01:00Z','Asia/Shanghai')).toBe('2026-12-01T09:00');
  expect(candidates('2026-11-01T01:30','America/New_York')).toEqual(['2026-11-01T05:30:00.000Z','2026-11-01T06:30:00.000Z']);
  expect(()=>instant('2026-11-01T01:30','America/New_York')).toThrow('两次');
  expect(instant('2026-11-01T01:30','America/New_York','2026-11-01T06:30:00.000Z')).toBe('2026-11-01T06:30:00.000Z');
  expect(candidates('2026-03-08T02:30','America/New_York')).toEqual([]);
  expect(dayStart('2026-12-01','Asia/Shanghai')).toBe('2026-11-30T16:00:00.000Z');
});

