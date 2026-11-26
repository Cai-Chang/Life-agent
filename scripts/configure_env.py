"""Create a private local Docker configuration once; never overwrite existing secrets."""
from pathlib import Path
import os
import secrets

root = Path(__file__).resolve().parents[1]
target = root / '.env'
try:
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
except FileExistsError:
    raise SystemExit('.env already exists and was preserved.')
with os.fdopen(fd, 'w') as stream:
    stream.write(f'POSTGRES_PASSWORD={secrets.token_urlsafe(32)}\nAPP_ENV=development\nAPP_ORIGIN=http://localhost:8080\nLIFEAGENT_HTTP_PORT=8080\n')
print('Created private .env for local Docker development; no credentials printed.')
