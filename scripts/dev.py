"""Run the native UI/API together; stop only processes created by this launcher."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from prepare_dev import main as prepare, dev_url

ROOT = Path(__file__).resolve().parents[1]


def main():
    prepare()
    env=dict(os.environ,DATABASE_URL=dev_url().render_as_string(hide_password=False),APP_ENV='development',
        APP_ORIGIN='http://127.0.0.1:5173',LIFEAGENT_API_TARGET='http://127.0.0.1:8000')
    children=[]
    def shutdown(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,shutdown)
    signal.signal(signal.SIGINT,shutdown)
    try:
        children.append(subprocess.Popen([sys.executable,'-m','uvicorn','lifeagent.main:app','--host','127.0.0.1','--port','8000'],cwd=ROOT/'backend',env=env,start_new_session=True))
        children.append(subprocess.Popen(['npm','run','dev'],cwd=ROOT/'frontend',env=env,start_new_session=True))
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
