"""Run explicitly: python -m lifeagent.migrate (upgrade only)."""
from alembic import command
from lifeagent.database import migration_config

if __name__ == '__main__':
    command.upgrade(migration_config(), 'head')
