"""Apply the reviewed organization-admin migration to an explicitly selected target.

Usage: .venv/bin/python scripts/portal_org_upgrade.py local
       .venv/bin/python scripts/portal_org_upgrade.py cloud
Only SECURITY DEFINER functions and grants are added. No data, users or credentials are created.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse, unquote

import psycopg

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = [('org-admin-v1', ROOT / 'supabase/migrations/202611050001_org_admin.sql'),
              ('registrar-login-v1', ROOT / 'supabase/migrations/202611050002_registrar_login.sql')]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('target', choices=['local', 'cloud'])
    args = parser.parse_args()
    os.umask(0o077)
    private = Path.home() / ('.config/maeum-intake' if args.target == 'cloud' else '.local/share/maeum-portal-test')
    config = json.loads((private / ('cloud-secrets.json' if args.target == 'cloud' else 'config.json')).read_text())
    dsn = config['MAEUM_DATABASE_URL']
    parsed = urlparse(dsn)
    if args.target == 'cloud':
        if (parsed.hostname != 'aws-0-ap-northeast-2.pooler.supabase.com'
                or parsed.username != 'postgres.ojhuuipsyxewtiubujom' or parsed.path != '/postgres'):
            raise RuntimeError('Unexpected cloud target')
        tls = {'sslmode': 'verify-full', 'sslrootcert': str(ROOT / 'deploy/supabase-ca.crt')}
    else:
        if parsed.hostname != '127.0.0.1' or not parsed.path.startswith('/maeum_test_'):
            raise RuntimeError('Unexpected local target')
        tls = {'sslmode': 'disable'}
    backup = private / ('pre-org-schema-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sql')
    environment = dict(os.environ, PGHOST=parsed.hostname, PGPORT=str(parsed.port or 5432), PGUSER=unquote(parsed.username),
                       PGPASSWORD=unquote(parsed.password or ''), PGDATABASE=parsed.path[1:], PGSSLMODE=tls['sslmode'])
    if 'sslrootcert' in tls:
        environment['PGSSLROOTCERT'] = tls['sslrootcert']
    with open(backup, 'xb') as out:
        result = subprocess.run(['/opt/homebrew/opt/postgresql@17/bin/pg_dump', '--schema-only', '--schema=maeum', '--no-owner'],
                                env=environment, stdout=out, stderr=subprocess.PIPE)
    if result.returncode:
        backup.unlink()
        raise RuntimeError('Schema backup failed; database unchanged')
    with psycopg.connect(dsn, **tls, prepare_threshold=None) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('maeum-cloud-deploy',0))")
        conn.execute('CREATE TABLE IF NOT EXISTS maeum.deployment_journal(id text PRIMARY KEY,checksum text NOT NULL,applied_at timestamptz DEFAULT now())')
        if not conn.execute("SELECT to_regprocedure('maeum.registrar_valid(text)') IS NOT NULL").fetchone()[0]:
            raise RuntimeError('Email login migration must be applied first')
        for journal_id, migration in MIGRATIONS:
            checksum = hashlib.sha256(migration.read_bytes()).hexdigest()
            previous = conn.execute("SELECT checksum FROM maeum.deployment_journal WHERE id=%s", (journal_id,)).fetchone()
            if previous and previous[0] != checksum:
                raise RuntimeError('Organization migration checksum differs; review required')
            if not previous:
                conn.execute(migration.read_text())
                conn.execute("INSERT INTO maeum.deployment_journal(id,checksum) VALUES(%s,%s)", (journal_id, checksum))
    print('Reviewed organization-admin functions applied. Private schema backup saved; credentials withheld.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Organization migration failed:', type(exc).__name__, '(details withheld)')
        sys.exit(1)
