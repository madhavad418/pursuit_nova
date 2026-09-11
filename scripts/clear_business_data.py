"""Remove all business records and keep user accounts (with their passwords), roles, permissions and settings.

Deletes companies, contacts, prospects, meetings, MoMs, actions, opportunities, follow-ups, opportunity teams,
documents, record shares, notifications and targets. Audit and security logs are kept unless --include-logs.

Usage (from backend/):
  PYTHONPATH=. python ../scripts/backup_db.py                       # take a backup first
  PYTHONPATH=. python ../scripts/clear_business_data.py --yes
Uses DATABASE_URL (local SQLite by default), so it works the same against Railway PostgreSQL.
"""
import argparse
from sqlalchemy import delete, func, select
from app.db import engine, metadata, DATABASE_URL

BUSINESS_TABLES = {"companies", "contacts", "leads", "meetings", "moms", "actions", "opportunities", "followups",
                   "opportunity_team", "documents", "record_shares", "notifications", "targets"}
LOG_TABLES = {"audit_logs", "security_logs", "revoked_sessions"}


def counts(names):
    with engine.connect() as c:
        return {t.name: c.execute(select(func.count()).select_from(t)).scalar_one() for t in metadata.sorted_tables if t.name in names}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--yes", action="store_true", help="actually delete (otherwise only shows what would be removed)")
    ap.add_argument("--include-logs", action="store_true", help="also clear audit logs, security logs and revoked sessions")
    args = ap.parse_args()
    targets = BUSINESS_TABLES | (LOG_TABLES if args.include_logs else set())
    print(f"Database: {engine.url.render_as_string(hide_password=True)}")
    before = counts(targets)
    for name, n in sorted(before.items()): print(f"  {name:<18} {n}")
    if not args.yes:
        print("Dry run. Re-run with --yes to delete these rows."); return
    with engine.begin() as c:
        # Children before parents, so no foreign key is ever left pointing at a deleted row.
        for t in reversed(metadata.sorted_tables):
            if t.name in targets: c.execute(delete(t))
    print(f"Deleted {sum(before.values())} rows. Users kept: {counts({'users'})['users']}")


if __name__ == "__main__":
    main()
