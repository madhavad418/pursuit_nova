# Deploying PursuitNova on Railway (PostgreSQL)

One Railway service runs the whole app: the Docker build compiles the React frontend, and FastAPI serves it and
`/api` from the same domain. A second Railway service provides PostgreSQL.

## 1. Put the code where Railway can build it

Either:

- **GitHub (recommended):** push this folder to a private GitHub repository, then in Railway choose
  **New Project → Deploy from GitHub repo**. Every push redeploys.
- **Railway CLI:** install it (`npm i -g @railway/cli`), then from this folder run `railway login`, `railway init`
  and `railway up`.

Railway finds the root `Dockerfile` and `railway.json` automatically. Nothing local is uploaded into the image:
`.dockerignore` excludes `backend/data`, `*.db`, `node_modules` and `.venv`.

## 2. Add PostgreSQL

In the project: **New → Database → PostgreSQL**. Railway names the service `Postgres`.

## 3. Set the app service variables

Open the app service → **Variables** and add:

| Variable | Value |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (a reference variable; Railway fills it in) |
| `APP_ENV` | `production` |
| `JWT_SECRET` | a long random value, e.g. from `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `COOKIE_SECURE` | `true` |
| `COOKIE_SAMESITE` | `lax` |
| `AUTO_CREATE_SCHEMA` | `false` (Alembic migrations own the schema) |
| `SEED_DEMO` | `false` |
| `CORS_ORIGINS` | your app URL, e.g. `https://pursuitnova-production.up.railway.app` |
| `CORPORATE_CURRENCY` | `USD` (or your reporting currency) |
| `METRICS_TOKEN` | a random value (protects `/metrics`) |

Optional, only for a brand-new empty database where you are **not** copying existing accounts (step 6):

| Variable | Value |
|---|---|
| `INITIAL_ADMIN_EMAIL` | e.g. `rreddy@jsanconsulting.com` |
| `INITIAL_ADMIN_PASSWORD` | a strong first password (change it after first login) |
| `INITIAL_ADMIN_NAME` | e.g. `Ram Reddy` |

The first Super Admin is only created while the users table is empty; remove these two password variables afterwards.

The app refuses to start in production if `JWT_SECRET` is shorter than 32 characters, `COOKIE_SECURE` is not
`true`, or `SEED_DEMO` / `SEED_DEMO_DATA` is `true`.

## 4. Deploy and open it

1. Deploy (or push). On start the container runs `alembic upgrade head`, then starts the API on Railway's `PORT`.
2. **Settings → Networking → Generate Domain** gives you the public URL. Put that URL in `CORS_ORIGINS`.
3. Railway checks `/readyz` (configured in `railway.json`) before switching traffic.

On every start the app also ensures the reference data exists: roles, permissions, field permissions, currency
settings, FX rates, master values and workflow rules. It never adds demo users or demo business data in production.

## 5. Custom domain (optional)

**Settings → Networking → Custom Domain**, e.g. `pursuitnova.jsanconsulting.com`, then add the CNAME Railway shows
to your DNS. Update `CORS_ORIGINS` to the new URL.

## 6. Bring over the existing accounts

To move every existing user (same emails, same passwords, same roles and reporting lines) from the local database
into Railway:

1. Deploy once (steps 1–4) so the tables exist. Leave the `INITIAL_ADMIN_*` variables unset.
2. In Railway open the **Postgres** service → **Variables** and copy `DATABASE_PUBLIC_URL`.
3. On your computer, from the `backend` folder:

```powershell
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe ..\scripts\copy_database.py --target "<DATABASE_PUBLIC_URL>"          # check only
.\.venv\Scripts\python.exe ..\scripts\copy_database.py --target "<DATABASE_PUBLIC_URL>" --yes    # copy
```

The script refuses to run if the target already contains companies, prospects or opportunities.

## 7. Backups

Railway PostgreSQL has backups under the Postgres service → **Backups**. For your own copy, with the PostgreSQL
client tools installed: `pg_dump --format=custom --file pursuitnova.dump "<DATABASE_PUBLIC_URL>"`.

## Maintenance scripts

Run from `backend` with `PYTHONPATH=.`; they use `DATABASE_URL` (set it to the Railway public URL to target production):

- `scripts/backup_db.py`: SQLite copy or `pg_dump`
- `scripts/clear_business_data.py --yes`: remove all business records, keep accounts, roles and settings
- `scripts/copy_database.py`: copy one database into another (step 6)
- `scripts/bootstrap_admin.py`: create an extra Super Admin from `ADMIN_EMAIL` / `ADMIN_PASSWORD`
