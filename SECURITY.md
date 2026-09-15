# Security Policy — PursuitNova

## Data Protection Rules

### NEVER delete existing data
- **No bulk deletes** — never run DELETE statements against production tables without explicit written approval from the project owner.
- **Deactivate, don't delete** — users should be deactivated (set `active=false`), not removed from the database. They may own leads, opportunities, and audit trails.
- **Soft-delete pattern** — when removing records, prefer marking them inactive over hard deletion. Hard deletes cascade and can destroy audit history.
- **CSV imports are additive only** — the import feature creates new records. It never updates or removes existing companies, leads, contacts, or actions.
- **Seed functions guard against overwrite** — all seed functions check `if count > 0: return` before inserting. They never truncate or replace existing data.

### Database migrations
- All schema changes must be **additive** (new columns, new tables). Never drop columns or tables in production.
- Use `_add_missing_columns()` with `ALTER TABLE ADD COLUMN` for safe migrations.
- New tables use `checkfirst=True` so they are only created if they don't already exist.
- The `category` column on the `users` table is added via migration — existing user rows get `NULL` and are unaffected.

### Authentication and sessions
- Passwords are hashed with **Argon2** — never store plaintext passwords.
- Sessions use **JWT** in HTTP-only cookies with CSRF double-submit protection.
- MFA (TOTP) is supported and should be enabled for admin accounts.
- Session tokens can be revoked — revoked JTIs are stored in `revoked_sessions`.
- Production enforces `COOKIE_SECURE=true` and a strong `JWT_SECRET` (32+ characters).

### Authorization
- **Role-based access control (RBAC)** with hierarchy-scoped visibility.
- Users only see their own work and their direct/indirect reports' work.
- Peers cannot see each other's data.
- 23 granular permissions control access to every feature.
- Admin operations require `USER_ADMIN` or `ROLE_ADMIN` permissions.
- Destructive operations (delete lead, delete role) require Super Admin or Admin role.

### API security
- All mutating endpoints (`POST`, `PUT`, `DELETE`) require CSRF validation.
- CORS origins are explicitly whitelisted — no wildcards in production.
- File uploads (CSV import) validate encoding, structure, and content before processing.
- SQL injection is prevented by SQLAlchemy's parameterized queries — never use raw string interpolation.
- Rate limiting should be configured at the reverse proxy / Railway level.

### CSV import safety
- Uploaded files are parsed in-memory — never written to disk.
- Encoding is auto-detected (UTF-8, Latin-1, CP1252) to prevent injection via encoding tricks.
- Duplicate companies are detected by normalized name and linked, not duplicated.
- Duplicate leads (same company) are skipped with a warning.
- All import operations are logged in the audit trail with source "csv".
- Errors and warnings are returned to the user — no silent failures.

### Environment variables
- `JWT_SECRET` — must be 32+ characters in production. Never commit to git.
- `INTEGRATION_ENCRYPTION_KEY` — Fernet key for Microsoft token encryption.
- `DATABASE_URL` — production PostgreSQL connection string. Never commit.
- `SEED_DEMO` and `SEED_DEMO_DATA` — must be `false` in production. Startup enforces this.
- `.env` files are gitignored. Only `.env.example` is committed.

### Audit trail
- Every create, update, delete, and import operation is logged in `audit_logs`.
- Security events (login, logout, password change, MFA) are logged in `security_logs`.
- Audit logs are scoped to the user's hierarchy — Super Admins see all, others see only their tree.

### Deployment
- Production rejects startup if `SEED_DEMO=true`, weak JWT secret, or insecure cookies.
- Static frontend is built at deploy time and served by FastAPI — no separate CDN needed.
- Database schema is managed by `AUTO_CREATE_SCHEMA` flag — set to `false` when using Alembic.
