"""Database setup and read-only readiness; never migrate during a request."""
import os
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool


def migration_config() -> Config:
    config = Config()
    config.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'migrations'))
    return config


def database_url() -> str:
    value = os.environ.get('DATABASE_URL', '')
    if make_url(value).drivername != 'postgresql+psycopg':
        raise ValueError('DATABASE_URL must use postgresql+psycopg')
    return value


def readiness() -> tuple[bool, str]:
    if not os.environ.get('DATABASE_URL'):
        return False, 'dependencies_not_configured'
    engine = None
    try:
        url = database_url()
        engine = create_engine(url, poolclass=NullPool, connect_args={'connect_timeout': 3, 'options': '-c statement_timeout=3000'}, hide_parameters=True)
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
            current = set(MigrationContext.configure(connection).get_current_heads())
            expected = set(ScriptDirectory.from_config(migration_config()).get_heads())
            if not expected or current != expected:
                return False, 'migrations_pending'
        return True, 'ready'
    except Exception:
        # Never expose URLs, credentials or driver errors in public responses.
        return False, 'database_unavailable'
    finally:
        if engine is not None:
            engine.dispose()
