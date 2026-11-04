"""Create/reuse ONLY a private local test cluster, seed two synthetic institutions.

No cloud secrets are read. Never connects to the existing Supabase/Vercel projects.
Usage: .venv/bin/python scripts/portal_local.py [init|serve|test|stop]
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = Path(os.getenv("MAEUM_LOCAL_ROOT", str(Path.home() / ".local/share/maeum-portal-test")))
PG = Path(os.getenv("MAEUM_PG_BIN", "/opt/homebrew/opt/postgresql@17/bin"))
PORT = int(os.getenv("MAEUM_LOCAL_DB_PORT", "55439"))
WEB_PORT = int(os.getenv("MAEUM_LOCAL_WEB_PORT", "8797"))


def run(args, **kw):
    return subprocess.run([str(x) for x in args], check=True, **kw)


def configure():
    config = json.loads((BASE / "config.json").read_text())
    os.environ.update(config)
    return config


def seed(conn, password):
    from app.portal_auth import hash_password
    full = ["report:read", "raw:read", "review:write", "link:issue", "member:manage", "audit:read"]
    counselor = ["report:read", "raw:read", "review:write"]
    for org in ("A", "B"):
        conn.execute("INSERT INTO maeum.organizations VALUES(%s,%s,true)", (org, "합성 " + org + " 상담기관"))
        for suffix, permissions in (("0", full), ("1", counselor), ("2", ["report:read"])):
            if org == "B" and suffix == "2":
                continue
            uid = org + suffix
            conn.execute("INSERT INTO maeum.portal_users(id,email,password_hash) VALUES(%s,%s,%s)", (uid, uid.lower() + "@example.test", hash_password(password)))
            conn.execute("INSERT INTO maeum.memberships(org_id,user_id,permissions) VALUES(%s,%s,%s)", (org, uid, permissions))


def init():
    BASE.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(BASE, 0o700)
    cluster = BASE / "pg"
    if not cluster.exists():
        run([PG / "initdb", "-D", cluster, "-U", "maeum_local_owner", "--auth-local=trust", "--auth-host=scram-sha-256", "--no-locale", "-E", "UTF8"], stdout=subprocess.DEVNULL)
    # Unix socket is inside a private directory; TCP disabled to avoid trust exposure.
    status = subprocess.run([str(PG / "pg_ctl"), "-D", str(cluster), "status"], stdout=subprocess.DEVNULL)
    if status.returncode != 0:
        listen = "127.0.0.1" if (BASE / "config.json").exists() else ""
        run([PG / "pg_ctl", "-D", cluster, "-l", BASE / "postgres.log", "-o", f"-k {BASE} -p {PORT} -h '{listen}'", "start"], stdout=subprocess.DEVNULL)
    import psycopg
    from psycopg import sql
    if not (BASE / "config.json").exists():
        owner_password, runtime_password, auth_password = (secrets.token_urlsafe(32) for _ in range(3))
        database = "maeum_test_portal"
        with psycopg.connect(host=str(BASE), port=PORT, user="maeum_local_owner", dbname="postgres", autocommit=True) as conn:
            conn.execute(sql.SQL("ALTER ROLE maeum_local_owner PASSWORD {}").format(sql.Literal(owner_password)))
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='maeum_portal'").fetchone():
                conn.execute("CREATE ROLE maeum_portal LOGIN NOSUPERUSER NOBYPASSRLS")
            conn.execute(sql.SQL("ALTER ROLE maeum_portal PASSWORD {}").format(sql.Literal(runtime_password)))
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='maeum_auth'").fetchone():
                conn.execute("CREATE ROLE maeum_auth LOGIN NOSUPERUSER NOBYPASSRLS")
            conn.execute(sql.SQL("ALTER ROLE maeum_auth PASSWORD {}").format(sql.Literal(auth_password)))
            if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (database,)).fetchone():
                conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        # Application uses explicit loopback with SCRAM. This cluster has no other databases with user data.
        run([PG / "pg_ctl", "-D", cluster, "-m", "fast", "stop"], stdout=subprocess.DEVNULL)
        with (cluster / "postgresql.conf").open("a") as f:
            f.write("\nlisten_addresses='127.0.0.1'\n")
        run([PG / "pg_ctl", "-D", cluster, "-l", BASE / "postgres.log", "-o", f"-k {BASE} -p {PORT}", "start"], stdout=subprocess.DEVNULL)
        owner = f"postgresql://maeum_local_owner:{owner_password}@127.0.0.1:{PORT}/{database}"
        runtime = f"postgresql://maeum_portal:{runtime_password}@127.0.0.1:{PORT}/{database}"
        auth_url = f"postgresql://maeum_auth:{auth_password}@127.0.0.1:{PORT}/{database}"
        password = secrets.token_urlsafe(18)
        with psycopg.connect(owner) as conn:
            if not conn.execute("SELECT to_regclass('maeum.portal_users')").fetchone()[0]:
                for role in ("anon", "authenticated"):
                    if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                        conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
                conn.execute((ROOT / "supabase/migrations/202611040001_cloud_store.sql").read_text())
                conn.execute((ROOT / "supabase/migrations/202611040002_portal.sql").read_text())
                conn.execute((ROOT / "supabase/migrations/202611040003_portal_sources_identity.sql").read_text())
                conn.execute((ROOT / "supabase/migrations/202611040004_portal_runtime_boundary.sql").read_text())
                conn.execute((ROOT / "supabase/migrations/202611040005_portal_cloud_identity.sql").read_text())
                conn.execute((ROOT / "supabase/migrations/202611040006_email_login.sql").read_text())
                conn.execute((ROOT / "supabase/migrations/202611050001_org_admin.sql").read_text())
                conn.execute((ROOT / "supabase/migrations/202611050002_registrar_login.sql").read_text())
                seed(conn, password)
            else:
                # Recover interrupted first provisioning, never run when config exists.
                from app.portal_auth import hash_password
                conn.execute("UPDATE maeum.portal_users SET password_hash=%s WHERE id IN ('A0','A1','A2','B0','B1')", (hash_password(password),))
        config = {"MAEUM_DATABASE_URL": owner, "PORTAL_DATABASE_URL": runtime, "PORTAL_AUTH_DATABASE_URL": auth_url,
                  "PORTAL_ENABLED": "1", "PORTAL_LOCAL_TEST": "1", "PORTAL_ORIGIN": f"http://127.0.0.1:{WEB_PORT}",
                  "PORTAL_CODE_SECRET": secrets.token_urlsafe(48), "PARTICIPANT_TICKET_SECRET": secrets.token_urlsafe(48),
                  "PORTAL_MAIL_DIR": str(BASE / "mail"), "MODEL": "fake", "KNOWLEDGE_DIR": str(ROOT / "knowledge-maeum"),
                  "DATA_DIR": str(BASE / "isolated-data"), "PRIVATE_LOCAL_UI": "1", "PUBLIC_CHAT_UI": "0", "DAILY_REQUEST_CAP": "10000"}
        private_write(BASE / "config.json", json.dumps(config))
        private_write(BASE / "accounts.txt", "LOCAL SYNTHETIC ONLY\nUsers: a0@example.test, a1@example.test, a2@example.test, b0@example.test, b1@example.test\nPassword: " + password + "\n")
    print("Local fixture ready. Credentials: " + str(BASE / "accounts.txt"))


def private_write(path, text):
    with open(path, "x", opener=lambda p, f: os.open(p, f, 0o600)) as f:
        f.write(text)


def data_hash():
    return {str(p.relative_to(ROOT / "data")): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "data").rglob("*") if p.is_file()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init", "serve", "test", "stop"], default="serve", nargs="?")
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.action == "stop":
        run([PG / "pg_ctl", "-D", BASE / "pg", "-m", "fast", "stop"])
        return
    init()
    if args.action == "init":
        return
    configure()
    if args.action == "serve":
        print(f"Local portal: http://127.0.0.1:{WEB_PORT}/portal")
        # No access logs: link exchanges and report IDs are not logged.
        os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(WEB_PORT), "--no-access-log"])
    before = data_hash()
    # Portal tests provision their own database; the persistent demo DB is not cleared.
    os.environ["PORTAL_TEST_CONFIG"] = str(BASE / "config.json")
    for key in list(configure()):
        if key != "PORTAL_TEST_CONFIG":
            os.environ.pop(key, None)
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "--tb=short", "tests/test_portal.py"])
    if data_hash() != before:
        raise RuntimeError("Original data/ content changed")
    print("Original data/ hashes unchanged.")
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
