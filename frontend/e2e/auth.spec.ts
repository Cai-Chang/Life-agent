import {test,expect,type Page} from '@playwright/test';
import {randomUUID} from 'node:crypto';

const password='Browser-Test-Only!2026';
async function register(page:Page,email:string) {
  await page.goto('/#/register');
  await page.getByLabel('昵称',{exact:true}).fill('小林');
  await page.getByLabel('邮箱',{exact:true}).fill(email);
  await page.getByLabel('密码',{exact:true}).fill(password);
  await page.getByLabel('你的时区').selectOption('Asia/Shanghai');
  await page.getByRole('button',{name:'创建账号并进入空间'}).click();
  await expect(page.locator('.page-heading h1')).toContainText('小林');
}

test('注册、空间重命名、资料持久化、退出及重新登录',async({page},info)=>{
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
  const email=`browser-${randomUUID()}@example.com`;
  await page.goto('/#/register');await page.screenshot({path:info.outputPath('register.png'),fullPage:true});
  await register(page,email);
  const initial=await(await page.request.get('/api/v1/me')).json();
  await page.screenshot({path:info.outputPath('home.png'),fullPage:true});
  await page.getByRole('link',{name:'个人空间',exact:true}).click();
  await page.getByLabel('空间名称').fill('我的学习空间');
  await page.getByRole('button',{name:'保存空间名称'}).click();
  await expect(page.getByRole('status')).toHaveText('空间名称已更新');
  await page.reload();await expect(page.getByLabel('空间名称')).toHaveValue('我的学习空间');
  await page.screenshot({path:info.outputPath('space.png'),fullPage:true});
  await page.getByRole('link',{name:'个人设置',exact:true}).click();
  await page.getByLabel('昵称',{exact:true}).fill('小陈');
  await page.getByLabel('生活时区',{exact:true}).selectOption('UTC');
  await page.getByRole('button',{name:'保存个人资料'}).click();
  await expect(page.getByRole('status')).toHaveText('个人资料已保存');
  await page.reload();await expect(page.getByLabel('昵称',{exact:true})).toHaveValue('小陈');
  await expect(page.getByLabel('生活时区',{exact:true})).toHaveValue('UTC');
  await page.getByRole('button',{name:'退出登录'}).click();
  await expect(page.getByRole('heading',{name:'欢迎回来'})).toBeVisible();
  await page.getByLabel('邮箱',{exact:true}).fill(email);
  await page.getByLabel('密码',{exact:true}).fill('wrong-password');
  await page.getByRole('button',{name:'登录',exact:true}).click();
  await expect(page.getByRole('alert')).toHaveText('邮箱或密码不正确');
  await page.getByLabel('密码',{exact:true}).fill(password);
  await page.getByRole('button',{name:'登录',exact:true}).click();
  await expect(page.locator('.page-heading h1')).toContainText('小陈');
  const restored=await(await page.request.get('/api/v1/me')).json();
  expect(restored.workspace.id).toBe(initial.workspace.id);
  expect(restored.workspace.name).toBe('我的学习空间');
  expect(restored.user.timezone).toBe('UTC');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  expect(errors).toEqual([]);
});

test('会话丢失后拒绝修改并返回登录页',async({page,context})=>{
  await register(page,`session-${randomUUID()}@example.com`);
  await page.getByRole('link',{name:'个人设置',exact:true}).click();
  await expect(page.getByLabel('服务商与地域',{exact:true})).toBeVisible();
  await page.getByLabel('昵称',{exact:true}).fill('不应保存');
  await context.clearCookies();
  await page.getByRole('button',{name:'保存个人资料'}).click();
  await expect(page.getByRole('heading',{name:'欢迎回来'})).toBeVisible();
  await expect(page.getByRole('alert')).toHaveText('登录已失效，请重新登录。');
});
