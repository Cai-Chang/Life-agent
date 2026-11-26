"""Authentication integration tests always use a newly created disposable PostgreSQL DB."""
import os
from pathlib import Path
from uuid import uuid4
import pytest
from alembic import command
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool


@pytest.fixture(scope='session')
def postgres_url():
    import getpass
    root = Path(__file__).resolve().parents[2]
    value = os.environ.get('LIFEAGENT_TEST_DATABASE_URL')
    admin_url = make_url(value) if value else URL.create('postgresql+psycopg', username=getpass.getuser(), database='postgres',
        query={'host': str(root / '.conda/postgresql-host/socket'), 'port': '55439'})
    if admin_url.drivername != 'postgresql+psycopg':
        pytest.fail('Integration tests require PostgreSQL with psycopg')
    admin = create_engine(admin_url, isolation_level='AUTOCOMMIT', poolclass=NullPool, connect_args={'connect_timeout':3})
    name = 'lifeagent_test_' + uuid4().hex
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql('CREATE DATABASE ' + name)
    except Exception:
        admin.dispose()
        pytest.fail('Test PostgreSQL unavailable: start the project DB service or set LIFEAGENT_TEST_DATABASE_URL; no existing database was modified')
    target = admin_url.set(database=name).render_as_string(hide_password=False)
    old = os.environ.get('DATABASE_URL')
    try:
        os.environ['DATABASE_URL'] = target
        from lifeagent.database import migration_config
        command.upgrade(migration_config(), 'head')
        yield target
    finally:
        if old is None:
            os.environ.pop('DATABASE_URL', None)
        else:
            os.environ['DATABASE_URL'] = old
        with admin.connect() as connection:
            connection.exec_driver_sql('DROP DATABASE ' + name + ' WITH (FORCE)')
        admin.dispose()
