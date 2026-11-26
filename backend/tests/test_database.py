"""SQLite verifies revision logic only, not PostgreSQL compatibility."""
from io import StringIO
from alembic import command

from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from fastapi.testclient import TestClient

from lifeagent import database
from lifeagent.main import app


def test_readiness_checks_real_revision_without_writing(monkeypatch):
    engine = create_engine('sqlite://')
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://unused')
    monkeypatch.setattr(database, 'create_engine', lambda *a, **kw: engine)
    monkeypatch.setattr(engine, 'dispose', lambda: None)
    assert database.readiness() == (False, 'migrations_pending')
    with engine.begin() as conn:
        assert not conn.dialect.has_table(conn, 'alembic_version')
        MigrationContext.configure(conn)._ensure_version_table()
        conn.execute(text("INSERT INTO alembic_version VALUES ('0004_conversations')"))
    assert database.readiness() == (True, 'ready')
    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num='unknown'"))
    assert database.readiness() == (False, 'migrations_pending')


def test_invalid_configuration_is_redacted(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'bad://user:secret@host')
    response = TestClient(app).get('/health/ready')
    assert response.status_code == 503
    assert response.json()['reason'] == 'database_unavailable'
    assert 'secret' not in response.text
    assert TestClient(app).get('/health/live').status_code == 200


def test_connection_failure_is_redacted(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://user:secret@127.0.0.1:1/test')
    response = TestClient(app).get('/health/ready')
    assert response.status_code == 503
    assert response.json()['reason'] == 'database_unavailable'
    assert 'secret' not in response.text


def test_ready_endpoint(monkeypatch):
    monkeypatch.setattr('lifeagent.main.readiness', lambda: (True, 'ready'))
    response = TestClient(app).get('/health/ready')
    assert response.status_code == 200
    assert response.json() == {'status': 'ready'}


def test_postgresql_baseline_offline_sql(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://unused')
    config = database.migration_config()
    config.output_buffer = StringIO()
    command.upgrade(config, 'head', sql=True)
    sql = config.output_buffer.getvalue()
    assert 'CREATE TABLE alembic_version' in sql
    assert '0001_baseline' in sql
