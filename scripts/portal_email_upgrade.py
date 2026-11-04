"""Apply the reviewed email-login migration to an explicitly selected target.

Usage: .venv/bin/python scripts/portal_email_upgrade.py local --registrar a0@example.test
       .venv/bin/python scripts/portal_email_upgrade.py cloud --registrar OWNER_EMAIL
No sender credentials, auth users or conversations are created by this script.
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
MIGRATION = ROOT / 'supabase/migrations/202611040006_email_login.sql'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('target', choices=['local', 'cloud'])
    parser.add_argument('--registrar', required=True)
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
    backup = private / ('pre-email-schema-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sql')
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
    checksum = hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
    with psycopg.connect(dsn, **tls, prepare_threshold=None) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('maeum-cloud-deploy',0))")
        conn.execute('CREATE TABLE IF NOT EXISTS maeum.deployment_journal(id text PRIMARY KEY,checksum text NOT NULL,applied_at timestamptz DEFAULT now())')
        previous = conn.execute("SELECT checksum FROM maeum.deployment_journal WHERE id='email-login-v1'").fetchone()
        if previous and previous[0] != checksum:
            raise RuntimeError('Email migration checksum differs; review required')
        if not previous:
            mapped = conn.execute("SELECT 1 FROM information_schema.columns WHERE table_schema='maeum' AND table_name='portal_users' AND column_name='supabase_user_id'").fetchone()
            if not mapped:
                if args.target != 'local':
                    raise RuntimeError('Cloud prerequisite migration is missing')
                conn.execute((ROOT / 'supabase/migrations/202611040005_portal_cloud_identity.sql').read_text())
            conn.execute(MIGRATION.read_text())
            conn.execute("INSERT INTO maeum.deployment_journal(id,checksum) VALUES('email-login-v1',%s)", (checksum,))
        registrar = conn.execute('SELECT id,active,supabase_user_id FROM maeum.portal_users WHERE email=%s FOR UPDATE',
                                 (args.registrar.strip().lower(),)).fetchone()
        if not registrar or not registrar[1] or (args.target == 'cloud' and not registrar[2]):
            raise RuntimeError('Registrar must be an existing active verified identity')
        conn.execute('UPDATE maeum.portal_users SET is_registrar=true WHERE id=%s', (registrar[0],))
    print('Reviewed email schema and the existing registrar applied. Private schema backup saved; credentials withheld.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Email migration failed:', type(exc).__name__, '(details withheld)')
        sys.exit(1)
