"""Install the project test PostgreSQL as a user launch service, from a host terminal.

This service only runs PostgreSQL; application code and migrations stay in the
Agent sandbox. Existing project or system databases are not reused or removed.
"""
import getpass
import os
from pathlib import Path
import plistlib
import subprocess
import time


def main():
    root = Path(__file__).resolve().parents[2]
    binary = root / '.conda/postgresql-test/bin'
    host = root / '.conda/postgresql-host'
    data, socket = host / 'data', host / 'socket'
    label = 'local.lifeagent.postgresql-test'
    service = f'gui/{os.getuid()}/{label}'
    plist = Path.home() / 'Library/LaunchAgents' / f'{label}.plist'
    if not (binary / 'postgres').is_file():
        raise SystemExit('Project PostgreSQL is not installed')
    for folder in (host, socket):
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        folder.chmod(0o700)
    settings = {
        'Label': label,
        'ProgramArguments': [str(binary / 'postgres'), '-D', str(data), '-h', '',
                             '-k', str(socket), '-p', '55439', '-c', 'unix_socket_permissions=0700'],
        'WorkingDirectory': str(host), 'RunAtLoad': True, 'KeepAlive': True,
        'ThrottleInterval': 10,
        'StandardOutPath': str(host / 'server.log'),
        'StandardErrorPath': str(host / 'server-error.log'),
    }
    if plist.exists() and plistlib.loads(plist.read_bytes()) != settings:
        raise SystemExit('An existing service has different settings; review it before changing')
    if not (data / 'PG_VERSION').exists():
        if data.exists():
            raise SystemExit('Incomplete data directory preserved; inspect before trying again')
        subprocess.run([str(binary / 'initdb'), '-D', str(data), '-U', getpass.getuser(),
                        '--auth-local=peer', '--auth-host=reject', '--no-locale', '-E', 'UTF8', '--no-clean'], check=True)
    elif (data / 'PG_VERSION').read_text().strip() != '17':
        raise SystemExit('Unexpected PostgreSQL major version; no upgrade attempted')
    if not plist.exists():
        plist.write_bytes(plistlib.dumps(settings))
        plist.chmod(0o600)
    loaded = subprocess.run(['launchctl', 'print', service], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not loaded:
        subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(plist)], check=True)
    for _ in range(60):
        probe = subprocess.run([str(binary / 'pg_isready'), '-h', str(socket), '-p', '55439'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if probe.returncode == 0:
            print('Project PostgreSQL host service is ready (Unix socket only).')
            print('Service:', service)
            print('Socket:', socket)
            return
        time.sleep(0.25)
    raise SystemExit(f'Database did not become ready; inspect {host}/server-error.log')


if __name__ == '__main__':
    main()
