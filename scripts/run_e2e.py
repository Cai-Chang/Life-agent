"""Run browser tests with a new disposable database; never use an existing app DB."""
import getpass
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[1]


def main():
    admin_url = make_url(os.environ['LIFEAGENT_TEST_DATABASE_URL']) if os.environ.get('LIFEAGENT_TEST_DATABASE_URL') else URL.create(
        'postgresql+psycopg', username=getpass.getuser(), database='postgres',
        query={'host':str(ROOT/'.conda/postgresql-host/socket'),'port':'55439'})
    name='lifeagent_e2e_'+uuid4().hex
    engine=create_engine(admin_url,isolation_level='AUTOCOMMIT',poolclass=NullPool)
    with engine.connect() as connection:
        connection.exec_driver_sql('CREATE DATABASE '+name)
    env=dict(os.environ,DATABASE_URL=admin_url.set(database=name).render_as_string(hide_password=False),
        PATH=str(Path(sys.executable).parent)+os.pathsep+os.environ['PATH'],APP_ENV='development')
    try:
        subprocess.run([sys.executable,'-m','lifeagent.migrate'],cwd=ROOT/'backend',env=env,check=True)
        result=subprocess.run(['npm','run','test:e2e','--',*sys.argv[1:]],cwd=ROOT/'frontend',env=env)
        return result.returncode
    finally:
        with engine.connect() as connection:
            connection.exec_driver_sql('DROP DATABASE '+name+' WITH (FORCE)')
        engine.dispose()


if __name__=='__main__':
    sys.exit(main())
