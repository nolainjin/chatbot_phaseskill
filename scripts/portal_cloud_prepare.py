"""Apply reviewed additive schema to the existing project, with private backup.
Run only on explicit deployment authorization. No existing conversations imported.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.parse import urlparse, quote
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path.home() / '.config/maeum-intake'
CONFIG = PRIVATE / 'cloud-secrets.json'


def save(config):
    temporary = CONFIG.with_suffix('.new')
    with open(temporary, 'w', opener=lambda p, f: os.open(p, f, 0o600)) as out:
        json.dump(config, out)
    os.replace(temporary, CONFIG)


def main():
    os.umask(0o077)
    config = json.loads(CONFIG.read_text())
    owner = urlparse(config['MAEUM_DATABASE_URL'])
    if (owner.hostname != 'aws-0-ap-northeast-2.pooler.supabase.com'
            or owner.username != 'postgres.ojhuuipsyxewtiubujom'
            or owner.path != '/postgres' or owner.port not in (5432, 6543)):
        raise RuntimeError('Unexpected deployment database target')
    backup = PRIVATE / 'pre-portal-cloud-schema.sql'
    if not backup.exists():
        env = dict(os.environ, PGHOST=owner.hostname, PGPORT=str(owner.port), PGUSER=owner.username,
                   PGPASSWORD=owner.password, PGDATABASE='postgres', PGSSLMODE='verify-full',
                   PGSSLROOTCERT=str(ROOT / 'deploy/supabase-ca.crt'))
        with open(backup, 'wb') as out:
            result = subprocess.run(['/opt/homebrew/opt/postgresql@17/bin/pg_dump', '--schema-only', '--schema=maeum', '--no-owner'],
                                    env=env, stdout=out, stderr=subprocess.PIPE)
        if result.returncode:
            backup.unlink()
            raise RuntimeError('Schema backup failed; database unchanged')
    files = [ROOT / 'supabase/migrations' / name for name in (
        '202611040002_portal.sql', '202611040003_portal_sources_identity.sql',
        '202611040004_portal_runtime_boundary.sql', '202611040005_portal_cloud_identity.sql')]
    files += [ROOT / 'deploy/portal_cloud_roles.sql']
    bundle = '\n'.join(p.read_text() for p in files)
    fingerprint = hashlib.sha256(bundle.encode()).hexdigest()
    role_keys = {'maeum_portal': 'PORTAL_DATABASE_URL', 'maeum_auth': 'PORTAL_AUTH_DATABASE_URL', 'maeum_engine': 'PORTAL_ENGINE_DATABASE_URL'}
    with psycopg.connect(config['MAEUM_DATABASE_URL'], sslmode='verify-full',
                         sslrootcert=str(ROOT / 'deploy/supabase-ca.crt'), prepare_threshold=None) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('maeum-cloud-deploy',0))")
        existing = conn.execute("SELECT to_regclass('maeum.portal_users')").fetchone()[0]
        if existing:
            old = conn.execute("SELECT checksum FROM maeum.deployment_journal WHERE id='portal-cloud-v1'").fetchone()
            if not old or old[0] != fingerprint:
                raise RuntimeError('Existing schema differs; review before migration')
            print('Reviewed cloud schema already applied.')
            return
        for role, key in role_keys.items():
            if conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
                raise RuntimeError('Unexpected existing role; no credentials changed')
            password = secrets.token_urlsafe(36)
            config[key] = f'postgresql://{role}.ojhuuipsyxewtiubujom:{quote(password)}@{owner.hostname}:{owner.port}/postgres'
            conn.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {}').format(sql.Identifier(role), sql.Literal(password)))
        conn.execute(bundle)
        conn.execute('CREATE TABLE maeum.deployment_journal(id text PRIMARY KEY,checksum text NOT NULL,applied_at timestamptz DEFAULT now())')
        conn.execute("INSERT INTO maeum.deployment_journal(id,checksum) VALUES('portal-cloud-v1',%s)", (fingerprint,))
        # Private credentials saved before commit, to avoid losing access on a disk error.
        config.setdefault('PORTAL_CODE_SECRET', secrets.token_urlsafe(48))
        config.setdefault('PORTAL_TRIAL_PASSWORD', secrets.token_urlsafe(24))
        save(config)
    print('Additive portal schema, restricted roles and auth identity triggers applied; credentials withheld.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Cloud preparation failed:', type(exc).__name__, '(details withheld to protect credentials)')
        sys.exit(1)
