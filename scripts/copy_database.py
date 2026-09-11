"""Copy a PursuitNova database into another one, e.g. local SQLite -> Railway PostgreSQL.

Every user keeps their password (hashes are copied unchanged), along with roles, permissions, reporting lines,
settings and any business data. The target must already have the schema (deploy the app once so
`alembic upgrade head` runs) and must not contain business data; its seeded reference rows are replaced.

Usage (from backend/):
  PYTHONPATH=. python ../scripts/copy_database.py --target "<Railway DATABASE_PUBLIC_URL>" --yes
  (--source defaults to the local SQLite database)
"""
import argparse
from sqlalchemy import create_engine, delete, func, insert, inspect, select, text, update
from app.db import metadata, normalize_database_url

SKIP = {"revoked_sessions"}                        # sessions never carry over between deployments
LOGS = {"audit_logs", "security_logs"}
BUSINESS = {"companies", "leads", "opportunities"}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", default="sqlite:///./data/pursuitnova.db")
    ap.add_argument("--target", required=True)
    ap.add_argument("--skip-logs", action="store_true", help="do not copy audit and security logs")
    ap.add_argument("--yes", action="store_true", help="replace the target's rows (otherwise only checks and reports)")
    args = ap.parse_args()
    src = create_engine(normalize_database_url(args.source))
    dst = create_engine(normalize_database_url(args.target))
    print(f"source: {src.url.render_as_string(hide_password=True)}\ntarget: {dst.url.render_as_string(hide_password=True)}")

    missing = {t.name for t in metadata.sorted_tables} - set(inspect(dst).get_table_names())
    if missing:
        raise SystemExit(f"Target has no schema yet ({len(missing)} tables missing). Deploy the app once so migrations run, then retry.")
    with dst.connect() as c:
        busy = {t: c.execute(select(func.count()).select_from(metadata.tables[t])).scalar_one() for t in BUSINESS}
    if any(busy.values()):
        raise SystemExit(f"Target already holds business data {busy}; refusing to overwrite it.")

    tables = [t for t in metadata.sorted_tables if t.name not in SKIP and not (args.skip_logs and t.name in LOGS)]
    with src.connect() as c:
        data = {t.name: [dict(r._mapping) for r in c.execute(select(t))] for t in tables}
    for t in tables: print(f"  {t.name:<22} {len(data[t.name])}")
    if not args.yes:
        print("Check only. Re-run with --yes to copy."); return

    with dst.begin() as c:
        for t in reversed(metadata.sorted_tables):
            c.execute(delete(t))
        for t in tables:
            rows = data[t.name]
            if not rows: continue
            # Self-references (users.manager_id) are filled in after every row exists.
            self_refs = [fk.parent.name for fk in t.foreign_keys if fk.column.table is t]
            c.execute(insert(t), [{**r, **{k: None for k in self_refs}} for r in rows])
            for r in rows:
                vals = {k: r[k] for k in self_refs if r[k] is not None}
                if vals: c.execute(update(t).where(t.c.id == r["id"]).values(**vals))
        if dst.dialect.name == "postgresql":
            # Rows were inserted with explicit ids; move each id sequence past them.
            for t in tables:
                if "id" in t.c and t.c.id.primary_key:
                    c.execute(text(f"SELECT setval(pg_get_serial_sequence('{t.name}', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {t.name}"))
    print("Copy complete.")


if __name__ == "__main__":
    main()
