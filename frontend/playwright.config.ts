import {defineConfig} from '@playwright/test';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
export default defineConfig({
  testDir: './e2e', fullyParallel: false, workers: 1, retries: 0, timeout: 45000,
  reporter: [['list'], ['html', {open: 'never'}]],
  use: {baseURL: 'http://127.0.0.1:5174', browserName: 'chromium',
    channel: process.env.CI ? undefined : 'chrome', screenshot: 'only-on-failure', trace: 'retain-on-failure'},
  projects: [{name:'desktop',use:{viewport:{width:1440,height:1000}}}, {name:'mobile',use:{viewport:{width:390,height:844}}}],
  webServer: [
    {command:'python -m uvicorn lifeagent.main:app --host 127.0.0.1 --port 8765',cwd:path.resolve(here,'../backend'),
      url:'http://127.0.0.1:8765/health/live',reuseExistingServer:false,timeout:30000,
      env:{APP_ENV:'development',APP_ORIGIN:'http://127.0.0.1:5174'}},
    {command:'npm run dev -- --port 5174',url:'http://127.0.0.1:5174',reuseExistingServer:false,timeout:30000,
      env:{LIFEAGENT_API_TARGET:'http://127.0.0.1:8765'}},
  ],
});
