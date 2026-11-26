"""Prepare the native development DB without touching any other database."""
import getpass
import os
from pathlib import Path
import subprocess
import sys
import time
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[1]


def dev_url(database='lifeagent_dev'):
    return URL.create('postgresql+psycopg', username=getpass.getuser(), database=database,
        query={'host':str(ROOT/'.conda/postgresql-host/socket'),'port':'55439'})


def ensure_database():
    probe = ROOT / '.conda/postgresql-test/bin/pg_isready'
    def ready():
        return probe.exists() and subprocess.run([str(probe), '-h', str(ROOT/'.conda/postgresql-host/socket'), '-p', '55439'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if ready():
        return
    if sys.platform != 'darwin':
        raise RuntimeError('Native launcher requires the project macOS DB service; use Docker Compose on other platforms')
    plist = Path.home()/'Library/LaunchAgents/local.lifeagent.postgresql-test.plist'
    if not plist.exists():
        raise RuntimeError('Project DB service is not installed; follow README setup first')
    loaded = subprocess.run(['launchctl', 'print', f'gui/{os.getuid()}/local.lifeagent.postgresql-test'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not loaded:
        subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(plist)], check=True)
    for _ in range(60):
        if ready():
            return
        time.sleep(.2)
    raise RuntimeError('Project DB did not become ready; inspect .conda/postgresql-host/server-error.log')


def main():
    ensure_database()
    engine=create_engine(dev_url('postgres'),isolation_level='AUTOCOMMIT',poolclass=NullPool)
    with engine.connect() as connection:
        exists=connection.scalar(text("SELECT 1 FROM pg_database WHERE datname = 'lifeagent_dev'"))
        if not exists:
            connection.exec_driver_sql('CREATE DATABASE lifeagent_dev')
    engine.dispose()
    env=dict(os.environ,DATABASE_URL=dev_url().render_as_string(hide_password=False))
    subprocess.run([sys.executable,'-m','lifeagent.migrate'],cwd=ROOT/'backend',env=env,check=True)
    print('Native LifeAgent development database is ready; existing records were preserved.')


if __name__=='__main__':
    main()
