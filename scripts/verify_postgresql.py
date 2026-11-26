"""Verify against a fresh project-local PostgreSQL database; preserve its data.
Run with .conda/lifeagent-dev/bin/python scripts/verify_postgresql.py.
Use the project host service when installed; otherwise start a temporary cluster.
Only temporary processes owned by this invocation are stopped.
"""
import getpass
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import json
import socket

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / '.conda/postgresql-test/bin'
HOST = ROOT / '.conda/postgresql-host'
USER = getpass.getuser()


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def http(url):
    try:
        response = urllib.request.urlopen(url, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


def main():
    import argparse
    import uuid
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fresh-cluster', action='store_true', help='Start an independent temporary cluster; requires host shared-memory access')
    args = parser.parse_args()
    host_mode = (HOST / 'data/PG_VERSION').exists() and not args.fresh_cluster
    run_dir = Path(tempfile.mkdtemp(prefix='pg-check-', dir=ROOT / '.conda'))
    data = run_dir / 'data'
    socket_dir = HOST / 'socket' if host_mode else run_dir
    database = 'lifeagent_verify_' + uuid.uuid4().hex[:16]
    started = False
    api = None
    try:
        if host_mode:
            # Connect only: the host service owns PostgreSQL shared-memory calls.
            run(BIN / 'pg_isready', '-h', socket_dir, '-p', '55439', '-U', USER)
            print('HOST SERVICE: reuse project PostgreSQL; no initdb or server startup in the Agent sandbox', flush=True)
        else:
            run(BIN / 'initdb', '-D', data, '-U', USER, '--auth-local=peer', '--auth-host=reject', '--no-locale', '-E', 'UTF8', '--no-clean', '-c', 'shared_memory_type=mmap', '-c', 'dynamic_shared_memory_type=mmap')
            run(BIN / 'pg_ctl', '-D', data, '-l', run_dir / 'postgres.log', '-o', f"-h '' -k {run_dir} -p 55439", '-w', 'start')
            started = True
        # Every run owns a new empty database. Never migrate an existing user's DB.
        run(BIN / 'createdb', '-h', socket_dir, '-p', '55439', '-U', USER, database)
        print('TEST DATABASE:', database, flush=True)
        from sqlalchemy.engine import URL
        env = dict(os.environ, DATABASE_URL=URL.create('postgresql+psycopg', username=USER, database=database, query={'host': str(socket_dir), 'port': '55439'}).render_as_string(hide_password=False))
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        with (run_dir / 'api.log').open('w') as log:
            api = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'lifeagent.main:app', '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT / 'backend', env=env, stdout=log, stderr=log)
            base = f'http://127.0.0.1:{port}'
            for _ in range(100):
                if api.poll() is not None:
                    raise RuntimeError('Test API exited; inspect api.log')
                try:
                    assert http(base + '/health/live') == (200, {'status': 'alive'})
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError('Test API did not start')
            before = http(base + '/health/ready')
            assert before == (503, {'status': 'not_ready', 'reason': 'migrations_pending'}), before
            print('BEFORE MIGRATION:', before, flush=True)
            run(sys.executable, '-m', 'lifeagent.migrate', cwd=ROOT / 'backend', env=env)
            after = http(base + '/health/ready')
            assert after == (200, {'status': 'ready'}), after
            print('AFTER MIGRATION:', after, flush=True)
            run(sys.executable, '-m', 'lifeagent.migrate', cwd=ROOT / 'backend', env=env)
            assert http(base + '/health/ready') == after
            print('REPEATED UPGRADE: ready', flush=True)
    finally:
        if api is not None:
            api.terminate()
            try:
                api.wait(timeout=10)
            except subprocess.TimeoutExpired:
                api.kill()
                api.wait(timeout=5)
        if started:
            run(BIN / 'pg_ctl', '-D', data, '-w', 'stop')
        print('Preserved verification logs:', run_dir, flush=True)
        if host_mode:
            print('Host service left running; preserved test database:', database, flush=True)


if __name__ == '__main__':
    main()
