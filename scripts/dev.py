"""Run the native UI/API together; stop only processes created by this launcher."""
import os
from pathlib import Path
import signal
import socket
import json
import urllib.error
import urllib.request
import subprocess
import sys
import time
from prepare_dev import main as prepare, dev_url

ROOT = Path(__file__).resolve().parents[1]


def main():
    for port in (8000, 5173):
        with socket.socket() as probe:
            probe.settimeout(.3)
            if probe.connect_ex(('127.0.0.1', port)) == 0:
                raise SystemExit(f'LifeAgent 端口 {port} 已被占用。请在原启动终端按 Ctrl+C 停止，再运行本命令。') from None
    prepare()
    env=dict(os.environ,DATABASE_URL=dev_url().render_as_string(hide_password=False),APP_ENV='development',
        APP_ORIGIN='http://127.0.0.1:5173',LIFEAGENT_API_TARGET='http://127.0.0.1:8000')
    children=[]
    def shutdown(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,shutdown)
    signal.signal(signal.SIGINT,shutdown)
    try:
        children.append(subprocess.Popen([sys.executable,'-m','uvicorn','lifeagent.main:app','--host','127.0.0.1','--port','8000','--reload','--reload-dir',str(ROOT/'backend/lifeagent'),'--reload-dir',str(ROOT/'backend/migrations')],cwd=ROOT/'backend',env=env,start_new_session=True))
        children.append(subprocess.Popen(['npm','run','dev'],cwd=ROOT/'frontend',env=env,start_new_session=True))
        ready = False
        for _ in range(100):
            if any(process.poll() is not None for process in children):
                break
            try:
                with urllib.request.urlopen('http://127.0.0.1:5173/health/ready', timeout=.5) as response:
                    ready = response.status == 200 and json.load(response) == {'status':'ready'}
            except (OSError, ValueError, urllib.error.URLError):
                pass
            if ready:
                break
            time.sleep(.2)
        if not ready:
            print('LifeAgent 未能就绪；请查看上方 API/前端启动日志。', file=sys.stderr, flush=True)
            return 1
        print('LifeAgent: http://127.0.0.1:5173  (Ctrl+C stops UI/API; Autoloop stays off)',flush=True)
        while all(process.poll() is None for process in children):
            time.sleep(0.3)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for process in children:
            if process.poll() is None:
                try:
                    os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:
                    pass
        for process in children:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)


if __name__=='__main__':
    sys.exit(main())
