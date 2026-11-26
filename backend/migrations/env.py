"""Explicit migration entry point; DATABASE_URL is never stored in config."""
from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from lifeagent.database import database_url

if context.is_offline_mode():
    context.configure(url=database_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(database_url(), poolclass=NullPool, connect_args={'connect_timeout': 3})
    try:
        with engine.connect() as connection:
            context.configure(connection=connection)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
